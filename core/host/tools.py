import re
from datetime import datetime

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..database.keys import (
    HISTORY_SHARE_QZONE,
    MEDIA_IMAGE,
    QZONE_TARGET_ID,
    SOURCE_COMMAND,
)
from ..reaction import mark_failed, mark_processing, mark_success
from ..tasks.interact.tracker import (
    QZONE_ACTION_COMMENTED,
    QZONE_AUTO_COMMENT_STATE_KEY,
    _mark_qzone_post_processed,
)
from .supportcomponent import SupportComponent


def _qzone_tool_period_label(hour: int) -> str:
    if 5 <= hour < 8:
        return "清晨"
    if 8 <= hour < 11:
        return "上午"
    if 11 <= hour < 14:
        return "中午"
    if 14 <= hour < 18:
        return "下午"
    if 18 <= hour < 20:
        return "傍晚"
    if 20 <= hour < 24:
        return "晚上"
    return "深夜"


def _format_qzone_tool_datetime(timestamp: int) -> str:
    try:
        ts = int(timestamp or 0)
        if ts <= 0:
            return ""
        dt = datetime.fromtimestamp(ts).astimezone()
    except Exception:
        return ""
    return f"{dt.strftime('%Y年%m月%d日 %H:%M')}（{_qzone_tool_period_label(dt.hour)}）"


class PluginToolService(SupportComponent):
    """大语言模型工具和相关事件的实际处理逻辑。"""

    async def run_daily_share_tool(
        self,
        event: AstrMessageEvent,
        share_type: str,
        source: str | None = None,
        get_image: bool = True,
        need_image: bool = False,
        need_video: bool = False,
        need_voice: bool = False,
        to_qzone: bool = False,
    ):
        if self._is_terminated:
            return ""

        if event is None:
            return "无法读取当前消息事件，不能执行分享工具。"

        self.permissions._remember_event_adapter(event)
        is_admin = self.permissions._is_admin_event(event)
        is_configured_receiver = self.permissions._is_configured_receiver_event(event)
        if to_qzone and not is_admin:
            await self.send_event(
                event, event.plain_result("分享到QQ空间仅管理员可用。")
            )
            return None
        if not (is_admin or is_configured_receiver):
            await self.send_event(
                event, self.permissions._plain_permission_denied(event)
            )
            return None

        share_target = str(getattr(event, "unified_msg_origin", "") or "").strip()
        if self.is_share_busy(share_target, global_scope=to_qzone):
            await self.send_event(
                event, event.plain_result("正如火如荼地准备中，请稍后...")
            )
            return None

        self.track_task(
            self.task_manager.command_share.async_daily_share_task(
                event,
                share_type,
                source,
                get_image,
                need_image,
                need_video,
                need_voice,
                to_qzone,
            )
        )
        return None

    async def inject_tool_context(self, event: AstrMessageEvent, req) -> None:
        try:
            tool_set = req.func_tool
            tool_names = tool_set.names() if tool_set else []
            if not tool_names:
                return

            target_uid = getattr(event, "unified_msg_origin", "")
            prompts = []
            if (
                "news_link" in tool_names
                and not self.tool_context._request_context_has_marker(
                    req, self.tool_context._NEWS_LINK_CONTEXT_MARKER
                )
            ):
                prompt = await self.tool_context._build_news_link_context_prompt(
                    target_uid
                )
                if prompt:
                    prompts.append(prompt)
            if (
                "qzone" in tool_names or "qzone_auto_interact" in tool_names
            ) and not self.tool_context._request_context_has_marker(
                req,
                self.tool_context._QZONE_CONTEXT_MARKER,
            ):
                prompt = await self.tool_context._build_qzone_context_prompt(target_uid)
                if prompt:
                    prompts.append(prompt)

            if prompts:
                self.tool_context._append_request_context_prompt(
                    req, "\n\n".join(prompts)
                )
        except Exception as e:
            logger.debug(f"[日常分享] 注入工具上下文失败: {e}")

    async def query_news_link(
        self,
        event: AstrMessageEvent,
        action: str = "link",
        index: str = "",
        query: str = "",
        source: str | None = None,
        source_explicit: bool = False,
        to_qzone: bool = False,
    ):
        if self._is_terminated:
            return ""

        if event is None:
            return "无法读取当前消息事件，不能查询新闻链接。"

        self.permissions._remember_event_adapter(event)
        is_admin = self.permissions._is_admin_event(event)
        if to_qzone and not is_admin:
            return "QQ空间新闻链接仅管理员可查询。"

        index = str(index or "").strip()
        query = str(query or "").strip()
        if index and query:
            return (
                "工具内部提示：index 和 query 不能同时填写。"
                "用户明确说第几条时只填写 index；用户只按标题查询时只填写 query。"
                "请严格依据本轮用户原话修正参数并再次调用本工具，不要向用户提及工具状态。"
            )

        source_key = (
            self.tool_context._resolve_news_source_name(source)
            if source_explicit
            else None
        )
        target_uid = QZONE_TARGET_ID if to_qzone else event.unified_msg_origin
        result = await self.task_manager.snapshot_store.get_cached_news_link(
            target_uid,
            action=action,
            index=index,
            query=query,
            source_key=source_key,
        )
        try:
            event.set_extra("daily_share_news_link_used", True)
            urls = self.tool_context._extract_news_link_urls(result)
            if urls:
                event.set_extra("daily_share_news_link_urls", urls)
        except Exception as e:
            logger.debug(f"[日常分享] 标记新闻链接状态失败: {e}")
        return result

    @staticmethod
    def _normalize_qzone_auto_interact_action(action: str = "") -> str:
        action_key = str(action or "all").strip().lower()
        return action_key if action_key in {"all", "like", "comment", "reply"} else ""

    @staticmethod
    def _format_qzone_auto_interact_result(action: str, result: dict) -> str:
        if not isinstance(result, dict):
            return "QQ 空间自动互动已触发，但没有返回可读统计。"

        label_map = {
            "all": "全部",
            "like": "自动点赞",
            "comment": "自动评论",
            "reply": "自动回评",
        }
        parts = [
            f"查询 {int(result.get('scanned', 0) or 0)} 条",
            f"点赞 {int(result.get('liked', 0) or 0)} 条",
            f"评论 {int(result.get('commented', 0) or 0)} 条",
            f"回评 {int(result.get('replied', 0) or 0)} 条",
            f"跳过 {int(result.get('skipped', 0) or 0)} 条",
            f"失败 {int(result.get('failed', 0) or 0)} 条",
        ]
        generation_failed = int(result.get("generation_failed", 0) or 0)
        if generation_failed:
            parts.append(f"生成/判断失败 {generation_failed} 条")

        prefix = f"QQ 空间{label_map.get(action, action)}执行完成"
        if not result.get("enabled"):
            prefix = f"QQ 空间{label_map.get(action, action)}未执行或未启用"

        reason = str(result.get("rate_limited_reason") or "").strip()
        suffix = (
            f"；已暂停，等待下次触发再试：{reason}"
            if result.get("rate_limited") and reason
            else ""
        )
        return f"{prefix}: {'，'.join(parts)}{suffix}"

    @staticmethod
    def _qzone_mutating_action_succeeded(action: str, result: str) -> bool:
        success_prefixes = {
            "publish": "已发布 QQ 空间说说。",
            "like": "已点赞。",
            "comment": "评论已发送。",
            "auto_comment": "自动评论已发送",
        }
        prefix = success_prefixes.get(action)
        return bool(prefix and str(result or "").startswith(prefix))

    @staticmethod
    def _qzone_auto_interaction_succeeded(result) -> bool:
        return isinstance(result, dict) and bool(result.get("enabled", True))

    async def run_qzone_auto_interaction_tool(
        self,
        event: AstrMessageEvent,
        action: str = "all",
        target_id: str = "",
    ):
        if self._is_terminated:
            return ""

        if event is None:
            return "无法读取当前消息事件，不能触发 QQ 空间自动互动。"

        self.permissions._remember_event_adapter(event)
        action_key = self.tools._normalize_qzone_auto_interact_action(action)
        if not action_key:
            return "不支持的 QQ 空间自动互动动作。可用动作：all、like、comment、reply。"

        is_admin = self.permissions._is_admin_event(event)
        sender_id = self.permissions._event_sender_id(event)
        scoped_target = str(target_id or "").strip()
        if not is_admin:
            if action_key not in {"like", "comment"}:
                return "QQ 空间全局自动互动仅管理员可用；普通用户只能触发自己说说的定向点赞、评论或续评。"
            if not sender_id:
                return "无法识别当前发送者 QQ，不能触发 QQ 空间定向续评。"
            if scoped_target and scoped_target != sender_id:
                return "普通用户只能触发自己 QQ 空间说说的定向点赞、评论或续评。"
            scoped_target = sender_id

        marked_processing = False
        operation_succeeded = False
        try:
            lock = self.task_manager.qzone_auto_interaction_lock
            if lock.locked():
                return "上一轮 QQ 空间自动互动正在执行中，请稍后再试。"
            async with lock:
                await mark_processing(event)
                marked_processing = True
                result = await self.tools._execute_qzone_auto_interact_action(
                    event, action_key, scoped_target
                )
                operation_succeeded = self.tools._qzone_auto_interaction_succeeded(
                    result
                )
            return self.tools._format_qzone_auto_interact_result(action_key, result)
        except Exception as exc:
            logger.warning(f"[日常分享] QQ 空间自动互动工具调用失败: {exc}")
            return f"QQ 空间自动互动执行失败: {exc}"
        finally:
            if marked_processing:
                await (
                    mark_success(event) if operation_succeeded else mark_failed(event)
                )

    async def _execute_qzone_auto_interact_action(
        self, event: AstrMessageEvent, action_key: str, scoped_target: str
    ):
        target_note = f"，目标={scoped_target}" if scoped_target else ""
        logger.info(f"[日常分享] 手动触发 QQ 空间自动互动: {action_key}{target_note}")
        service = self.task_manager.qzone_interaction
        if action_key == "all":
            return await service.execute_qzone_auto_interaction()
        if action_key == "like":
            return await service.execute_qzone_auto_like(
                emit_summary=True, target_id=scoped_target
            )
        if action_key == "comment":
            return await service.execute_qzone_auto_comment(
                emit_summary=True,
                target_id=scoped_target,
                target_umo=str(getattr(event, "unified_msg_origin", "") or ""),
            )
        return await service.execute_qzone_auto_reply(emit_summary=True)

    @staticmethod
    def _format_qzone_post_for_llm(
        post,
        index: int = 0,
        *,
        self_uin: int = 0,
        include_comments: bool = False,
    ) -> str:
        prefix = f"{index}. " if index else ""
        author = post.name or str(post.uin or "")
        self_flag = (
            "（我的说说）"
            if self_uin and int(getattr(post, "uin", 0) or 0) == int(self_uin)
            else ""
        )
        text = str(getattr(post, "text", "") or "").strip()
        repost = str(getattr(post, "rt_con", "") or "").strip()
        display_text = text or repost or "（无文字）"
        lines = [f"{prefix}{author}{self_flag}: {display_text}"]
        if repost and repost != text:
            repost_author = str(
                getattr(post, "rt_uinname", "") or getattr(post, "rt_uin", "") or ""
            ).strip()
            repost_prefix = f"{repost_author}: " if repost_author else ""
            lines.append(f"   转发内容: {repost_prefix}{repost}")
        rt_images = getattr(post, "rt_images", []) or []
        if rt_images:
            lines.append(f"   转发图片: {len(rt_images)} 张")
        create_time = int(getattr(post, "create_time", 0) or 0)
        time_text = _format_qzone_tool_datetime(create_time)
        if time_text:
            lines.append(f"   发布时间: {time_text}")
        lines.append(f"   ID: {post.key}")
        if post.images:
            lines.append(f"   图片: {len(post.images)} 张")
        if post.videos:
            lines.append(f"   视频: {len(post.videos)} 个")
        if include_comments and post.comments:
            comments = []
            for comment in post.comments[:8]:
                name = comment.nickname or str(comment.uin or "")
                content = str(comment.content or "").strip()
                if content:
                    comments.append(f"{name}: {content}")
            if comments:
                lines.append("   评论: " + "；".join(comments))
        return "\n".join(lines)

    @staticmethod
    def _qzone_detail_unavailable_message(post_id: str, exc: Exception) -> str:
        reason = str(exc or "").strip() or "目标说说不可查看"
        target = str(post_id or "").strip()
        suffix = f"（{target}）" if target else ""
        return f"这条缓存说说{suffix}已删除或暂时无法查看：{reason}。请重新调用 qzone.list 获取最新说说列表。"

    @staticmethod
    def _is_qzone_detail_unavailable_error(exc: Exception) -> bool:
        text = str(exc or "").lower()
        return any(
            token in text
            for token in (
                "原文已经被删除",
                "无法查看",
                "已被删除",
                "deleted",
                "not found",
            )
        )

    @staticmethod
    def _qzone_event_plain_text(event: AstrMessageEvent) -> str:
        return str(event.message_str or "").strip()

    @staticmethod
    def _qzone_compact_comment_text(text: str) -> str:
        return re.sub(r"\s+", "", str(text or "")).strip()

    def _qzone_comment_content_is_user_supplied(
        self, event: AstrMessageEvent, content: str
    ) -> bool:
        text = self.tools._qzone_compact_comment_text(content)
        if not text:
            return False
        user_text = self.tools._qzone_compact_comment_text(
            self.tools._qzone_event_plain_text(event)
        )
        return bool(user_text and text in user_text)

    async def _qzone_auto_comment_post(self, post, *, target_umo: str = "") -> str:
        generator = self.task_manager.qzone_interaction.generate_qzone_auto_comment
        loaded_state = await self.db.get_qzone_state(QZONE_AUTO_COMMENT_STATE_KEY, {})
        state = loaded_state if isinstance(loaded_state, dict) else {}

        comment = str(
            await generator(post, state=state, target_umo=target_umo) or ""
        ).strip()
        if not comment:
            return "自动评论生成结果为空，已取消发送。"

        post_key = str(getattr(post, "key", "") or "").strip()
        await self.qzone_service.comment(post_key, comment)

        processed = state.get("processed") if isinstance(state, dict) else {}
        if not isinstance(processed, dict):
            processed = {}
        _mark_qzone_post_processed(
            processed,
            post,
            QZONE_ACTION_COMMENTED,
            content=comment,
            post_key=post_key,
            post_uin=int(getattr(post, "uin", 0) or 0),
            post_tid=str(getattr(post, "tid", "") or ""),
            author=str(getattr(post, "name", "") or getattr(post, "uin", "") or ""),
        )
        state["processed"] = processed
        await self.db.set_qzone_state(QZONE_AUTO_COMMENT_STATE_KEY, state)
        return f"自动评论已发送：{comment}"

    @staticmethod
    def _qzone_normalize_images(images) -> list:
        if not images:
            return []
        if isinstance(images, str):
            return [line.strip() for line in images.splitlines() if line.strip()]
        return images if isinstance(images, list) else []

    async def _qzone_tool_self_uin(self, action_key: str) -> int:
        if action_key not in {"list", "detail", "publish"}:
            return 0
        try:
            return int(getattr(await self.qzone_service.context(), "uin", 0) or 0)
        except Exception:
            return 0

    @staticmethod
    def _qzone_tool_member_guard(
        *,
        action_key: str,
        sender_id: str,
        target_id: str,
        post_id: str,
    ) -> tuple[bool, str, str]:
        allowed_actions = {"list", "detail", "like", "comment", "auto_comment"}
        if action_key not in allowed_actions:
            return False, "QQ 空间发布和任意目标操作仅管理员可用。", target_id
        if not sender_id:
            return False, "无法识别当前发送者 QQ，不能操作 QQ 空间。", target_id

        target_for_check = str(target_id or "").strip()
        if action_key == "list":
            if target_for_check and target_for_check != sender_id:
                return False, "普通用户只能查看自己的 QQ 空间说说。", target_id
            return True, "", sender_id

        owner_id = str(post_id or "").split(":", 1)[0].strip()
        if not owner_id:
            return (
                False,
                "请先查看自己的 QQ 空间说说，再指定要操作的说说 ID。",
                target_id,
            )
        if owner_id != sender_id:
            return (
                False,
                "普通用户只能查看、点赞、评论或自动评论自己的 QQ 空间说说。",
                target_id,
            )
        return True, "", target_id

    async def _qzone_tool_list_posts(
        self,
        event: AstrMessageEvent,
        *,
        target_id: str,
        pos: int,
        num: int,
        is_admin: bool,
        sender_id: str,
        self_uin: int,
    ) -> str:
        target = str(target_id or "").strip()
        if not is_admin and sender_id and target == sender_id:
            target_label = "你的说说"
        else:
            target_label = (
                "我的说说"
                if not target or (self_uin and target == str(self_uin))
                else f"QQ {target} 的说说"
            )
        posts = await self.qzone_service.query_posts(
            target_id=target,
            pos=max(0, int(pos or 0)),
            num=min(max(int(num or 5), 1), 10),
            with_detail=False,
        )
        if not posts:
            return f"没有读取到可展示的{target_label}。"
        await self.tool_context._remember_qzone_context_posts(
            event.unified_msg_origin,
            posts,
            target_id=target,
            self_uin=self_uin,
            target_label=target_label,
        )
        header = f"当前查看：{target_label}"
        return "\n".join(
            [header]
            + [
                self.tools._format_qzone_post_for_llm(post, index, self_uin=self_uin)
                for index, post in enumerate(posts, start=1)
            ]
        )

    async def _qzone_tool_detail_post(
        self, event: AstrMessageEvent, *, post_id: str, self_uin: int
    ) -> str:
        if not post_id:
            return "请先查看 QQ 空间说说，再指定要查看详情的说说 ID。"
        try:
            post = await self.qzone_service.detail(post_id)
        except Exception as exc:
            if self.tools._is_qzone_detail_unavailable_error(exc):
                await self.tool_context._clear_qzone_context_focus(
                    event.unified_msg_origin, post_id
                )
                return self.tools._qzone_detail_unavailable_message(post_id, exc)
            raise
        await self.tool_context._remember_qzone_context_focus(
            event.unified_msg_origin, post.key
        )
        return self.tools._format_qzone_post_for_llm(
            post, self_uin=self_uin, include_comments=True
        )

    async def _qzone_tool_publish_post(
        self,
        event: AstrMessageEvent,
        *,
        content: str,
        images: list,
        self_uin: int,
    ) -> str:
        text = str(content or "").strip()
        if not text and not images:
            return "说说内容或媒体不能为空。"
        post = await self.qzone_service.publish_post(text=text, images=images)
        await self.db.add_sent_history(
            QZONE_TARGET_ID,
            HISTORY_SHARE_QZONE,
            text or "QQ 空间说说",
            True,
            source_type=SOURCE_COMMAND,
            media_type=MEDIA_IMAGE if images else "",
            media_url=str(images[0]) if images else "",
        )
        await self.tool_context._remember_qzone_context_posts(
            event.unified_msg_origin,
            [post],
            focus_post_id=post.key,
            self_uin=self_uin,
            target_label="我的说说",
        )
        self.emit_dashboard_event("qzone", {"action": "publish", "post_id": post.key})
        return f"已发布 QQ 空间说说。\n{self.tools._format_qzone_post_for_llm(post, self_uin=self_uin)}"

    async def _qzone_tool_like_post(
        self, event: AstrMessageEvent, *, post_id: str
    ) -> str:
        if not post_id:
            return "请先查看 QQ 空间说说，再指定要点赞的说说 ID。"
        await self.qzone_service.like(post_id)
        await self.tool_context._remember_qzone_context_focus(
            event.unified_msg_origin, post_id
        )
        self.emit_dashboard_event("qzone", {"action": "like", "post_id": post_id})
        return "已点赞。"

    async def _qzone_tool_comment_post(
        self, event: AstrMessageEvent, *, post_id: str, content: str
    ) -> str:
        if not post_id:
            return "请先查看 QQ 空间说说，再指定要评论的说说 ID。"
        text = str(content or "").strip()
        if not text:
            return (
                "评论内容不能为空。需要机器人自动写评论时，请使用 action=auto_comment。"
            )
        if not self.tools._qzone_comment_content_is_user_supplied(event, text):
            return "未检测到用户提供这段固定评论正文，已拒绝直发。需要机器人自动写评论时，请使用 action=auto_comment。"
        await self.qzone_service.comment(post_id, text)
        await self.tool_context._remember_qzone_context_focus(
            event.unified_msg_origin, post_id
        )
        self.emit_dashboard_event("qzone", {"action": "comment", "post_id": post_id})
        return "评论已发送。"

    async def _qzone_tool_auto_comment_post(
        self, event: AstrMessageEvent, *, post_id: str
    ) -> str:
        if not post_id:
            return "请先查看 QQ 空间说说，再指定要自动评论的说说 ID。"
        try:
            post = await self.qzone_service.detail(post_id)
        except Exception as exc:
            if self.tools._is_qzone_detail_unavailable_error(exc):
                await self.tool_context._clear_qzone_context_focus(
                    event.unified_msg_origin, post_id
                )
                return self.tools._qzone_detail_unavailable_message(post_id, exc)
            raise
        result = await self.tools._qzone_auto_comment_post(
            post,
            target_umo=str(getattr(event, "unified_msg_origin", "") or ""),
        )
        await self.tool_context._remember_qzone_context_focus(
            event.unified_msg_origin, post_id
        )
        if result.startswith("自动评论已发送"):
            self.emit_dashboard_event(
                "qzone", {"action": "auto_comment", "post_id": post_id}
            )
        return result

    async def run_qzone_tool(
        self,
        event: AstrMessageEvent,
        action: str = "list",
        post_id: str = "",
        target_id: str = "",
        content: str = "",
        images=None,
        pos: int = 0,
        num: int = 5,
    ):
        if self._is_terminated:
            return ""

        if event is None:
            return "无法读取当前消息事件，不能操作 QQ 空间。"

        self.permissions._remember_event_adapter(event)
        is_admin = self.permissions._is_admin_event(event)
        sender_id = self.permissions._event_sender_id(event)

        action_key = str(action or "list").strip().lower()
        images = self.tools._qzone_normalize_images(images)
        marked_processing = action_key in {
            "publish",
            "like",
            "comment",
            "auto_comment",
        }
        processing_started = False
        operation_succeeded = False

        try:
            self_uin = await self.tools._qzone_tool_self_uin(action_key)

            if not is_admin:
                allowed, message, target_id = self.tools._qzone_tool_member_guard(
                    action_key=action_key,
                    sender_id=sender_id,
                    target_id=target_id,
                    post_id=post_id,
                )
                if not allowed:
                    return message

            if marked_processing:
                await mark_processing(event)
                processing_started = True
            result = await self.tools._execute_qzone_tool_action(
                event,
                action_key=action_key,
                post_id=post_id,
                target_id=target_id,
                content=content,
                images=images,
                pos=pos,
                num=num,
                is_admin=is_admin,
                sender_id=sender_id,
                self_uin=self_uin,
            )
            if marked_processing:
                operation_succeeded = self.tools._qzone_mutating_action_succeeded(
                    action_key, result
                )
            return result
        except Exception as exc:
            logger.warning(f"[日常分享] QQ 空间工具调用失败: {exc}")
            return f"QQ 空间操作失败: {exc}"
        finally:
            if processing_started:
                await (
                    mark_success(event) if operation_succeeded else mark_failed(event)
                )

    async def _execute_qzone_tool_action(
        self,
        event: AstrMessageEvent,
        *,
        action_key: str,
        post_id: str,
        target_id: str,
        content: str,
        images: list,
        pos: int,
        num: int,
        is_admin: bool,
        sender_id: str,
        self_uin: int,
    ) -> str:
        if action_key == "list":
            return await self.tools._qzone_tool_list_posts(
                event,
                target_id=target_id,
                pos=pos,
                num=num,
                is_admin=is_admin,
                sender_id=sender_id,
                self_uin=self_uin,
            )
        if action_key == "detail":
            return await self.tools._qzone_tool_detail_post(
                event, post_id=post_id, self_uin=self_uin
            )
        if action_key == "publish":
            return await self.tools._qzone_tool_publish_post(
                event, content=content, images=images, self_uin=self_uin
            )
        if action_key == "like":
            return await self.tools._qzone_tool_like_post(event, post_id=post_id)
        if action_key == "comment":
            return await self.tools._qzone_tool_comment_post(
                event, post_id=post_id, content=content
            )
        if action_key == "auto_comment":
            return await self.tools._qzone_tool_auto_comment_post(
                event, post_id=post_id
            )
        return "不支持的 QQ 空间操作。可用动作：list、detail、publish、like、comment、auto_comment。"

    async def clean_news_link_llm_references(
        self, event: AstrMessageEvent, resp
    ) -> None:
        try:
            used = event.get_extra("daily_share_news_link_used")
        except Exception:
            used = None
        if not used or not resp:
            return

        try:
            original = str(resp.completion_text or "")
            cleaned = self.tool_context._strip_news_link_reference_tail(original)
            urls = event.get_extra("daily_share_news_link_urls", []) or []
            cleaned = self.tool_context._ensure_news_link_urls_in_reply(cleaned, urls)
            if cleaned != original:
                resp.completion_text = cleaned
                logger.debug("[日常分享] 已清理新闻链接模型回复中的参考链接尾部")
        except Exception as e:
            logger.warning(f"[日常分享] 清理新闻链接模型参考链接失败: {e}")

    async def clean_news_link_decorating_references(
        self, event: AstrMessageEvent
    ) -> None:
        try:
            used = event.get_extra("daily_share_news_link_used")
        except Exception:
            used = None
        if not used:
            return

        try:
            result = event.get_result()
            if not result or not result.chain:
                return

            plain_components = []
            for component in result.chain:
                component_type = getattr(component, "type", "")
                type_name = getattr(component_type, "value", component_type)
                if (
                    type_name == "Plain" or component.__class__.__name__ == "Plain"
                ) and hasattr(component, "text"):
                    plain_components.append(component)
            if not plain_components:
                return

            original = "".join(
                str(getattr(component, "text", "") or "")
                for component in plain_components
            )
            cleaned = self.tool_context._strip_news_link_reference_tail(original)
            urls = event.get_extra("daily_share_news_link_urls", []) or []
            cleaned = self.tool_context._ensure_news_link_urls_in_reply(cleaned, urls)
            if cleaned != original:
                common_prefix = 0
                for before, after in zip(original, cleaned):
                    if before != after:
                        break
                    common_prefix += 1

                offset = 0
                updated = False
                for component in plain_components:
                    text = str(getattr(component, "text", "") or "")
                    next_offset = offset + len(text)
                    if next_offset <= common_prefix:
                        offset = next_offset
                        continue
                    if not updated:
                        keep = max(0, common_prefix - offset)
                        component.text = f"{text[:keep]}{cleaned[common_prefix:]}"
                        updated = True
                    else:
                        component.text = ""
                    offset = next_offset

                if not updated:
                    plain_components[
                        -1
                    ].text = f"{plain_components[-1].text}{cleaned[common_prefix:]}"
                logger.debug("[日常分享] 已在发送前清理新闻链接参考链接尾部")
        except Exception as e:
            logger.warning(f"[日常分享] 发送前清理新闻链接参考链接失败: {e}")
        finally:
            try:
                event.set_extra("daily_share_news_link_used", None)
                event.set_extra("daily_share_news_link_urls", None)
            except Exception as e:
                logger.debug(f"[日常分享] 清理新闻链接事件标记失败: {e}")

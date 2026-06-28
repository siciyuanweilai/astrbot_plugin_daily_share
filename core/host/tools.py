from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..database.keys import (
    HISTORY_SHARE_QZONE,
    MEDIA_IMAGE,
    MEDIA_VIDEO,
    QZONE_TARGET_ID,
    SOURCE_COMMAND,
)


class PluginToolMixin:
    """大语言模型工具和相关事件的实际处理逻辑。"""

    async def _daily_share_tool_impl(
        self,
        event: AstrMessageEvent,
        share_type: str,
        source: str = None,
        get_image: bool = True,
        need_image: bool = False,
        need_video: bool = False,
        need_voice: bool = False,
        to_qzone: bool = False,
    ):
        if self._is_terminated:
            return ""

        event = self._resolve_message_event(event)
        if event is None:
            return "无法读取当前消息事件，不能执行分享工具。"

        self._remember_event_adapter(event)
        is_admin = self._is_admin_event(event)
        is_configured_receiver = self._is_configured_receiver_event(event)
        if to_qzone and not is_admin:
            await event.send(event.plain_result("分享到QQ空间仅管理员可用。"))
            return None
        if not (is_admin or is_configured_receiver):
            await event.send(self._plain_permission_denied(event))
            return None

        share_target = str(getattr(event, "unified_msg_origin", "") or "").strip()
        if self._is_share_busy(share_target, global_scope=to_qzone):
            await event.send(event.plain_result("正如火如荼地准备中，请稍后..."))
            return None

        self._track_task(
            self.task_manager.async_daily_share_task(
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

    async def _inject_news_link_context_impl(self, event: AstrMessageEvent, req) -> None:
        try:
            tool_set = getattr(req, "func_tool", None)
            tool_names = tool_set.names() if tool_set and hasattr(tool_set, "names") else []
            if "news_link" not in tool_names:
                return

            system_prompt = str(getattr(req, "system_prompt", "") or "")
            if self._NEWS_LINK_CONTEXT_MARKER in system_prompt:
                return

            prompt = await self._build_news_link_context_prompt(
                getattr(event, "unified_msg_origin", "")
            )
            if not prompt:
                return

            req.system_prompt = f"{system_prompt.rstrip()}\n\n{prompt}\n".lstrip()
        except Exception as e:
            logger.debug(f"[每日分享] 注入新闻链接上下文失败: {e}")

    async def _news_link_tool_impl(
        self,
        event: AstrMessageEvent,
        action: str = "link",
        index: str = "",
        query: str = "",
        source: str = None,
        source_explicit: bool = False,
        to_qzone: bool = False,
    ):
        if self._is_terminated:
            return ""

        event = self._resolve_message_event(event)
        if event is None:
            return "无法读取当前消息事件，不能查询新闻链接。"

        self._remember_event_adapter(event)
        is_admin = self._is_admin_event(event)
        if to_qzone and not is_admin:
            return "QQ空间新闻链接仅管理员可查询。"

        source_key = self._resolve_news_source_name(source) if source_explicit else None
        target_uid = QZONE_TARGET_ID if to_qzone else event.unified_msg_origin
        result = await self.task_manager.get_cached_news_link(
            target_uid,
            action=action,
            index=index,
            query=query,
            source_key=source_key,
            refresh_source=False,
        )
        try:
            event.set_extra("daily_share_news_link_used", True)
            urls = self._extract_news_link_urls(result)
            if urls:
                event.set_extra("daily_share_news_link_urls", urls)
        except Exception as e:
            logger.debug(f"[每日分享] 标记新闻链接状态失败: {e}")
        return result

    @staticmethod
    def _format_qzone_post_for_llm(post, index: int = 0, *, include_comments: bool = False) -> str:
        prefix = f"{index}. " if index else ""
        author = post.name or str(post.uin or "")
        text = (post.text or post.rt_con or "").strip() or "（无文字）"
        lines = [f"{prefix}{author}: {text}", f"   ID: {post.key}"]
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

    async def _qzone_tool_impl(
        self,
        event: AstrMessageEvent,
        action: str = "list",
        post_id: str = "",
        target_id: str = "",
        content: str = "",
        images=None,
        videos=None,
        pos: int = 0,
        num: int = 5,
    ):
        if self._is_terminated:
            return ""

        event = self._resolve_message_event(event)
        if event is None:
            return "无法读取当前消息事件，不能操作 QQ 空间。"

        self._remember_event_adapter(event)
        if not self._is_admin_event(event):
            return "QQ空间操作仅管理员可用。"

        action_key = str(action or "list").strip().lower()
        images = images or []
        if isinstance(images, str):
            images = [line.strip() for line in images.splitlines() if line.strip()]
        if not isinstance(images, list):
            images = []
        videos = videos or []
        if isinstance(videos, str):
            videos = [line.strip() for line in videos.splitlines() if line.strip()]
        if not isinstance(videos, list):
            videos = []

        try:
            if action_key in {"list", "feed", "view", "query", "动态", "查看"}:
                posts = await self.qzone_service.query_posts(
                    target_id=str(target_id or "").strip(),
                    pos=max(0, int(pos or 0)),
                    num=min(max(int(num or 5), 1), 10),
                    with_detail=False,
                )
                if not posts:
                    return "没有读取到可展示的 QQ 空间说说。"
                return "\n".join(
                    self._format_qzone_post_for_llm(post, index)
                    for index, post in enumerate(posts, start=1)
                )

            if action_key in {"detail", "详情"}:
                if not post_id:
                    return "请先查看 QQ 空间说说，再指定要查看详情的说说 ID。"
                post = await self.qzone_service.detail(post_id)
                return self._format_qzone_post_for_llm(post, include_comments=True)

            if action_key in {"publish", "post", "send", "发", "发布", "发说说"}:
                text = str(content or "").strip()
                if not text and not images and not videos:
                    return "说说内容或媒体不能为空。"
                post = await self.qzone_service.publish_post(text=text, images=images, videos=videos)
                await self.db.add_sent_history(
                    QZONE_TARGET_ID,
                    HISTORY_SHARE_QZONE,
                    text or "QQ 空间说说",
                    True,
                    source_type=SOURCE_COMMAND,
                    media_type=MEDIA_VIDEO if videos else MEDIA_IMAGE if images else "",
                    media_url=str(videos[0] if videos else images[0]) if (videos or images) else "",
                )
                self._page_emit_dashboard_event("qzone", {"action": "publish", "post_id": post.key})
                return f"已发布 QQ 空间说说。\n{self._format_qzone_post_for_llm(post)}"

            if action_key in {"like", "赞", "点赞"}:
                if not post_id:
                    return "请先查看 QQ 空间说说，再指定要点赞的说说 ID。"
                await self.qzone_service.like(post_id)
                self._page_emit_dashboard_event("qzone", {"action": "like", "post_id": post_id})
                return "已点赞。"

            if action_key in {"comment", "reply", "评", "评论"}:
                if not post_id:
                    return "请先查看 QQ 空间说说，再指定要评论的说说 ID。"
                text = str(content or "").strip()
                if not text:
                    return "评论内容不能为空。"
                await self.qzone_service.comment(post_id, text)
                self._page_emit_dashboard_event("qzone", {"action": "comment", "post_id": post_id})
                return "评论已发送。"

            return "不支持的 QQ 空间操作。可用动作：list、detail、publish、like、comment。"
        except Exception as exc:
            logger.warning(f"[每日分享] QQ 空间工具调用失败: {exc}")
            return f"QQ 空间操作失败: {exc}"

    async def _clean_news_link_llm_references_impl(self, event: AstrMessageEvent, resp) -> None:
        try:
            used = event.get_extra("daily_share_news_link_used")
        except Exception:
            used = None
        if not used or not resp:
            return

        try:
            original = str(resp.completion_text or "")
            cleaned = self._strip_news_link_reference_tail(original)
            urls = event.get_extra("daily_share_news_link_urls", []) or []
            cleaned = self._ensure_news_link_urls_in_reply(cleaned, urls)
            if cleaned != original:
                resp.completion_text = cleaned
                logger.debug("[每日分享] 已清理新闻链接模型回复中的参考链接尾部")
        except Exception as e:
            logger.warning(f"[每日分享] 清理新闻链接模型参考链接失败: {e}")

    async def _clean_news_link_decorating_references_impl(self, event: AstrMessageEvent) -> None:
        try:
            used = event.get_extra("daily_share_news_link_used")
        except Exception:
            used = None
        if not used:
            return

        result = event.get_result()
        if not result or not result.chain:
            return

        try:
            original = result.get_plain_text()
            cleaned = self._strip_news_link_reference_tail(original)
            urls = event.get_extra("daily_share_news_link_urls", []) or []
            cleaned = self._ensure_news_link_urls_in_reply(cleaned, urls)
            if cleaned != original:
                event.set_result(event.plain_result(cleaned))
                logger.debug("[每日分享] 已在发送前清理新闻链接参考链接尾部")
            event.set_extra("daily_share_news_link_used", None)
            event.set_extra("daily_share_news_link_urls", None)
        except Exception as e:
            logger.warning(f"[每日分享] 发送前清理新闻链接参考链接失败: {e}")

import asyncio

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ...config import ShareType
from ...constants import period_label, share_type_label
from ...toolkit import format_exception


class TaskExecutorFlowMixin:
    """分享主流程编排。"""

    async def _execute_share_for_target(
        self,
        *,
        uid: str,
        target_index: int,
        total_targets: int,
        force_type: ShareType = None,
        news_source: str = None,
        specific_target: str = None,
        event: AstrMessageEvent = None,
        history_source: str,
        period: str,
        life_ctx: str,
        r_groups: dict,
        r_users: dict,
    ) -> bool:
        progress_id = ""
        stype = force_type or ShareType.GREETING
        is_group = self._target_looks_group(uid)
        try:
            adapter_id, real_id = self.ctx_service._parse_umo(uid)
            target_specific_type = self._target_share_type_config(uid, is_group, r_groups, r_users)
            stype = force_type or await self.decide_type_with_state(
                period,
                is_qzone=False,
                target_id=uid,
                specific_type=target_specific_type,
            )

            target_label = await self._get_target_display_name(uid, event=event, is_group=is_group)
            nickname = "" if is_group else target_label
            target_display = f"{target_label}({uid})" if target_label else uid
            logger.info(
                f"[每日分享] 正在为 {target_display} 生成内容... "
                f"时段: {period_label(period)}, 类型: {share_type_label(stype)}"
            )
            progress_id = self._start_share_progress(
                source_type=history_source,
                target_id=uid,
                target_label=target_label,
                share_type=stype,
                total_targets=total_targets,
                current_index=target_index,
                enabled_steps=["content", "image", "video", "audio", "send"],
                message=f"准备为 {target_label or real_id or uid} 生成内容",
            )

            loaded_news, news_data = await self._load_execute_share_news(
                uid=uid,
                stype=stype,
                news_source=news_source,
                event=event,
                history_source=history_source,
                progress_id=progress_id,
            )
            if not loaded_news:
                return False

            self._update_share_progress(progress_id, "content", message="文案生成中")
            content_context = await self._prepare_content_context(
                target_umo=uid,
                share_type=stype,
                life_ctx=life_ctx,
                is_group=is_group,
                event=event,
                nickname=nickname,
            )
            if is_group and "group_info" in content_context["hist_data"]:
                if not specific_target and not self.ctx_service.check_group_strategy(content_context["group_info"]):
                    logger.info(f"[每日分享] 因策略跳过群组 {uid}")
                    self._finish_share_progress(progress_id, success=True, message="已按群策略跳过")
                    return True

            content = await self.content_service.generate(
                stype,
                period,
                uid,
                is_group,
                content_context["life_prompt"],
                content_context["hist_prompt"],
                news_data,
                nickname=nickname,
                recent_dynamics=content_context["recent_dynamics"],
            )
            if not content:
                logger.warning(f"[每日分享] 内容生成失败 {uid}")
                await self._record_share_failure(
                    target_id=uid,
                    share_type=stype.value,
                    message="生成失败（大语言模型无响应）",
                    error_reason="生成失败（大语言模型无响应）",
                    source_type=history_source,
                )
                if event:
                    await event.send(event.plain_result("内容生成失败，请稍后再试。"))
                self._finish_share_progress(progress_id, success=False, message="文案生成失败")
                return False
            self._complete_share_progress_step(progress_id, "content", "文案已生成")

            self.image_service.reset_last_description()
            tool_event = event if self._event_matches_target(event, uid) else None
            img_path, send_img_path, video_url, audio_path = await self._generate_execute_share_media(
                progress_id=progress_id,
                content=content,
                stype=stype,
                life_ctx=life_ctx,
                target_umo=uid,
                event=tool_event,
                period=period,
                initial_img_path=await self._maybe_attach_hot_news_image(
                    uid=uid,
                    stype=stype,
                    news_data=news_data,
                ),
            )

            send_img_path = send_img_path or img_path
            sent, media_result = await self._send_execute_share_result(
                uid=uid,
                content=content,
                send_img_path=send_img_path,
                audio_path=audio_path,
                video_url=video_url,
                event=tool_event,
                progress_id=progress_id,
            )
            if not sent:
                await self._record_share_failure(
                    target_id=uid,
                    share_type=stype.value,
                    message="发送失败",
                    error_reason="发送失败",
                    source_type=history_source,
                    media_result=media_result,
                    image_ref=send_img_path,
                    video_ref=video_url,
                )
                if event:
                    await event.send(event.plain_result("内容已生成，但发送失败，请查看日志或检查平台连接状态。"))
                self._finish_share_progress(progress_id, success=False, message="发送失败")
                return False

            await self._record_execute_share_success(
                uid=uid,
                stype=stype,
                content=content,
                history_source=history_source,
                media_result=media_result,
                image_ref=send_img_path or img_path,
                video_ref=video_url,
            )
            self._log_partial_send_errors(uid, media_result)
            if event and tool_event:
                await self._notify_partial_send_errors(event, media_result)
            self._finish_share_progress(progress_id, success=True, message="分享完成")
            return True
        except Exception as e:
            self._log_exception(f"[每日分享] 处理 {uid} 时出错", e)
            if event:
                await event.send(event.plain_result(f"分享出错: {format_exception(e)}"))
            await self._record_share_failure(
                target_id=uid,
                share_type=stype.value if isinstance(stype, ShareType) else str(stype or ""),
                message=f"分享出错: {format_exception(e)}",
                error_reason=format_exception(e),
                source_type=history_source,
            )
            if progress_id:
                self._finish_share_progress(progress_id, success=False, message="分享出错")
            return False

    async def execute_share(
        self,
        force_type: ShareType = None,
        news_source: str = None,
        specific_target: str = None,
        event: AstrMessageEvent = None,
        target_scope: str = "all",
        source_type: str = "",
    ):
        """分享主流程（支持群聊私聊独立配置与记忆序列）。"""
        if self.plugin._is_terminated:
            return

        history_source = str(source_type or ("command" if event else "scheduled")).strip()
        period = self.get_curr_period()
        life_ctx = await self.ctx_service.get_life_context()
        targets = self._resolve_execute_share_targets(specific_target, target_scope)
        if not targets:
            logger.warning("[每日分享] 未配置接收对象，且未指定目标，请在配置页填写群号或 QQ 号")
            if event:
                await event.send(event.plain_result("分享失败：未配置接收对象，也没有指定当前会话目标。"))
            return

        abort_on_target_failure = bool(specific_target)
        r_groups = self._parse_targets_config(self.receiver_conf.get("groups", []))
        r_users = self._parse_targets_config(self.receiver_conf.get("users", []))

        total_targets = len(targets)
        for target_index, uid in enumerate(targets, 1):
            if self.plugin._is_terminated:
                break
            ok = await self._execute_share_for_target(
                uid=uid,
                target_index=target_index,
                total_targets=total_targets,
                force_type=force_type,
                news_source=news_source,
                specific_target=specific_target,
                event=event,
                history_source=history_source,
                life_ctx=life_ctx,
                period=period,
                r_groups=r_groups,
                r_users=r_users,
            )
            if not ok:
                if abort_on_target_failure:
                    return
                continue
            await asyncio.sleep(2)

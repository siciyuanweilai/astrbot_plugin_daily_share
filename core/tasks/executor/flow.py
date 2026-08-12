import asyncio
from typing import TYPE_CHECKING, Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ...config import ShareType, TimePeriod
from ...constants import period_label, share_type_label
from ...database.keys import SOURCE_SCHEDULED, SOURCE_SMART
from ...toolkit import format_exception
from ..taskbase import TaskServiceBase


class TaskExecutorFlowService(TaskServiceBase):
    """分享主流程编排。"""

    if TYPE_CHECKING:

        def _target_looks_group(self, uid: str) -> bool: ...

        def _target_share_type_config(
            self, uid: str, is_group: bool, groups: dict, users: dict
        ) -> Any: ...

        def resolve_execute_share_targets(
            self,
            specific_target: str | None,
            target_scope: str,
            *,
            exclude_custom_cron: bool,
        ) -> list[str]: ...

        async def _load_execute_share_news(
            self,
            *,
            uid: str,
            stype: ShareType,
            news_source: str | None,
            event: AstrMessageEvent | None,
            history_source: str,
            progress_id: str,
        ) -> tuple[bool, object]: ...

        async def _maybe_attach_hot_news_image(
            self, *, uid: str, stype: ShareType, news_data: Any | None = None
        ) -> str | None: ...

        async def _generate_execute_share_media(
            self,
            *,
            progress_id: str,
            content: str,
            stype: ShareType,
            life_ctx: str,
            target_umo: str,
            event: AstrMessageEvent | None,
            period: TimePeriod,
            initial_img_path: str | None,
        ) -> tuple[str | None, str | None, str | None, str | None, str]: ...

        async def _send_execute_share_result(
            self,
            *,
            uid: str,
            content: str,
            send_img_path: str | None,
            audio_path: str | None,
            video_url: str | None,
            event: AstrMessageEvent | None,
            progress_id: str,
        ) -> tuple[bool, dict]: ...

        async def _record_execute_share_success(
            self,
            *,
            uid: str,
            stype: ShareType,
            content: str,
            history_source: str,
            media_result: dict,
            image_ref: str | None,
            video_ref: str | None,
            news_snapshot_data: dict | None,
            news_image_url: str | None,
            image_description: str,
            degradation_reason: str,
        ) -> None: ...

    async def _prepare_execute_share_target(
        self,
        *,
        uid: str,
        target_index: int,
        total_targets: int,
        force_type: ShareType | None = None,
        history_source: str,
        period: TimePeriod,
        event: AstrMessageEvent | None = None,
        r_groups: dict,
        r_users: dict,
    ) -> dict:
        is_group = self._target_looks_group(uid)
        adapter_id, real_id = self.ctx_service.parse_umo(uid)
        target_specific_type = self._target_share_type_config(
            uid, is_group, r_groups, r_users
        )
        stype = force_type or await self.services.type_selector.decide_type_with_state(
            period,
            is_qzone=False,
            target_id=uid,
            specific_type=target_specific_type,
        )

        target_label = await self.services.targets.get_target_display_name(
            uid, event=event, is_group=is_group
        )
        target_display = f"{target_label}({uid})" if target_label else uid
        logger.info(
            f"[日常分享] 正在为 {target_display} 生成内容... "
            f"时段: {period_label(period)}, 类型: {share_type_label(stype)}"
        )
        progress_id = self.services.progress.start_share_progress(
            source_type=history_source,
            target_id=uid,
            target_label=target_label,
            share_type=stype,
            total_targets=total_targets,
            current_index=target_index,
            enabled_steps=["content", "image", "video", "audio", "send"],
            message=f"准备为 {target_label or real_id or uid} 生成内容",
        )
        return {
            "is_group": is_group,
            "stype": stype,
            "target_label": target_label,
            "nickname": "" if is_group else target_label,
            "progress_id": progress_id,
        }

    async def _generate_execute_share_content(
        self,
        *,
        uid: str,
        stype: ShareType,
        period: TimePeriod,
        life_ctx: str,
        is_group: bool,
        nickname: str,
        news_data,
        progress_id: str,
        history_source: str,
        specific_target: str | None = None,
        event: AstrMessageEvent | None = None,
    ) -> tuple[bool | None, str]:
        self.services.progress.update_share_progress(
            progress_id, "content", message="文案生成中"
        )
        content_context = await self.services.executor_helpers.prepare_content_context(
            target_umo=uid,
            share_type=stype,
            life_ctx=life_ctx,
            is_group=is_group,
            event=event,
            nickname=nickname,
        )
        if is_group and "group_info" in content_context["hist_data"]:
            if not specific_target and not self.ctx_service.check_group_strategy(
                content_context["group_info"]
            ):
                logger.info(f"[日常分享] 因策略跳过群组 {uid}")
                self.services.progress.finish_share_progress(
                    progress_id, success=True, message="已按群策略跳过"
                )
                return True, ""

        content = await self.content_service.generate(
            stype,
            period,
            uid,
            is_group,
            content_context["life_prompt"],
            news_data,
            nickname=nickname,
            recent_dynamics=content_context["recent_dynamics"],
            structured_history=content_context.get("structured_history", ""),
        )
        if content:
            self.services.progress.complete_share_progress_step(
                progress_id, "content", "文案已生成"
            )
            return None, content

        logger.warning(f"[日常分享] 内容生成失败 {uid}")
        await self.services.executor_helpers.record_share_failure(
            target_id=uid,
            share_type=stype.value,
            message="生成失败（大语言模型无响应）",
            error_reason="生成失败（大语言模型无响应）",
            source_type=history_source,
        )
        if event:
            await self.send_event(
                event, event.plain_result("内容生成失败，请稍后再试。")
            )
        self.services.progress.finish_share_progress(
            progress_id, success=False, message="文案生成失败"
        )
        return False, ""

    async def _send_execute_share_content(
        self,
        *,
        uid: str,
        stype: ShareType,
        content: str,
        news_data,
        life_ctx: str,
        period: TimePeriod,
        progress_id: str,
        history_source: str,
        event: AstrMessageEvent | None = None,
    ) -> bool:
        tool_event = (
            event if self.services.targets.event_matches_target(event, uid) else None
        )
        hot_news_image_url = await self._maybe_attach_hot_news_image(
            uid=uid,
            stype=stype,
            news_data=news_data,
        )
        (
            img_path,
            send_img_path,
            video_url,
            audio_path,
            image_description,
        ) = await self._generate_execute_share_media(
            progress_id=progress_id,
            content=content,
            stype=stype,
            life_ctx=life_ctx,
            target_umo=uid,
            event=tool_event,
            period=period,
            initial_img_path=hot_news_image_url,
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
            await self.services.executor_helpers.record_share_failure(
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
                await self.send_event(
                    event,
                    event.plain_result(
                        "内容已生成，但发送失败，请查看日志或检查平台连接状态。"
                    ),
                )
            self.services.progress.finish_share_progress(
                progress_id, success=False, message="发送失败"
            )
            return False

        news_snapshot_data = None
        news_image_url = None
        if (
            stype == ShareType.NEWS
            and news_data
            and hot_news_image_url
            and media_result.get("image_sent")
        ):
            news_snapshot_data = self.services.snapshots.news_snapshot_payload(
                news_data[0], news_data[1]
            )
            news_image_url = (
                media_result.get("downloaded_image_path")
                or media_result.get("image_path")
                or hot_news_image_url
                or ""
            )

        await self._record_execute_share_success(
            uid=uid,
            stype=stype,
            content=content,
            history_source=history_source,
            media_result=media_result,
            image_ref=send_img_path or img_path,
            video_ref=video_url,
            news_snapshot_data=news_snapshot_data,
            news_image_url=news_image_url,
            image_description=image_description,
            degradation_reason=self.services.progress.share_progress_degradation_reason(
                progress_id
            ),
        )
        self.services.executor_helpers.log_partial_send_errors(uid, media_result)
        if event and tool_event:
            await self.services.executor_helpers.notify_partial_send_errors(
                event, media_result
            )
        self.services.progress.finish_share_progress(
            progress_id, success=True, message="分享完成"
        )
        return True

    async def _execute_share_for_target(
        self,
        *,
        uid: str,
        target_index: int,
        total_targets: int,
        force_type: ShareType | None = None,
        news_source: str | None = None,
        specific_target: str | None = None,
        event: AstrMessageEvent | None = None,
        history_source: str,
        period: TimePeriod,
        life_ctx: str,
        r_groups: dict,
        r_users: dict,
    ) -> bool:
        progress_id = ""
        stype = force_type or ShareType.GREETING
        try:
            target = await self._prepare_execute_share_target(
                uid=uid,
                target_index=target_index,
                total_targets=total_targets,
                force_type=force_type,
                history_source=history_source,
                period=period,
                event=event,
                r_groups=r_groups,
                r_users=r_users,
            )
            stype = target["stype"]
            progress_id = target["progress_id"]

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

            early_result, content = await self._generate_execute_share_content(
                uid=uid,
                stype=stype,
                period=period,
                life_ctx=life_ctx,
                is_group=target["is_group"],
                nickname=target["nickname"],
                news_data=news_data,
                progress_id=progress_id,
                history_source=history_source,
                specific_target=specific_target,
                event=event,
            )
            if early_result is not None:
                return early_result

            return await self._send_execute_share_content(
                uid=uid,
                stype=stype,
                content=content,
                news_data=news_data,
                life_ctx=life_ctx,
                period=period,
                progress_id=progress_id,
                history_source=history_source,
                event=event,
            )
        except Exception as e:
            self.services.executor_helpers.log_exception(
                f"[日常分享] 处理 {uid} 时出错", e
            )
            if event:
                await self.send_event(
                    event, event.plain_result(f"分享出错: {format_exception(e)}")
                )
            await self.services.executor_helpers.record_share_failure(
                target_id=uid,
                share_type=stype.value
                if isinstance(stype, ShareType)
                else str(stype or ""),
                message=f"分享出错: {format_exception(e)}",
                error_reason=format_exception(e),
                source_type=history_source,
            )
            if progress_id:
                self.services.progress.finish_share_progress(
                    progress_id, success=False, message="分享出错"
                )
            return False

    async def execute_share(
        self,
        force_type: ShareType | None = None,
        news_source: str | None = None,
        specific_target: str | None = None,
        event: AstrMessageEvent | None = None,
        target_scope: str = "all",
        source_type: str = "",
        exclude_custom_cron: bool | None = None,
    ) -> bool:
        """分享主流程（支持群聊私聊独立配置与记忆序列）。"""
        if self.plugin._is_terminated:
            return False

        history_source = str(
            source_type or ("command" if event else "scheduled")
        ).strip()
        if exclude_custom_cron is None:
            exclude_custom_cron = history_source in {SOURCE_SCHEDULED, SOURCE_SMART}
        targets = self.resolve_execute_share_targets(
            specific_target,
            target_scope,
            exclude_custom_cron=exclude_custom_cron,
        )
        if not targets:
            logger.warning(
                "[日常分享] 未找到可用接收对象，请填写 /sid 输出的完整会话标识。"
            )
            if event:
                await self.send_event(
                    event,
                    event.plain_result(
                        "分享失败：未配置接收对象，也没有指定当前会话目标。"
                    ),
                )
            return False

        period = self.services.executor_helpers.get_curr_period()
        abort_on_target_failure = bool(specific_target)
        r_groups = self.services.targets.parse_targets_config(
            self.receiver_conf.get("groups", []), expected_group=True
        )
        r_users = self.services.targets.parse_targets_config(
            self.receiver_conf.get("users", []), expected_group=False
        )

        total_targets = len(targets)
        any_success = False
        for target_index, uid in enumerate(targets, 1):
            if self.plugin._is_terminated:
                break
            life_ctx = await self.ctx_service.get_life_context(uid)
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
                    return False
                continue
            any_success = True
            await asyncio.sleep(2)
        return any_success

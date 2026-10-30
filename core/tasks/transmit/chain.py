from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain

from ...platformsession import create_message_session
from ...qqofficial import ensure_qq_official_background_send
from ...toolkit import format_exception
from ...submission import mark_submission
from ...readiness import wait_target_ready
from ..taskbase import TaskServiceBase
from .stage import TaskDeliveryStatusService

if TYPE_CHECKING:
    from ..runtime import TaskRuntime
    from ..taskbase import TaskConfigState, TaskSharedState


class TaskDeliveryChainService(TaskServiceBase):
    """按平台路由消息，登记阶段结果和已确认的生活回执。"""

    def __init__(
        self,
        runtime: TaskRuntime,
        config: TaskConfigState,
        state: TaskSharedState,
        *,
        status: TaskDeliveryStatusService,
    ) -> None:
        super().__init__(runtime, config, state)
        self.status = status

    async def send_message_chain(
        self, uid, chain: MessageChain, event: AstrMessageEvent | None = None
    ):
        binding = await wait_target_ready(
            self.services.targets, str(uid or "")
        )
        is_weixin = self.ctx_service.is_weixin_platform(uid)
        timeout = (
            self.services.weixin_delivery.get_send_timeout_seconds()
            if is_weixin
            else 120
        )

        if event and self.services.targets.event_matches_target(event, str(uid)):
            await mark_submission()
            await asyncio.wait_for(self.send_event(event, chain), timeout=timeout)
            await mark_submission("completed")
            return

        ensure_qq_official_background_send(binding, str(uid))

        if binding.shared_id:
            parsed = self.ctx_service.parse_umo(str(uid or ""))
            if not parsed or not parsed[1]:
                raise RuntimeError(f"目标会话格式无效: {uid}")
            message_type = (
                "GroupMessage"
                if self.ctx_service.is_group_chat(uid)
                else "FriendMessage"
            )
            session = create_message_session(
                binding.platform_id, message_type, parsed[1]
            )
            await mark_submission()
            await asyncio.wait_for(
                binding.instance.send_by_session(session, chain),
                timeout=timeout,
            )
            await mark_submission("completed")
            return

        await mark_submission()
        sent = await asyncio.wait_for(
            self.plugin.context.send_message(uid, chain), timeout=timeout
        )
        if not sent:
            raise RuntimeError(f"未找到目标平台实例或消息未发送: {uid}")
        await mark_submission("completed")

    def _is_probable_delivery_timeout(self, error: Exception) -> bool:
        detail = f"{type(error).__name__}: {error}".lower()
        if "timeout" not in detail:
            return False
        return any(
            marker in detail
            for marker in (
                "retcode=1200",
                "retcode': 1200",
                '"retcode": 1200',
                "sendmsg",
                "ntevent",
            )
        )

    async def send_chain_stage(
        self,
        uid,
        chain: MessageChain,
        stage: str,
        event: AstrMessageEvent | None = None,
        media_result: dict | None = None,
    ) -> bool:
        try:
            await self.send_message_chain(uid, chain, event)
            self.status.mark_send_stage_success(media_result, stage)
            sent_at = time.time()
            if isinstance(media_result, dict):
                media_result[f"{stage}_sent_at"] = sent_at
            # 回传失败不改变已发送事实，更不能触发平台重发。
            try:
                bridge = getattr(self.plugin, "daily_life_bridge", None)
                record = getattr(bridge, "record_delivery", None)
                kinds = tuple(
                    kind
                    for kind in ("image", "video")
                    if stage == kind
                    or any(
                        type(component).__name__.lower() == kind
                        for component in getattr(chain, "chain", [])
                    )
                )
                if callable(record):
                    await record(str(uid), sent_at, media_kinds=kinds)
            except Exception as exc:
                logger.warning(
                    f"[日常分享] 已发送，生活回执暂未登记：{type(exc).__name__}"
                )
            return True
        except Exception as error:
            if self._is_probable_delivery_timeout(error):
                self.status.record_send_stage_error(
                    media_result,
                    stage,
                    error,
                    probable_sent=True,
                )
                self.status.mark_send_stage_success(
                    media_result,
                    stage,
                    probable_sent=True,
                )
                logger.warning(
                    f"[日常分享] {self.status.send_stage_label(stage)}发送回执超时，消息可能已送达，继续后续流程: {format_exception(error)}"
                )
                return True
            self.status.record_send_stage_error(media_result, stage, error)
            raise

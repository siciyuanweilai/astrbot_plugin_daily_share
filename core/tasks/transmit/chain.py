from __future__ import annotations

import asyncio

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain

from ...platformsession import create_message_session
from ...toolkit import format_exception
from .pause import TaskDeliveryDelayService


class TaskDeliveryChainService(TaskDeliveryDelayService):
    async def send_message_chain(
        self, uid, chain: MessageChain, event: AstrMessageEvent | None = None
    ):
        binding = self.services.targets.ensure_target_platform_routable(str(uid or ""))
        is_weixin = self.ctx_service.is_weixin_platform(uid)
        timeout = (
            self.services.weixin_delivery.get_send_timeout_seconds()
            if is_weixin
            else 120
        )

        if event:
            await asyncio.wait_for(self.send_event(event, chain), timeout=timeout)
            return

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
            await asyncio.wait_for(
                binding.instance.send_by_session(session, chain),
                timeout=timeout,
            )
            return

        sent = await asyncio.wait_for(
            self.plugin.context.send_message(uid, chain), timeout=timeout
        )
        if not sent:
            raise RuntimeError(f"未找到目标平台实例或消息未发送: {uid}")

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

    async def _send_chain_stage(
        self,
        uid,
        chain: MessageChain,
        stage: str,
        event: AstrMessageEvent | None = None,
        media_result: dict | None = None,
    ) -> bool:
        try:
            await self.send_message_chain(uid, chain, event)
            self._mark_send_stage_success(media_result, stage)
            return True
        except Exception as error:
            if self._is_probable_delivery_timeout(error):
                self._record_send_stage_error(
                    media_result,
                    stage,
                    error,
                    probable_sent=True,
                )
                self._mark_send_stage_success(
                    media_result,
                    stage,
                    probable_sent=True,
                )
                logger.warning(
                    f"[日常分享] {self._send_stage_label(stage)}发送回执超时，消息可能已送达，继续后续流程: {format_exception(error)}"
                )
                return True
            self._record_send_stage_error(media_result, stage, error)
            raise

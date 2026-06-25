from __future__ import annotations

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain

from ...toolkit import format_exception


class TaskDeliveryChainMixin:
    async def _send_message_chain(self, uid, chain: MessageChain, event: AstrMessageEvent = None):
        if self.ctx_service._is_weixin_platform(uid):
            self._apply_weixin_timeout(getattr(event, "platform", None) if event else None)

        if event:
            await event.send(chain)
            return

        platform_inst = self._select_platform_instance_for_target(uid)
        session = self._build_message_session_for_target(uid, platform_inst)
        if platform_inst and session:
            if self.ctx_service._is_weixin_platform(uid):
                self._apply_weixin_timeout(platform_inst)
            if self.ctx_service._is_weixin_platform(uid) and not self._has_weixin_context_token(uid, platform_inst):
                logger.warning(
                    f"[每日分享] 个人微信平台主动发送目标 {uid} 暂无上下文令牌。"
                    "需要个人微信私聊发一条消息，收到后会保存上下文令牌。"
                )
            await platform_inst.send_by_session(session, chain)
            return

        await self.plugin.context.send_message(uid, chain)

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
        event: AstrMessageEvent = None,
        media_result: dict = None,
    ) -> bool:
        try:
            await self._send_message_chain(uid, chain, event)
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
                    f"[每日分享] {self._send_stage_label(stage)}发送回执超时，消息可能已送达，继续后续流程: {format_exception(error)}"
                )
                return True
            self._record_send_stage_error(media_result, stage, error)
            raise

import asyncio
import json

from .contextbase import ContextComponent
from .shared import (
    DAILY_SHARE_MEMORY_PROMPT,
    DAILY_SHARE_SOURCE,
    logger,
)


class ContextMemoryService(ContextComponent):
    def _clean_share_text_for_memory(self, content: str) -> str:
        return str(content or "").strip()

    async def _conversation_history_list(self, conversation) -> list:
        raw = getattr(conversation, "history", []) if conversation else []
        if isinstance(raw, str):
            try:
                raw = await asyncio.to_thread(json.loads, raw or "[]")
            except json.JSONDecodeError:
                return []
        return list(raw) if isinstance(raw, list) else []

    async def record_bot_reply_to_history(
        self, target_umo: str, content: str, image_desc: str | None = None
    ):
        if not target_umo:
            return

        final_parts = []
        clean_content = self._clean_share_text_for_memory(content)
        if clean_content:
            final_parts.append(clean_content)
        if image_desc:
            final_parts.append(f"[发送了一张配图: {image_desc}]")

        final_content = "\n\n".join(final_parts).strip()
        if not final_content:
            return

        try:
            conv_manager = self.context.conversation_manager
            get_curr = conv_manager.get_curr_conversation_id
            get_conversation = conv_manager.get_conversation
            update_conversation = conv_manager.update_conversation

            conversation_id = await get_curr(target_umo)
            if not conversation_id:
                conversation_id = await conv_manager.new_conversation(target_umo)

            conversation = await get_conversation(target_umo, conversation_id)
            history = await self._conversation_history_list(conversation)
            history.append(
                {
                    "role": "assistant",
                    "content": final_content,
                    "source": DAILY_SHARE_SOURCE,
                }
            )

            await update_conversation(target_umo, conversation_id, history=history)
            logger.debug(f"[上下文] 已写入分享历史: {target_umo}")

        except Exception as e:
            logger.warning(f"[上下文] 写入对话历史失败: {e}")

    async def record_external_share(
        self,
        target_umo: str,
        content: str,
        image_desc: str | None = None,
        *,
        image_sent: bool = False,
        media_kind: str = "",
    ) -> bool:
        description = (
            str(image_desc or "").strip()
            if self.image_conf.get("record_image_description", True)
            else ""
        )
        recorded = await self.service.daily_life_bridge.record_external_activity(
            target_umo,
            content,
            image_description=description,
            image_sent=image_sent,
            media_kind=media_kind,
            reason=DAILY_SHARE_MEMORY_PROMPT,
            sync_memory=bool(self.memory_conf.get("record_share_to_memory", True)),
        )
        if recorded:
            logger.debug(f"[上下文] 已向生活插件回传主动分享: {target_umo}")
        return recorded

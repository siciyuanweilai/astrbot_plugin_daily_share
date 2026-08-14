from __future__ import annotations

import asyncio

from ..contextbase import ContextComponent
from ..shared import DAILY_SHARE_SOURCE, Any, Dict, json, logger


class ContextHistoryConversationFetchService(ContextComponent):
    """读取会话历史。"""

    async def _get_conversation_history_data(
        self, target_umo: str, is_group: bool | None = None
    ) -> Dict[str, Any]:
        """读取已保存的会话历史，用于个人微信不支持主动拉取历史的平台。"""
        if is_group is None:
            is_group = self.is_group_chat(target_umo)

        conv_manager = self.context.conversation_manager

        try:
            conversation_id = await conv_manager.get_curr_conversation_id(target_umo)
            if not conversation_id:
                return {}
            conversation = await conv_manager.get_conversation(
                target_umo, conversation_id
            )
            if not conversation:
                return {}

            history = await self._conversation_history_list(conversation)
            if not isinstance(history, list):
                return {}

            max_count = self._get_history_max_count(is_group)
            if max_count <= 0:
                return {}

            messages = [
                message
                for item in history[-max_count:]
                if (message := self._normalize_conversation_history_item(item))
            ]

            if not messages:
                return {}

            result = {"messages": messages, "is_group": is_group}
            if is_group:
                analysis_messages = [
                    msg for msg in messages if msg.get("source") != DAILY_SHARE_SOURCE
                ]
                result["group_info"] = self._analyze_group_chat(analysis_messages)
            logger.debug(
                f"[日常分享] 已读取会话历史: {target_umo} ({len(messages)} 条)"
            )
            return result
        except Exception as e:
            logger.warning(f"[日常分享] 读取会话历史失败: {e}")
            return {}

    @staticmethod
    async def _conversation_history_list(conversation):
        history_raw = getattr(conversation, "history", "[]")
        if isinstance(history_raw, list):
            return history_raw
        try:
            return await asyncio.to_thread(json.loads, history_raw or "[]")
        except json.JSONDecodeError as exc:
            logger.debug(f"[日常分享] 会话历史结构化数据解析失败: {exc}")
            return []

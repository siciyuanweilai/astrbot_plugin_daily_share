from __future__ import annotations

from ..shared import DAILY_SHARE_SOURCE, Any, Dict, json, logger


class ContextHistoryConversationFetchMixin:
    """读取 AstrBot 会话历史。"""

    async def _get_conversation_history_data(self, target_umo: str, is_group: bool = None) -> Dict[str, Any]:
        """读取 AstrBot 已保存的会话历史，用于个人微信不支持主动拉取历史的平台。"""
        if is_group is None:
            is_group = self._is_group_chat(target_umo)

        conv_manager = getattr(self.context, "conversation_manager", None)
        if not conv_manager:
            return {}

        try:
            conversation_id = await conv_manager.get_curr_conversation_id(target_umo)
            if not conversation_id:
                return {}
            conversation = await conv_manager.get_conversation(target_umo, conversation_id)
            if not conversation:
                return {}

            history_raw = getattr(conversation, "history", "[]")
            if isinstance(history_raw, list):
                history = history_raw
            else:
                try:
                    history = json.loads(history_raw or "[]")
                except json.JSONDecodeError as e:
                    logger.debug(f"[每日分享] 会话历史结构化数据解析失败: {e}")
                    history = []

            if not isinstance(history, list):
                return {}

            max_count = self._get_history_max_count(is_group)
            if max_count <= 0:
                return {}

            messages = []
            next_assistant_is_daily_share = False
            history_window = history[-(max_count + 1):]
            for item in history_window:
                role_content = self._extract_conversation_item_role_content(item)
                if role_content and self._is_internal_share_trigger(*role_content):
                    next_assistant_is_daily_share = True
                    continue

                msg = self._normalize_conversation_history_item(item)
                if msg:
                    if next_assistant_is_daily_share:
                        if msg.get("role") == "assistant":
                            msg["source"] = DAILY_SHARE_SOURCE
                        next_assistant_is_daily_share = False
                    messages.append(msg)
            messages = messages[-max_count:]

            if not messages:
                return {}

            result = {"messages": messages, "is_group": is_group}
            if is_group:
                analysis_messages = [
                    msg for msg in messages
                    if msg.get("source") != DAILY_SHARE_SOURCE
                ]
                result["group_info"] = self._analyze_group_chat(analysis_messages)
            logger.debug(f"[每日分享] 已读取 AstrBot 会话历史: {target_umo} ({len(messages)} 条)")
            return result
        except Exception as e:
            logger.warning(f"[每日分享] 读取 AstrBot 会话历史失败: {e}")
            return {}

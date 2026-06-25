from __future__ import annotations

from ..shared import DAILY_SHARE_SOURCE, Any, Dict, logger


class ContextHistoryPlatformFetchMixin:
    """读取 AstrBot 平台消息历史。"""

    async def _get_astrbot_saved_history_data(self, target_umo: str, is_group: bool = None) -> Dict[str, Any]:
        """优先读取 AstrBot 平台消息历史；没有可用记录时再读取会话历史。"""
        platform_data = await self._get_platform_message_history_data(target_umo, is_group)
        if not platform_data:
            return await self._get_conversation_history_data(target_umo, is_group)

        if any(msg.get("role") == "assistant" for msg in platform_data.get("messages", [])):
            conversation_data = await self._get_conversation_history_data(target_umo, is_group)
            self._mark_daily_share_sources(
                platform_data.get("messages", []),
                conversation_data.get("messages", []) if conversation_data else [],
            )
            if platform_data.get("is_group"):
                analysis_messages = [
                    msg for msg in platform_data["messages"]
                    if msg.get("source") != DAILY_SHARE_SOURCE
                ]
                platform_data["group_info"] = self._analyze_group_chat(analysis_messages)

        return platform_data

    async def _get_platform_message_history_data(self, target_umo: str, is_group: bool = None) -> Dict[str, Any]:
        """读取 AstrBot 保存的平台消息记录表，用于 WebChat 等平台。"""
        if is_group is None:
            is_group = self._is_group_chat(target_umo)

        adapter_id, real_id = self._parse_umo(str(target_umo or ""))
        if not adapter_id or not real_id:
            return {}

        history_manager = getattr(self.context, "message_history_manager", None)
        get_history = getattr(history_manager, "get", None)
        if not callable(get_history):
            return {}

        max_count = self._get_history_max_count(is_group)
        if max_count <= 0:
            return {}

        try:
            records = []
            for user_id in self._get_platform_history_user_ids(adapter_id, real_id):
                records = await get_history(
                    platform_id=adapter_id,
                    user_id=user_id,
                    page=1,
                    page_size=max_count,
                )
                if records:
                    break

            messages = []
            next_assistant_is_daily_share = False
            for record in records or []:
                role_content = self._extract_platform_history_role_content(record)
                if role_content and self._is_internal_share_trigger(*role_content):
                    next_assistant_is_daily_share = True
                    continue

                msg = self._normalize_platform_history_item(record)
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
            logger.debug(f"[每日分享] 已读取 AstrBot 平台消息历史: {target_umo} ({len(messages)} 条)")
            return result
        except Exception as e:
            logger.warning(f"[每日分享] 读取 AstrBot 平台消息历史失败: {e}")
            return {}

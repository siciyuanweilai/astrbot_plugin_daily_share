from __future__ import annotations

from ..contextbase import ContextComponent
from ..shared import DAILY_SHARE_SOURCE, Any, Dict, logger


class ContextHistoryPlatformFetchService(ContextComponent):
    """读取平台消息历史。"""

    async def _get_astrbot_saved_history_data(
        self, target_umo: str, is_group: bool | None = None
    ) -> Dict[str, Any]:
        """优先读取平台消息历史；没有可用记录时再读取会话历史。"""
        platform_data = await self._get_platform_message_history_data(
            target_umo, is_group
        )
        if not platform_data:
            return await self._get_conversation_history_data(target_umo, is_group)

        if any(
            msg.get("role") == "assistant" for msg in platform_data.get("messages", [])
        ):
            conversation_data = await self._get_conversation_history_data(
                target_umo, is_group
            )
            self._mark_daily_share_sources(
                platform_data.get("messages", []),
                conversation_data.get("messages", []) if conversation_data else [],
            )
            if platform_data.get("is_group"):
                analysis_messages = [
                    msg
                    for msg in platform_data["messages"]
                    if msg.get("source") != DAILY_SHARE_SOURCE
                ]
                platform_data["group_info"] = self._analyze_group_chat(
                    analysis_messages
                )

        return platform_data

    async def _get_platform_message_history_data(
        self, target_umo: str, is_group: bool | None = None
    ) -> Dict[str, Any]:
        """读取已保存的平台消息记录表，用于 WebChat 等平台。"""
        if is_group is None:
            is_group = self.is_group_chat(target_umo)

        adapter_id, real_id = self.parse_umo(str(target_umo or ""))
        if not adapter_id or not real_id:
            return {}

        history_manager = self.context.message_history_manager

        max_count = self._get_history_max_count(is_group)
        if max_count <= 0:
            return {}

        try:
            records = await self._platform_history_records(
                history_manager, adapter_id, real_id, max_count
            )
            messages = [
                message
                for record in records
                if (message := self._normalize_platform_history_item(record))
            ][-max_count:]
            if not messages:
                return {}

            result = {"messages": messages, "is_group": is_group}
            if is_group:
                analysis_messages = [
                    msg for msg in messages if msg.get("source") != DAILY_SHARE_SOURCE
                ]
                result["group_info"] = self._analyze_group_chat(analysis_messages)
            logger.debug(
                f"[日常分享] 已读取平台消息历史: {target_umo} ({len(messages)} 条)"
            )
            return result
        except Exception as e:
            logger.warning(f"[日常分享] 读取平台消息历史失败: {e}")
            return {}

    async def _platform_history_records(
        self, history_manager, adapter_id: str, real_id: str, max_count: int
    ) -> list:
        for user_id in self._get_platform_history_user_ids(adapter_id, real_id):
            records = await history_manager.get(
                platform_id=adapter_id,
                user_id=user_id,
                page=1,
                page_size=max_count,
            )
            if records:
                return records
        return []

from __future__ import annotations

from ..shared import Any, Dict, logger


class ContextHistoryFetchRouterMixin:
    """根据平台能力选择聊天历史读取来源。"""

    async def get_history_data(self, target_umo: str, is_group: bool = None, event=None) -> Dict[str, Any]:
        """获取聊天历史记录。"""
        if not self.history_conf.get("enable_chat_history", True):
            return {}

        if is_group is None:
            is_group = self._is_group_chat(target_umo)
        adapter_id, real_id = self._parse_umo(target_umo)
        if not real_id:
            target_s = str(target_umo or "").strip()
            if target_s.isdigit():
                real_id = target_s
            else:
                logger.warning(f"[每日分享] 无法解析目标标识: {target_umo}")
                return {}

        is_onebot_target = (
            self._is_onebot_platform(adapter_id)
            or self._is_onebot_event(event)
            or (not adapter_id and str(real_id or target_umo).strip().isdigit())
        )
        if not is_onebot_target:
            return await self._get_astrbot_saved_history_data(target_umo, is_group)

        bot = self._get_onebot_bot(target_umo, event=event, adapter_id=adapter_id)
        if not bot:
            return await self._get_astrbot_saved_history_data(target_umo, is_group)
        return await self._get_onebot_history_data(target_umo, real_id, is_group, bot)

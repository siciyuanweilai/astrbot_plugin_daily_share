from __future__ import annotations

import json

from ..contextbase import ContextComponent
from ..shared import ShareType


class ContextLifeFormatService(ContextComponent):
    """按群聊/私聊目标格式化生活上下文提示。"""

    def format_life_context(
        self,
        context: str,
        share_type: ShareType,
        is_group: bool,
        group_info: dict | None = None,
    ) -> str:
        """格式化生活上下文。"""
        if not context:
            return ""
        if is_group:
            return self._format_life_context_for_group(context, share_type, group_info)
        return self._format_life_context_for_private(context, share_type)

    def _format_life_context_for_group(
        self, context: str, share_type: ShareType, group_info: dict | None = None
    ) -> str:
        """格式化群聊生活上下文。"""
        if (
            share_type == ShareType.MOOD
            and group_info
            and group_info.get("chat_intensity") == "high"
        ):
            return ""

        full_status = self._group_safe_life_status(context)
        if not full_status:
            return ""

        if share_type == ShareType.GREETING:
            return f"\n\n【你的状态】\n{full_status}\n结合天气、时段(早/晚)和状态，自然地向大家打招呼\n"
        if share_type == ShareType.NEWS:
            return f"\n\n【当前场景】\n{full_status}\n结合你当前的状态(如所处环境/休闲/天气)自然地分享新闻\n"
        if share_type in (ShareType.KNOWLEDGE, ShareType.RECOMMENDATION):
            return f"\n\n【当前场景】\n{full_status}\n结合你当前的状态来切入分享\n"
        if share_type == ShareType.MOOD:
            return f"\n\n【你的状态】\n{full_status}\n可以简单分享心情（结合天气或当前活动），但不要过于私人\n"
        return ""

    def _group_safe_life_status(self, context: str) -> str:
        try:
            data = json.loads(context)
        except (TypeError, ValueError):
            return ""
        if not isinstance(data, dict):
            return ""
        material = {}
        state = data.get("当前状态")
        if isinstance(state, dict):
            state = {
                key: state[key]
                for key in ("天气", "心情", "时段", "忙碌度", "当前实际活动")
                if isinstance(state.get(key), str) and state[key].strip()
            }
            if state:
                material["当前状态"] = state
        schedule = data.get("日程计划")
        if self.life_conf.get("group_share_schedule", False) and isinstance(
            schedule, list
        ):
            entries = [
                {
                    key: item[key]
                    for key in ("活动", "时间", "执行状态")
                    if isinstance(item.get(key), str)
                }
                for item in schedule
                if isinstance(item, dict) and isinstance(item.get("活动"), str)
            ]
            if entries:
                material["日程计划"] = entries
        return json.dumps(material, ensure_ascii=False, indent=2) if material else ""

    def _format_life_context_for_private(
        self, context: str, share_type: ShareType
    ) -> str:
        """格式化私聊生活上下文。"""
        identity_rule = self._build_people_identity_rule()

        if share_type == ShareType.GREETING:
            return f"\n\n【你的真实状态】\n{context}{identity_rule}\n"
        if share_type == ShareType.MOOD:
            return f"\n\n【你现在的状态】\n{context}{identity_rule}\n"
        if share_type == ShareType.NEWS:
            return f"\n\n【你当前真实状态】\n{context}{identity_rule}\n"
        if share_type in (ShareType.KNOWLEDGE, ShareType.RECOMMENDATION):
            return f"\n\n【你当前真实状态】\n{context}{identity_rule}\n"
        return ""

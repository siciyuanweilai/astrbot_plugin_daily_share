from __future__ import annotations

from ...prompt import build_private_recipient_identity_prompt, build_scene_consistency_rule
from ..shared import ShareType


class ContextLifeFormatMixin:
    """按群聊/私聊目标格式化生活上下文提示。"""

    def format_life_context(
        self,
        context: str,
        share_type: ShareType,
        is_group: bool,
        group_info: dict = None,
        target_info: dict = None,
    ) -> str:
        """格式化生活上下文。"""
        if not context:
            return ""
        if is_group:
            return self._format_life_context_for_group(context, share_type, group_info)
        return self._format_life_context_for_private(context, share_type, target_info)

    def _format_life_context_for_group(self, context: str, share_type: ShareType, group_info: dict = None) -> str:
        """格式化群聊生活上下文。"""
        if not self.life_conf.get("life_context_in_group", True):
            return ""

        if share_type == ShareType.MOOD and group_info and group_info.get("chat_intensity") == "high":
            return ""

        if self.life_conf.get("group_share_schedule", False):
            identity_rule = self._build_people_identity_rule()
            return f"\n\n【你的当前状态与记忆】\n{context}{identity_rule}\n(注意：这是群聊，你可以提及上述状态，但请保持自然，不要像汇报工作一样)\n"

        full_status = self._group_safe_life_status(context)

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
        lines = context.split("\n")
        weather, period, busy, curr_act, mood_str = None, None, False, None, None
        for line in lines:
            if "天气" in line or "温度" in line:
                weather = line.strip()
            elif "时段" in line:
                period = line.strip()
            elif "今日基调" in line:
                mood_str = line.strip()
            elif "今日计划" in line:
                busy = True
            elif "【当前活动】" in line:
                curr_act = line.strip()

        status_parts = []
        if weather:
            status_parts.append(weather)
        if mood_str:
            status_parts.append(mood_str)
        if period:
            status_parts.append(period)
        if curr_act:
            status_parts.append(curr_act)
        elif busy:
            status_parts.append("（今日状态：比较忙碌）")
        return "\n".join(status_parts) if status_parts else "未知"

    def _build_private_recipient_identity_rule(self, target_info: dict = None) -> str:
        if not isinstance(target_info, dict):
            return ""

        fields = []
        seen = set()
        for key, label in (
            ("nickname", "昵称/备注"),
            ("real_id", "会话标识"),
            ("target_id", "完整目标"),
        ):
            value = self._compact_life_text(target_info.get(key), 100)
            if not value or value in seen:
                continue
            fields.append(f"{label}: {value}")
            seen.add(value)

        if not fields:
            return ""

        target_text = " | ".join(fields)
        return f"\n\n{build_private_recipient_identity_prompt(target_text)}\n"

    def _format_life_context_for_private(self, context: str, share_type: ShareType, target_info: dict = None) -> str:
        """格式化私聊生活上下文。"""
        identity_rule = self._build_people_identity_rule()
        recipient_rule = self._build_private_recipient_identity_rule(target_info)

        if share_type == ShareType.GREETING:
            return (
                f"\n\n【你的真实状态】\n{context}{identity_rule}{recipient_rule}\n\n"
                f"{build_scene_consistency_rule('问候')}\n"
            )
        if share_type == ShareType.MOOD:
            return (
                f"\n\n【你现在的状态】\n{context}{identity_rule}{recipient_rule}\n\n"
                f"{build_scene_consistency_rule('分享心情')}\n"
            )
        if share_type == ShareType.NEWS:
            return (
                f"\n\n【你当前真实状态】\n{context}{identity_rule}{recipient_rule}\n\n"
                f"{build_scene_consistency_rule('分享新闻')}\n"
            )
        if share_type in (ShareType.KNOWLEDGE, ShareType.RECOMMENDATION):
            return (
                f"\n\n【你当前真实状态】\n{context}{identity_rule}{recipient_rule}\n\n"
                f"{build_scene_consistency_rule('分享内容')}\n"
            )
        return ""

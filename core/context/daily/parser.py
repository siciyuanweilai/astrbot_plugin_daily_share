from __future__ import annotations

from ..contextbase import ContextComponent
from ..shared import datetime, logger


class ContextLifeParseService(ContextComponent):
    """解析生活插件结构化数据为自然语言上下文。"""

    def _parse_life_data(self, data: dict) -> str:
        """解析生活日程插件返回的结构化数据为自然语言。"""
        try:
            parts: list[str] = []
            self._append_life_overview(parts, data)

            state_text = self._format_life_state(data.get("state", {}))
            if state_text:
                parts.append(state_text)

            availability = self._format_share_availability(data.get("subject", {}))
            if availability:
                parts.append(availability)

            rhythm = self._format_physiological_rhythm(
                data.get("state", {}).get("physiological_rhythm", {})
                if isinstance(data.get("state"), dict)
                else {}
            )
            if rhythm:
                parts.append(rhythm)

            current_activity = self._current_life_activity(data.get("timeline", []))
            if current_activity:
                parts.append(current_activity)

            self._append_life_memories(parts, data)

            guidance = self._format_share_guidance(data.get("share_guidance", {}))
            if guidance:
                parts.append(guidance)

            schedule = data.get("schedule", "")
            if schedule:
                parts.append(f"【今日完整时间轴及计划】\n{schedule}")

            return "\n\n".join(parts)
        except Exception as e:
            logger.error(f"[上下文] 解析生活数据失败: {e}")
            return str(data)

    @staticmethod
    def _append_life_overview(parts: list[str], data: dict) -> None:
        weather = data.get("weather", "")
        if weather:
            parts.append(f"【今日天气】{weather}")
        outfit = data.get("outfit", "")
        if outfit:
            parts.append(
                f"【今日穿搭】{outfit}\n"
                "（归属：主角/你本人；只用于描述你自己的外观状态，不用于日程或关系档案里的其他人。）"
            )
        labels = (
            ("theme", "主题"),
            ("mood", "心情"),
            ("style", "风格"),
            ("schedule_type", "定位"),
        )
        meta = data.get("meta", {})
        values = [f"{label}: {meta[key]}" for key, label in labels if meta.get(key)]
        if values:
            parts.append(f"【今日基调】{' | '.join(values)}")

    def _append_life_memories(self, parts: list[str], data: dict) -> None:
        memo = data.get("memo", "")
        if memo:
            parts.append(f"【今日备忘录】\n{memo}")
        records = (
            ("关系档案", self._format_relationships, "relationships"),
            ("聊天记忆摘要", self._format_chat_summaries, "chat_summaries"),
            ("地点记忆", self._format_places, "places"),
            ("近期事件", self._format_events, "events"),
            ("当前相关约定", self._format_commitments, "commitments"),
        )
        for title, formatter, key in records:
            text = formatter(data.get(key, []))
            if text:
                parts.append(f"【{title}】\n{text}")

    def _format_life_state(self, state: dict) -> str:
        if not isinstance(state, dict) or not state:
            return ""
        sleep = state.get("sleep", {})
        state_items = []
        for key, label in (
            ("energy", "体力"),
            ("busyness", "忙碌度"),
            ("social", "社交意愿"),
        ):
            value = state.get(key)
            if value is not None and value != "":
                state_items.append(f"{label}: {value}/100")
        if isinstance(sleep, dict):
            quality = sleep.get("quality")
            summary = sleep.get("summary", "")
            if quality is not None and quality != "":
                text = f"睡眠质量: {quality}/100"
                if summary:
                    text += f"（{summary}）"
                state_items.append(text)
        mood_text = state.get("mood", "")
        summary_text = state.get("summary", "")
        if mood_text:
            state_items.append(f"心情: {mood_text}")
        if summary_text:
            state_items.append(f"整体: {summary_text}")
        return f"【当前状态】{' | '.join(state_items)}" if state_items else ""

    def _format_physiological_rhythm(self, rhythm: dict) -> str:
        if not isinstance(rhythm, dict) or not rhythm:
            return ""
        items = []
        for key, label in (
            ("energy_curve", "精力节奏"),
            ("attention_state", "注意力"),
            ("summary", "状态摘要"),
        ):
            value = self._compact_life_text(rhythm.get(key), 100)
            if value:
                items.append(f"{label}: {value}")
        body = rhythm.get("body_condition", {})
        if isinstance(body, dict):
            label = self._compact_life_text(body.get("label"), 60)
            intensity = body.get("intensity")
            if label:
                suffix = (
                    f" {intensity}/100" if isinstance(intensity, (int, float)) else ""
                )
                items.append(f"身体状态: {label}{suffix}")
        social = rhythm.get("social_battery")
        if isinstance(social, (int, float)):
            items.append(f"社交电量: {social}/100")
        actions = rhythm.get("recovery_actions", [])
        if isinstance(actions, list):
            values = [
                self._compact_life_text(value, 50) for value in actions[:4] if value
            ]
            if values:
                items.append(f"恢复建议: {'、'.join(values)}")
        optional = rhythm.get("optional_cycle", {})
        if isinstance(optional, dict) and optional.get("enabled"):
            label = self._compact_life_text(optional.get("label"), 60)
            if label:
                items.append(f"可选周期状态: {label}")
        return f"【当前生理节律】{' | '.join(items)}" if items else ""

    @staticmethod
    def _format_share_availability(subject: dict) -> str:
        if not isinstance(subject, dict) or "can_interrupt_default" not in subject:
            return ""
        available = bool(subject.get("can_interrupt_default"))
        label = "适合自然地主动分享" if available else "暂不适合主动打扰"
        reason = str(subject.get("interrupt_reason") or "").strip()
        return f"【主动分享状态】{label}" + (f"（{reason}）" if reason else "")

    def _current_life_activity(self, timeline) -> str:
        if not timeline:
            return ""
        now = datetime.datetime.now()
        now_mins = now.hour * 60 + now.minute
        current_act = None
        for item in timeline:
            try:
                h, m = map(int, item.get("time", "00:00").split(":"))
                if h * 60 + m <= now_mins:
                    current_act = item
            except (TypeError, ValueError) as e:
                logger.debug(f"[日常分享] 跳过无效时间线条目 {item}: {e}")
        if not current_act:
            return ""
        return f"【当前活动】{current_act.get('activity')} (状态: {current_act.get('status', '未知')})"

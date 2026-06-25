from __future__ import annotations

from ..shared import datetime, logger


class ContextLifeParseMixin:
    """解析 daily_life JSON 数据为自然语言上下文。"""

    def _parse_life_data(self, data: dict) -> str:
        """解析生活日程插件返回的 JSON 数据为自然语言。"""
        try:
            parts = []

            weather = data.get("weather", "")
            if weather:
                parts.append(f"【今日天气】{weather}")

            outfit = data.get("outfit", "")
            if outfit:
                parts.append(
                    f"【今日穿搭】{outfit}\n"
                    "（归属：主角/你本人；只用于描述你自己的外观状态，不用于日程或关系档案里的其他人。）"
                )

            meta = data.get("meta", {})
            theme = meta.get("theme", "")
            mood = meta.get("mood", "")
            style = meta.get("style", "")
            schedule_type = meta.get("schedule_type", "")

            meta_str = []
            if theme:
                meta_str.append(f"主题: {theme}")
            if mood:
                meta_str.append(f"心情: {mood}")
            if style:
                meta_str.append(f"风格: {style}")
            if schedule_type:
                meta_str.append(f"定位: {schedule_type}")
            if meta_str:
                parts.append(f"【今日基调】{' | '.join(meta_str)}")

            state = data.get("state", {})
            state_text = self._format_life_state(state)
            if state_text:
                parts.append(state_text)

            current_activity = self._current_life_activity(data.get("timeline", []))
            if current_activity:
                parts.append(current_activity)

            memo = data.get("memo", "")
            if memo:
                parts.append(f"【今日备忘录】\n{memo}")

            memories = data.get("long_term_memory", [])
            if memories:
                parts.append(f"【你的近期记忆 (可用于丰富话题)】\n" + "\n".join(f"- {m}" for m in memories))

            for title, text in (
                ("关系档案", self._format_relationships(data.get("relationships", []))),
                ("聊天记忆摘要", self._format_chat_summaries(data.get("chat_summaries", []))),
                ("地点记忆", self._format_places(data.get("places", []))),
                ("近期事件", self._format_events(data.get("events", []))),
            ):
                if text:
                    parts.append(f"【{title}】\n{text}")

            schedule = data.get("schedule", "")
            if schedule:
                parts.append(f"【今日完整时间轴及计划】\n{schedule}")

            return "\n\n".join(parts)
        except Exception as e:
            logger.error(f"[上下文] 解析生活数据失败: {e}")
            return str(data)

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
                logger.debug(f"[每日分享] 跳过无效时间线条目 {item}: {e}")
        if not current_act:
            return ""
        return f"【当前活动】{current_act.get('activity')} (状态: {current_act.get('status', '未知')})"

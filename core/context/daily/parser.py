from __future__ import annotations

import json

from ..contextbase import ContextComponent
from ..shared import datetime, logger


class ContextLifeParseService(ContextComponent):
    """解析生活插件结构化数据为自然语言上下文。"""

    @staticmethod
    def _current_facts(data: dict) -> dict:
        value = data.get("current_facts")
        return value if isinstance(value, dict) else {}

    def _current_action(self, data: dict) -> str:
        facts = self._current_facts(data)
        if facts.get("valid") is False:
            return ""
        action = facts.get("current_action") or {}
        if not isinstance(action, dict) or not action.get("activity"):
            return ""
        label = {
            "running": "进行中",
            "paused": "已暂停，尚未完成",
            "ready": "等待结算，尚未确认完成",
            "settling": "结算中，尚未确认完成",
        }.get(action.get("status"))
        return (
            f"{self._compact_life_text(action['activity'], 240)}（{label}）"
            if label
            else ""
        )

    @staticmethod
    def _public_expression(data: dict) -> str:
        guidance = data.get("share_guidance") or {}
        expression = guidance.get("expression") if isinstance(guidance, dict) else None
        if not isinstance(expression, dict):
            return ""
        safe = {
            key: [
                " ".join(value.split())[:100]
                for value in expression.get(key, [])
                if isinstance(value, str)
            ][:4]
            for key in ("tones", "habits", "avoid")
            if isinstance(expression.get(key), list)
        }
        return (
            "【当前对象表达软偏好，仅调整语气，不公开私聊内容】\n"
            + json.dumps(safe, ensure_ascii=False)
            if any(safe.values())
            else ""
        )

    def _parse_group_life_data(self, data: dict) -> str:
        """先按字段选择群聊材料，文案与配图均不接收私人记忆。"""
        facts = {}
        if self._current_facts(data).get("valid") is False:
            return ""
        action = self._current_action(data)
        if action:
            facts["当前实际活动"] = action
        state = data.get("state")
        state = state if isinstance(state, dict) else {}
        awareness = data.get("current_awareness")
        awareness = awareness if isinstance(awareness, dict) else {}
        for label, value, limit in (
            ("天气", data.get("weather"), 120),
            ("心情", state.get("mood"), 80),
            ("时段", awareness.get("time_period"), 40),
        ):
            if isinstance(value, str) and value.strip():
                facts[label] = self._compact_life_text(value, limit)
        busyness = state.get("busyness")
        if (
            isinstance(busyness, (int, float))
            and not isinstance(busyness, bool)
            and 0 <= busyness <= 100
        ):
            facts["忙碌度"] = f"{busyness:g}/100"
        payload = {"当前状态": facts} if facts else {}

        if self.life_conf.get("group_share_schedule", False):
            schedule = []
            timeline = data.get("timeline")
            for item in timeline if isinstance(timeline, list) else []:
                if not isinstance(item, dict):
                    continue
                activity = item.get("activity")
                if not isinstance(activity, str) or not activity.strip():
                    continue
                entry = {"活动": self._compact_life_text(activity, 240)}
                time = item.get("time")
                if isinstance(time, str) and time.strip():
                    entry["时间"] = self._compact_life_text(time, 20)
                entry["执行状态"] = {
                    "planned": "计划中，尚未确认执行",
                    "active": "进行中",
                    "completed": "已完成",
                    "skipped": "已跳过",
                    "cancelled": "已取消",
                    "expired": "已过期，尚未确认执行",
                    "elapsed": "时间已过，尚未确认执行",
                }.get(str(item.get("execution_state") or ""), "尚未确认执行")
                schedule.append(entry)
            if schedule:
                payload["日程计划"] = schedule

        appearance = {}
        meta = data.get("meta")
        meta = meta if isinstance(meta, dict) else {}
        for label, value in (
            ("穿搭", data.get("outfit")),
            ("发型名称", meta.get("hair_style")),
            ("发型细节", meta.get("hair")),
            ("妆容", meta.get("makeup")),
            ("美甲", meta.get("nails")),
        ):
            if isinstance(value, str) and value.strip():
                appearance[label] = value.strip()
        if appearance:
            payload["主角本人配图外观"] = appearance
        return json.dumps(payload, ensure_ascii=False, indent=2) if payload else ""

    def _parse_qzone_post_data(self, data: dict) -> str:
        """只选当前字段，不从完整日程或私聊记忆推断已发生的事。"""
        if self._current_facts(data).get("valid") is False:
            return "【当前生活材料】居住地背景正在刷新，旧地点、天气、穿搭、心情和日程不能当作当前事实。"
        facts = {}
        weather = (
            self._compact_life_text(data.get("weather"), 120)
            if isinstance(data.get("weather"), str)
            else ""
        )
        if weather:
            facts["当前天气"] = weather
        state = data.get("state")
        if isinstance(state, dict):
            for key, label, limit in (
                ("summary", "当前状态", 240),
                ("mood", "当前心情", 80),
            ):
                value = (
                    self._compact_life_text(state.get(key), limit)
                    if isinstance(state.get(key), str)
                    else ""
                )
                if value:
                    facts[label] = value
        timeline = data.get("timeline")
        current_action = self._current_action(data)
        if current_action:
            facts["当前实际活动"] = current_action
        elif not self._current_facts(data) and isinstance(timeline, list):
            active = [
                item
                for item in timeline
                if isinstance(item, dict) and item.get("execution_state") == "active"
            ]
            if len(active) == 1:
                activity = (
                    self._compact_life_text(active[0].get("activity"), 240)
                    if isinstance(active[0].get("activity"), str)
                    else ""
                )
                if activity:
                    facts["正在进行的活动"] = activity
        if not facts:
            return ""
        return "\n".join(
            part
            for part in (
                "【当前生活材料】\n" + json.dumps(facts, ensure_ascii=False, indent=2),
                self._public_expression(data),
            )
            if part
        )

    def _parse_life_data(self, data: dict) -> str:
        """解析生活日程插件返回的结构化数据为自然语言。"""
        try:
            parts: list[str] = []
            if self._current_facts(data).get("valid") is False:
                return (
                    "【生活背景待刷新】旧地点、天气、穿搭、心情和日程不代表当前事实。"
                )
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

            current_activity = self._current_action(data)
            if current_activity:
                current_activity = "【当前实际活动】" + current_activity
            elif not self._current_facts(data):
                current_activity = self._current_life_activity(data.get("timeline", []))
            if current_activity:
                parts.append(current_activity)
            body = self._current_facts(data).get("body")
            if isinstance(body, dict) and body:
                parts.append(
                    "【已观测身体状态】"
                    + json.dumps(body, ensure_ascii=False)
                    + "；仅为身体状态，不能推断动作已完成，未观测时段不能编造经历。"
                )

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
        meta = data.get("meta", {})
        if not isinstance(meta, dict):
            meta = {}
        appearance_labels = (
            ("hair_style", "发型名称"),
            ("hair", "发型细节"),
            ("makeup", "妆容"),
            ("nails", "美甲"),
        )
        appearance = [
            f"{label}: {meta[key]}" for key, label in appearance_labels if meta.get(key)
        ]
        if appearance:
            parts.append(
                f"【当前外观】{' | '.join(appearance)}\n"
                "（归属：主角/你本人；当天动态外观优先于人设中的固定造型，不用于其他人物。）"
            )
        labels = (
            ("theme", "主题"),
            ("mood", "心情"),
            ("style", "风格"),
            ("schedule_type", "定位"),
        )
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

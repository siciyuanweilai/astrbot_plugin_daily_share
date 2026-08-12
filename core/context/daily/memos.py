from __future__ import annotations

from ..contextbase import ContextComponent


class ContextLifeMemoryService(ContextComponent):
    """格式化生活插件的记忆、关系、地点和事件数据。"""

    def _compact_life_text(self, value, limit: int = 120) -> str:
        text = str(value or "").strip()
        text = " ".join(text.split())
        return text[:limit]

    def _latest_life_item_text(self, values, limit: int) -> str:
        if not isinstance(values, list) or not values:
            return ""
        latest = values[-1]
        if isinstance(latest, dict):
            latest = latest.get("content")
        return self._compact_life_text(latest, limit)

    def _build_people_identity_rule(self) -> str:
        return (
            "\n\n【日程人物与穿搭归属规则】\n"
            "- 日程或记忆里出现其他人时，必须先对照【关系档案】中的人设线索、记忆点和最近备注原文。\n"
            "- 对方身份、关系和称谓以这些原文为准；原文没有明确写出的信息不要自行补全或改写。\n"
            "- 如果无法从原文确认身份细节，就使用名字或中性称呼，不要擅自判断。\n"
            "- 【今日穿搭】只属于主角/你本人；即使日程里出现其他人，也不得把这套穿搭套用到对方身上。\n"
        )

    def _format_relationships(self, relationships) -> str:
        if not isinstance(relationships, list):
            return ""
        lines = []
        for item in relationships[:5]:
            if not isinstance(item, dict):
                continue
            name = self._compact_life_text(
                item.get("name") or item.get("id") or "用户", 40
            )
            details = []
            persona = self._compact_life_text(item.get("persona_hint"), 90)
            point = self._latest_life_item_text(item.get("memory_points", []), 90)
            note = self._latest_life_item_text(item.get("notes", []), 80)
            if persona:
                details.append(f"人设线索：{persona}")
            if point:
                details.append(f"记忆点：{point}")
            if note:
                details.append(f"最近：{note}")
            count = item.get("interactions", 0)
            suffix = f"；{'；'.join(details)}" if details else ""
            lines.append(f"- {name}：互动 {count} 次{suffix}")
        return "\n".join(lines)

    def _format_chat_summaries(self, summaries) -> str:
        if not isinstance(summaries, list):
            return ""
        lines = []
        for item in summaries[:5]:
            if not isinstance(item, dict):
                continue
            brief = self._compact_life_text(
                item.get("brief") or item.get("long_summary"), 100
            )
            if not brief:
                continue
            date = self._compact_life_text(item.get("date"), 20)
            keywords = item.get("keywords", [])
            keyword_text = ""
            if isinstance(keywords, list) and keywords:
                keyword_text = "；关键词：" + "、".join(
                    self._compact_life_text(value, 24) for value in keywords[:5]
                )
            lines.append(f"- {date}：{brief}{keyword_text}")
        return "\n".join(lines)

    def _format_places(self, places) -> str:
        if not isinstance(places, list):
            return ""
        lines = []
        for item in places[:6]:
            if not isinstance(item, dict):
                continue
            name = self._compact_life_text(item.get("name"), 40)
            if not name:
                continue
            visits = item.get("visits", 0)
            hint = self._compact_life_text(item.get("hint") or item.get("source"), 70)
            suffix = f"；{hint}" if hint else ""
            lines.append(f"- {name}：出现 {visits} 次{suffix}")
        return "\n".join(lines)

    def _format_events(self, events) -> str:
        if not isinstance(events, list):
            return ""
        lines = []
        for item in events[:6]:
            if not isinstance(item, dict):
                continue
            summary = self._compact_life_text(
                item.get("summary") or item.get("content"), 100
            )
            if not summary:
                continue
            date = self._compact_life_text(item.get("date"), 20)
            place = self._compact_life_text(item.get("place"), 40)
            place_text = f" @ {place}" if place else ""
            lines.append(f"- {date}{place_text}：{summary}")
        return "\n".join(lines)

    def _format_commitments(self, commitments) -> str:
        if not isinstance(commitments, list):
            return ""
        lines = []
        for item in commitments[:5]:
            if not isinstance(item, dict):
                continue
            content = self._compact_life_text(item.get("content"), 100)
            if not content:
                continue
            trigger = " ".join(
                value
                for value in (
                    self._compact_life_text(item.get("trigger_date"), 20),
                    self._compact_life_text(item.get("trigger_time"), 12),
                    self._compact_life_text(item.get("time_window"), 20),
                )
                if value
            )
            lines.append(f"- {trigger + '：' if trigger else ''}{content}")
        return "\n".join(lines)

    def _format_share_guidance(self, guidance) -> str:
        if not isinstance(guidance, dict) or not guidance:
            return ""
        sections = []

        episodes = []
        for item in guidance.get("episodes", [])[:3]:
            if not isinstance(item, dict):
                continue
            title = self._compact_life_text(item.get("title"), 100)
            summary = self._compact_life_text(item.get("summary"), 180)
            if not title and not summary:
                continue
            date = self._compact_life_text(item.get("date"), 20)
            impact = self._compact_life_text(item.get("impact"), 100)
            body = "：".join(value for value in (title, summary) if value)
            suffix = f"；影响：{impact}" if impact else ""
            episodes.append(f"- {date + ' ' if date else ''}{body}{suffix}")
        if episodes:
            sections.append("【近期相关经历】\n" + "\n".join(episodes))

        rhythm_trend = self._compact_life_text(guidance.get("rhythm_trend"), 240)
        if rhythm_trend:
            sections.append(f"【近期节律趋势】{rhythm_trend}")

        focus = []
        for item in guidance.get("focus", [])[:4]:
            if not isinstance(item, dict):
                continue
            label = self._compact_life_text(item.get("label"), 80)
            reason = self._compact_life_text(item.get("reason"), 100)
            if label:
                focus.append(f"- {label}" + (f"：{reason}" if reason else ""))
        if focus:
            sections.append("【近期关注】\n" + "\n".join(focus))

        expression = guidance.get("expression", {})
        if isinstance(expression, dict):
            lines = []
            for key, label in (
                ("tones", "语气"),
                ("habits", "习惯"),
                ("avoid", "避免"),
                ("temporary", "临时状态"),
            ):
                values = expression.get(key, [])
                if not isinstance(values, list):
                    continue
                clean = [
                    self._compact_life_text(value, 100) for value in values[:4] if value
                ]
                if clean:
                    lines.append(f"- {label}：{'；'.join(clean)}")
            if lines:
                sections.append("【当前目标表达偏好】\n" + "\n".join(lines))

        behavior = []
        for item in guidance.get("behavior", [])[:4]:
            if not isinstance(item, dict):
                continue
            scene = self._compact_life_text(item.get("scene"), 80)
            preferred = self._compact_life_text(item.get("preferred"), 100)
            avoid = self._compact_life_text(item.get("avoid"), 100)
            outcome = self._compact_life_text(item.get("outcome"), 100)
            details = []
            if preferred:
                details.append(f"适合：{preferred}")
            if avoid:
                details.append(f"避免：{avoid}")
            if outcome:
                details.append(f"效果：{outcome}")
            if scene or details:
                behavior.append(
                    f"- {scene or '当前场景'}"
                    + (f"；{'；'.join(details)}" if details else "")
                )
        if behavior:
            sections.append("【互动方式建议】\n" + "\n".join(behavior))

        interaction = guidance.get("interaction", {})
        if isinstance(interaction, dict):
            summary = self._compact_life_text(interaction.get("summary"), 160)
            if summary:
                sections.append(f"【近期互动反馈】{summary}")

        terms = []
        for item in guidance.get("terms", [])[:3]:
            if not isinstance(item, dict):
                continue
            term = self._compact_life_text(item.get("term"), 50)
            meaning = self._compact_life_text(item.get("meaning"), 100)
            scene = self._compact_life_text(item.get("scene"), 70)
            if term and meaning:
                suffix = f"；场景：{scene}" if scene else ""
                terms.append(f"- {term}：{meaning}{suffix}")
        if terms:
            sections.append("【当前目标熟悉用语】\n" + "\n".join(terms))

        return "\n\n".join(sections)

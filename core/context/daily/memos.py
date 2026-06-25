from __future__ import annotations


class ContextLifeMemoryMixin:
    """格式化 daily_life 的记忆、关系、地点和事件数据。"""

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
            name = self._compact_life_text(item.get("name") or item.get("id") or "用户", 40)
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
            brief = self._compact_life_text(item.get("brief") or item.get("long_summary"), 100)
            if not brief:
                continue
            date = self._compact_life_text(item.get("date"), 20)
            keywords = item.get("keywords", [])
            keyword_text = ""
            if isinstance(keywords, list) and keywords:
                keyword_text = "；关键词：" + "、".join(self._compact_life_text(value, 24) for value in keywords[:5])
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
            summary = self._compact_life_text(item.get("summary") or item.get("content"), 100)
            if not summary:
                continue
            date = self._compact_life_text(item.get("date"), 20)
            place = self._compact_life_text(item.get("place"), 40)
            place_text = f" @ {place}" if place else ""
            lines.append(f"- {date}{place_text}：{summary}")
        return "\n".join(lines)

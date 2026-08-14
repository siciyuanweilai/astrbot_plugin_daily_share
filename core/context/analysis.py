from __future__ import annotations

from typing import Any

from .contextbase import ContextComponent
from .shared import DAILY_SHARE_SOURCE, datetime, time


class ContextHistoryAnalysisService(ContextComponent):
    def _analyze_group_chat(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        if not messages:
            return {}
        try:
            check_count = int(self.history_conf.get("group_intensity_check_count", 30))
        except Exception:
            check_count = 30

        active_window_seconds = 20 * 60
        now = time.time()
        cutoff_time = now - active_window_seconds

        active_msgs_count = 0
        user_count: dict[str, int] = {}
        topics: list[str] = []
        last_msg_time: float = 0

        consideration_msgs = (
            messages[-(check_count * 2) :]
            if len(messages) > (check_count * 2)
            else messages
        )
        for msg in consideration_msgs:
            ts = self._parse_history_timestamp(msg.get("timestamp", ""))
            if ts > last_msg_time:
                last_msg_time = ts

            if ts >= cutoff_time:
                active_msgs_count += 1
                if msg.get("role") == "user":
                    uid = str(msg.get("user_id", "unknown"))
                    user_count[uid] = user_count.get(uid, 0) + 1

                content = str(msg.get("content", "") or "").strip()
                if len(content) > 5:
                    topics.append(content[:50])

        active_users = sorted(user_count.items(), key=lambda x: x[1], reverse=True)[:3]
        threshold_high = check_count * 0.5
        threshold_medium = check_count * 0.16
        if active_msgs_count > threshold_high:
            intensity = "high"
        elif active_msgs_count > threshold_medium:
            intensity = "medium"
        else:
            intensity = "low"

        is_discussing = bool(last_msg_time > 0 and (now - last_msg_time) < 600)
        return {
            "recent_topics": topics[-5:],
            "active_users": [u for u, _c in active_users],
            "chat_intensity": intensity,
            "message_count": active_msgs_count,
            "is_discussing": is_discussing,
        }

    def _parse_history_timestamp(self, value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value or "").strip()
        if not text:
            return 0
        try:
            return float(text)
        except ValueError:
            pass
        try:
            return datetime.datetime.fromisoformat(text).timestamp()
        except ValueError:
            return 0

    def format_structured_history_context(
        self, history_data: dict[str, Any], *, limit: int = 6
    ) -> str:
        if not history_data or not history_data.get("messages"):
            return ""
        messages = history_data["messages"]
        is_group = history_data.get("is_group", False)
        flow = self._format_structured_history_flow(
            messages, is_group=is_group, limit=limit
        )
        if not flow:
            return ""
        return (
            "<structured_history>\n"
            "  <note>最近真实消息流，优先判断谁对谁说话、@、回复和媒体；不是长期记忆。</note>\n"
            f"{flow}\n"
            "</structured_history>"
        )

    def _format_structured_history_flow(
        self, messages: list[dict[str, Any]], *, is_group: bool, limit: int = 6
    ) -> str:
        if not messages:
            return ""
        lines: list[str] = []
        for msg in messages[-max(1, int(limit or 6)) :]:
            line = self._format_structured_history_line(msg, is_group=is_group)
            if line:
                lines.append(line)
        return "\n".join(lines)

    def _format_structured_history_line(
        self, msg: dict[str, Any], *, is_group: bool
    ) -> str:
        content = str(msg.get("content") or "").strip()
        if not content:
            return ""
        content = self._trim_history_text(content, 160 if is_group else 180)
        timestamp = str(msg.get("timestamp") or "").strip()
        time_text = ""
        if timestamp:
            parsed = self._parse_history_timestamp(timestamp)
            if parsed > 0:
                time_text = datetime.datetime.fromtimestamp(parsed).strftime("%H:%M")
            else:
                time_text = timestamp[:16]

        speaker = self._format_history_speaker(msg, is_group=is_group)
        meta = self._format_history_meta(msg)
        if time_text:
            prefix = f"[{time_text}] {speaker}"
        else:
            prefix = speaker
        if meta:
            prefix = f"{prefix} {meta}"
        return f"- {prefix}: {content}"

    def _format_history_speaker(self, msg: dict[str, Any], *, is_group: bool) -> str:
        role = str(msg.get("role") or "user").strip().lower()
        name = str(msg.get("name") or "").strip()
        user_id = str(msg.get("user_id") or "").strip()
        source = str(msg.get("source") or "chat").strip()
        if source == DAILY_SHARE_SOURCE and role == "assistant":
            return "你(已分享)"
        if role == "assistant" and not is_group:
            return "你"
        if role == "assistant":
            return name or user_id or "你"
        return name or user_id or "对方"

    def _format_history_meta(self, msg: dict[str, Any]) -> str:
        media = str(msg.get("media") or "").strip()
        reply_to_name = str(msg.get("reply_to_name") or "").strip()
        reply_to_id = str(msg.get("reply_to_id") or "").strip()
        at_targets = msg.get("at_targets") or []
        extras = []
        if media:
            extras.append(media)
        if reply_to_name or reply_to_id:
            extras.append(f"回复 {reply_to_name or reply_to_id}")
        if isinstance(at_targets, list) and at_targets:
            names = []
            for item in at_targets:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or item.get("user_id") or "").strip()
                if name and name not in names:
                    names.append(name)
            if names:
                extras.append("@" + "、".join(names[:3]))
        return f"({' / '.join(extras)})" if extras else ""

    @staticmethod
    def _trim_history_text(value: str, limit: int) -> str:
        text = " ".join(str(value or "").split())
        if limit > 0 and len(text) > limit:
            return text[:limit].rstrip() + "..."
        return text

    def check_group_strategy(self, group_info: dict[str, Any]) -> bool:
        if not group_info:
            return True
        strategy = self.history_conf.get("group_share_strategy", "cautious")
        is_discussing = group_info.get("is_discussing", False)
        intensity = group_info.get("chat_intensity", "low")

        if strategy == "cautious":
            if is_discussing and intensity == "high":
                return False
        elif strategy == "minimal":
            if is_discussing or intensity != "low":
                return False
        return True

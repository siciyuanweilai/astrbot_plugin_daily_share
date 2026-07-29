from __future__ import annotations

from .contextbase import ContextComponent

from .shared import DAILY_SHARE_SOURCE, Any, Dict, List, Optional, datetime


class ContextHistoryNormalizeService(ContextComponent):
    def _get_platform_history_user_ids(
        self, adapter_id: str, real_id: str
    ) -> List[str]:
        ids = []
        real_id = str(real_id or "").strip()
        if real_id:
            ids.append(real_id)

        if str(adapter_id or "").strip().lower().startswith(
            "webchat"
        ) and real_id.startswith("webchat!"):
            parts = real_id.split("!", 2)
            if len(parts) == 3 and parts[2]:
                ids.append(parts[2])

        return list(dict.fromkeys(ids))

    def _normalize_platform_history_item(self, record: Any) -> Optional[Dict[str, Any]]:
        payload = self._extract_history_payload(getattr(record, "content", None))
        content = str(payload.get("content") or "").strip()
        if not content:
            return None

        created_at = getattr(record, "created_at", None)
        try:
            if isinstance(created_at, datetime.datetime):
                ts_str = created_at.isoformat()
            elif created_at:
                ts_str = str(created_at)
            else:
                ts_str = ""
        except Exception:
            ts_str = ""

        sender_id = str(getattr(record, "sender_id", "") or "").strip()
        sender_name = str(getattr(record, "sender_name", "") or "").strip()
        content_type = ""
        record_content = getattr(record, "content", None)
        if isinstance(record_content, dict):
            content_type = str(record_content.get("type") or "").strip().lower()

        role = "assistant" if content_type in ("bot", "assistant") else "user"
        if sender_id.lower() in ("bot", "assistant"):
            role = "assistant"

        return {
            "role": role,
            "content": content,
            "timestamp": ts_str,
            "user_id": sender_id or sender_name or role,
            "name": sender_name,
            "source": "chat",
            "message_id": self._first_non_empty(
                getattr(record, "message_id", ""),
                getattr(record, "message_seq", ""),
                payload.get("message_id", ""),
            ),
            "media": str(payload.get("media") or "").strip(),
            "reply_to_id": str(payload.get("reply_to_id") or "").strip(),
            "reply_to_name": str(payload.get("reply_to_name") or "").strip(),
            "reply_to_content": str(payload.get("reply_to_content") or "").strip(),
            "at_targets": list(payload.get("at_targets") or []),
        }

    @staticmethod
    def _new_history_payload() -> Dict[str, Any]:
        return {
            "content": "",
            "message_id": "",
            "media": "",
            "reply_to_id": "",
            "reply_to_name": "",
            "reply_to_content": "",
            "at_targets": [],
        }

    @staticmethod
    def _append_history_content(payload: Dict[str, Any], text: Any) -> None:
        text = str(text or "").strip()
        if text:
            payload["content"] = (
                f"{payload['content']} {text}".strip() if payload["content"] else text
            )

    def _append_history_at_target(
        self,
        payload: Dict[str, Any],
        target_user_id: Any,
        target_name: Any,
        *,
        dedupe: bool,
    ) -> None:
        target_user_id = str(target_user_id or "").strip()
        target_name = str(target_name or "").strip()
        if not target_user_id and not target_name:
            return
        if dedupe and any(
            str(old.get("user_id") or "").strip() == target_user_id
            and str(old.get("name") or "").strip() == target_name
            for old in payload["at_targets"]
            if isinstance(old, dict)
        ):
            return
        payload["at_targets"].append(
            {"user_id": target_user_id, "name": target_name or target_user_id}
        )

    def _merge_history_payload(
        self, payload: Dict[str, Any], partial: Dict[str, Any]
    ) -> None:
        self._append_history_content(payload, partial.get("content"))

        for key in ("message_id", "reply_to_id", "reply_to_name", "reply_to_content"):
            current = str(payload.get(key) or "").strip()
            candidate = str(partial.get(key) or "").strip()
            if candidate and not current:
                payload[key] = candidate

        media = str(partial.get("media") or "").strip()
        if media:
            payload["media"] = self._merge_history_media_label(payload["media"], media)

        for item in list(partial.get("at_targets") or []):
            if isinstance(item, dict):
                self._append_history_at_target(
                    payload,
                    item.get("user_id"),
                    item.get("name"),
                    dedupe=True,
                )

    def _extract_history_nested_payload(
        self, payload: Dict[str, Any], value: Dict[str, Any]
    ) -> None:
        nested = value.get("message", value.get("content", value.get("data")))
        if isinstance(nested, (list, dict)):
            self._merge_history_payload(payload, self._extract_history_payload(nested))
        elif nested not in (None, "") and not payload["content"]:
            payload["content"] = str(nested).strip()

    def _apply_history_text_fields(
        self, payload: Dict[str, Any], value: Dict[str, Any]
    ) -> None:
        text = self._first_non_empty(value.get("text"), value.get("content"))
        if not text:
            data = value.get("data")
            if isinstance(data, dict):
                text = self._first_non_empty(data.get("text"), data.get("content"))
        self._append_history_content(payload, text)

    def _apply_history_media_kind(self, payload: Dict[str, Any], kind: str) -> None:
        media_labels = {
            "image": ("[图片]", "图片"),
            "img": ("[图片]", "图片"),
            "record": ("[语音]", "语音"),
            "audio": ("[语音]", "语音"),
            "voice": ("[语音]", "语音"),
            "video": ("[视频]", "视频"),
            "file": ("[文件]", "文件"),
        }
        placeholder, label = media_labels.get(kind, ("", ""))
        if not label:
            return
        payload["content"] = payload["content"] or placeholder
        payload["media"] = self._merge_history_media_label(payload["media"], label)

    def _apply_history_reply_fields(
        self, payload: Dict[str, Any], value: Dict[str, Any], kind: str
    ) -> None:
        if kind not in ("reply", "quote") and not any(
            key in value
            for key in (
                "reply_to",
                "replyTo",
                "message_id",
                "target_message_id",
                "target_message_content",
            )
        ):
            return

        reply_id = self._first_non_empty(
            value.get("message_id"),
            value.get("target_message_id"),
            value.get("reply_to"),
            value.get("id"),
            value.get("seq"),
            value.get("replyId"),
            value.get("reply_to_id"),
        )
        reply_name = self._first_non_empty(
            value.get("sender_name"),
            value.get("nickname"),
            value.get("name"),
            value.get("target_message_sender_nickname"),
            value.get("target_message_sender_cardname"),
        )
        reply_content = self._first_non_empty(
            value.get("target_message_content"),
            value.get("message_str"),
            value.get("content"),
            value.get("text"),
        )
        data = value.get("data")
        if isinstance(data, dict):
            reply_id = self._first_non_empty(
                reply_id, data.get("message_id"), data.get("id"), data.get("seq")
            )
            reply_name = self._first_non_empty(
                reply_name, data.get("name"), data.get("nickname")
            )
            reply_content = self._first_non_empty(
                reply_content, data.get("content"), data.get("text")
            )
        if reply_id:
            payload["reply_to_id"] = reply_id
        if reply_name:
            payload["reply_to_name"] = reply_name
        if reply_content:
            payload["reply_to_content"] = reply_content

    def _apply_history_mention_fields(
        self, payload: Dict[str, Any], value: Dict[str, Any], kind: str
    ) -> None:
        if kind not in ("at", "mention") and not any(
            key in value for key in ("target_user_id", "target_id", "qq", "user_id")
        ):
            return

        target_user_id = self._first_non_empty(
            value.get("target_user_id"),
            value.get("target_id"),
            value.get("qq"),
            value.get("user_id"),
            value.get("target"),
        )
        target_name = self._first_non_empty(
            value.get("target_user_cardname"),
            value.get("target_user_nickname"),
            value.get("target_name"),
            value.get("name"),
            value.get("nickname"),
        )
        data = value.get("data")
        if isinstance(data, dict):
            target_user_id = self._first_non_empty(
                target_user_id,
                data.get("qq"),
                data.get("user_id"),
                data.get("target_user_id"),
            )
            target_name = self._first_non_empty(
                target_name, data.get("name"), data.get("nickname"), data.get("card")
            )
        self._append_history_at_target(
            payload, target_user_id, target_name, dedupe=False
        )

    def _extract_history_payload(self, value: Any) -> Dict[str, Any]:
        payload = self._new_history_payload()

        if isinstance(value, str):
            payload["content"] = value.strip()
            return payload

        if isinstance(value, list):
            for item in value:
                self._merge_history_payload(
                    payload, self._extract_history_payload(item)
                )
            return payload

        if not isinstance(value, dict):
            text = getattr(value, "text", None)
            if text:
                payload["content"] = str(text).strip()
            return payload

        kind = str(value.get("type") or value.get("kind") or "").strip().lower()

        self._extract_history_nested_payload(payload, value)
        self._apply_history_text_fields(payload, value)
        self._apply_history_media_kind(payload, kind)
        self._apply_history_reply_fields(payload, value, kind)
        self._apply_history_mention_fields(payload, value, kind)

        return payload

    @staticmethod
    def _merge_history_media_label(existing: str, label: str) -> str:
        labels = [item for item in str(existing or "").split("·") if item]
        if label and label not in labels:
            labels.append(label)
        return "·".join(labels)

    @staticmethod
    def _first_non_empty(*values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""

    def _mark_daily_share_sources(
        self, messages: List[Dict[str, Any]], reference_messages: List[Dict[str, Any]]
    ) -> None:
        daily_contents = [
            str(msg.get("content") or "").strip()
            for msg in reference_messages
            if msg.get("source") == DAILY_SHARE_SOURCE
            and str(msg.get("content") or "").strip()
        ]
        if not daily_contents:
            return

        for msg in messages:
            if (
                msg.get("role") != "assistant"
                or msg.get("source") == DAILY_SHARE_SOURCE
            ):
                continue
            content = str(msg.get("content") or "").strip()
            if any(
                self._is_same_daily_share_content(content, ref)
                for ref in daily_contents
            ):
                msg["source"] = DAILY_SHARE_SOURCE

    def _is_same_daily_share_content(self, content: str, reference: str) -> bool:
        content = str(content or "").strip()
        reference = str(reference or "").strip()
        return bool(
            content
            and reference
            and (
                content == reference
                or content.startswith(reference)
                or reference.startswith(content)
            )
        )

    def _normalize_conversation_history_item(
        self, item: Any
    ) -> Optional[Dict[str, Any]]:
        """把框架会话历史中的不同结构归一成可用消息。"""
        if not isinstance(item, dict):
            return None

        payload = self._extract_history_payload(item.get("content", ""))
        content = str(payload.get("content") or "").strip()
        if not content:
            return None

        role = str(item.get("role") or item.get("type") or "user").lower()
        if role not in ("user", "assistant"):
            role = "assistant" if role in ("ai", "bot") else "user"

        ts = item.get("timestamp") or item.get("time")
        try:
            if isinstance(ts, (int, float)):
                ts_str = datetime.datetime.fromtimestamp(ts).isoformat()
            elif ts:
                ts_str = str(ts)
            else:
                ts_str = ""
        except Exception:
            ts_str = ""

        source = (
            DAILY_SHARE_SOURCE if item.get("source") == DAILY_SHARE_SOURCE else "chat"
        )
        message_id = self._first_non_empty(
            item.get("message_id"), item.get("id"), payload.get("message_id")
        )
        at_targets = item.get("at_targets")
        if not isinstance(at_targets, list):
            at_targets = list(payload.get("at_targets") or [])
        media = self._first_non_empty(item.get("media"), payload.get("media"))
        reply_to_id = self._first_non_empty(
            item.get("reply_to_id"), payload.get("reply_to_id")
        )
        reply_to_name = self._first_non_empty(
            item.get("reply_to_name"), payload.get("reply_to_name")
        )
        reply_to_content = self._first_non_empty(
            item.get("reply_to_content"), payload.get("reply_to_content")
        )
        talking_to = self._first_non_empty(
            item.get("talking_to"), item.get("talking_to_name")
        )

        return {
            "role": role,
            "content": content,
            "timestamp": ts_str,
            "user_id": str(item.get("user_id") or item.get("name") or role),
            "name": str(item.get("name") or ""),
            "source": source,
            "message_id": message_id,
            "media": media,
            "reply_to_id": reply_to_id,
            "reply_to_name": reply_to_name,
            "reply_to_content": reply_to_content,
            "at_targets": at_targets,
            "talking_to": talking_to,
        }

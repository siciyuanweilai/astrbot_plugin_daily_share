from __future__ import annotations

from astrbot.api import logger

from ..models import QzoneComment


class QzoneCommentUtilMixin:
    """QQ 空间评论提交与诊断的通用工具。"""

    @staticmethod
    def _payload_message(payload: dict) -> str:
        if not isinstance(payload, dict):
            return ""
        message = str(payload.get("message") or payload.get("msg") or "")
        if not message:
            return ""
        decoded = QzoneCommentUtilMixin._decode_mojibake(message)
        return decoded or message

    @staticmethod
    def _decode_mojibake(value: str) -> str:
        text = str(value or "")
        if not text:
            return ""
        candidates = [text]
        for source, target in (("latin1", "utf-8"), ("cp1252", "utf-8"), ("gbk", "utf-8")):
            try:
                decoded = text.encode(source, errors="ignore").decode(target, errors="ignore").strip()
            except Exception:
                continue
            if decoded and decoded not in candidates:
                candidates.append(decoded)

        def score(item: str) -> int:
            bad = sum(item.count(token) for token in ("锟", "�", "璇", "绌", "棿", "宸茶"))
            cjk = sum(1 for ch in item if "\u4e00" <= ch <= "\u9fff")
            return cjk - bad * 3

        return max(candidates, key=score)

    @staticmethod
    def _reply_target_unavailable(payload: dict) -> bool:
        if int((payload or {}).get("code") or 0) == -10049:
            return True
        message = str((payload or {}).get("message") or (payload or {}).get("msg") or "")
        return any(token in message for token in ("该条内容已被删除", "原文已经被删除", "无法查看"))

    @staticmethod
    def _reply_content(content: str, comment: QzoneComment) -> str:
        text = str(content or "").strip()
        if not text or text.startswith("@{"):
            return text
        uin = int(getattr(comment, "uin", 0) or 0)
        if not uin:
            return text
        nickname = str(getattr(comment, "nickname", "") or uin).strip()
        nickname = nickname.replace("}", "").replace(",", " ").strip() or str(uin)
        return f"@{{uin:{uin},nick:{nickname},auto:1}} {text}"

    def _comment_submit_ok(self, payload: dict) -> bool:
        if self._ok(payload):
            return True
        if self._write_response_without_json_ok(payload):
            logger.debug("[每日分享] QQ 空间评论接口返回内容不是结构化数据，但接口状态正常，按评论成功处理。")
            return True
        return False

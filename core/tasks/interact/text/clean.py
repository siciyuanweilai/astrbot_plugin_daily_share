from __future__ import annotations

import re
from typing import Any

_QZONE_MENTION_TAG_RE = re.compile(r"@\{[^{}]*\buin\s*:\s*\d+[^{}]*\}\s*")
_QZONE_EMPTY_GENERATION_TEXT = {"跳过", "不评论", "略过", "skip", "pass"}


def _compact_auto_comment_spacing(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return re.sub(r"(?<=[\u4e00-\u9fff，。！？、；：])\s+(?=[\u4e00-\u9fff])", "", text)


def _strip_qzone_mention_tags(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = _QZONE_MENTION_TAG_RE.sub(" ", text).strip()
    if text.startswith("@{") and "}" not in text:
        text = re.sub(r"^@\{[^}\s]*\s+", "", text).strip()
        if text.startswith("@{") and "}" not in text:
            return ""
    return _compact_auto_comment_spacing(text)


def _trim_text_utf8_bytes(text: str, max_bytes: int) -> str:
    if max_bytes <= 0 or len(text.encode("utf-8")) <= max_bytes:
        return text
    total = 0
    chars = []
    for char in text:
        size = len(char.encode("utf-8"))
        if total + size > max_bytes:
            break
        chars.append(char)
        total += size
    return "".join(chars).strip()


def _fit_auto_comment_text_bytes(text: str, max_bytes: int) -> str:
    text = _strip_qzone_mention_tags(text)
    if max_bytes <= 0 or len(text.encode("utf-8")) <= max_bytes:
        return text

    clipped = _trim_text_utf8_bytes(text, max_bytes)
    for match in reversed(list(re.finditer(r"[。！？!?；;，,、]", clipped))):
        candidate = clipped[: match.end()].strip().rstrip("，,、；;：:")
        if len(candidate) < 4:
            continue
        if candidate[-1:] not in "。！？!?":
            candidate = f"{candidate}。"
        if len(candidate.encode("utf-8")) <= max_bytes:
            return candidate

    candidate = clipped.rstrip("，,、；;：: ")
    if candidate and candidate[-1:] not in "。！？!?":
        terminal = (
            "。" if any("\u4e00" <= char <= "\u9fff" for char in candidate) else "."
        )
        with_period = f"{candidate}{terminal}"
        if len(with_period.encode("utf-8")) <= max_bytes:
            return with_period
        base = _trim_text_utf8_bytes(
            candidate, max_bytes - len(terminal.encode("utf-8"))
        ).rstrip("，,、；;：: ")
        if len(base) >= 4:
            return f"{base}{terminal}"
    return candidate


def _clean_auto_comment_text(value: Any, *, max_bytes: int = 0) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"^```(?:\w+)?\s*|\s*```$", "", text, flags=re.S).strip()
    text = text.strip("`\"'“”‘’")
    text = re.sub(
        r"^(?:评论|回复|回评|内容|评论正文|回复正文|回评正文)\s*[:：]\s*", "", text
    ).strip()
    text = text.strip("`\"'“”‘’")
    text = _strip_qzone_mention_tags(text)
    text = _compact_auto_comment_spacing(text)
    if text.lower() in _QZONE_EMPTY_GENERATION_TEXT:
        return ""
    if max_bytes > 0:
        text = _fit_auto_comment_text_bytes(text, max_bytes)
    return text

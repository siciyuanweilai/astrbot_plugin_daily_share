from __future__ import annotations

import sys
from typing import Any

from astrbot.api import logger


class QzoneVideoDebugMixin:
    VIDEO_ID_KEYS = {"sVid", "vid", "videoId", "video_id"}
    VIDEO_URL_KEYS = {
        "url",
        "video_url",
        "videourl",
        "play_url",
        "playurl",
        "download_url",
        "downloadurl",
        "raw",
        "pre",
        "url2",
        "url3",
    }

    @classmethod
    def _qzone_debug_logger(cls):
        owner = sys.modules.get(cls.__module__)
        return getattr(owner, "logger", logger)

    @classmethod
    def _first_nested_text(cls, payload: Any, keys: set[str]) -> str:
        lowered = {key.lower() for key in keys}
        for item in cls._walk_mappings(payload):
            for key, value in item.items():
                if str(key).lower() in lowered and value not in (None, ""):
                    return str(value).strip()
        return ""

    @classmethod
    def _nested_urls(cls, payload: Any) -> list[str]:
        urls: list[str] = []
        for item in cls._walk_mappings(payload):
            for key, value in item.items():
                if not isinstance(value, str):
                    continue
                text = value.strip()
                if not text.startswith(("http://", "https://")):
                    continue
                key_text = str(key).lower()
                if key_text in cls.VIDEO_URL_KEYS or "video" in key_text or text.lower().endswith((".mp4", ".mov", ".m4v")):
                    urls.append(text)
        return list(dict.fromkeys(urls))

    @staticmethod
    def _http_video_urls(values: list[str]) -> list[str]:
        urls: list[str] = []
        for value in list(dict.fromkeys(str(item or "").strip() for item in values)):
            if not value.startswith(("http://", "https://")):
                continue
            lower = value.lower()
            if (
                lower.endswith((".mp4", ".mov", ".m4v", ".webm", ".m3u8"))
                or "photovideo" in lower
                or "/video" in lower
                or "video." in lower
            ):
                urls.append(value)
        return urls

    @classmethod
    def _video_debug_key_interesting(cls, key: Any) -> bool:
        key_text = str(key or "").strip().lower()
        return bool(key_text) and any(word in key_text for word in cls.VIDEO_DEBUG_KEYWORDS)

    @classmethod
    def _video_debug_key_sensitive(cls, key: Any, value: Any = None) -> bool:
        key_text = str(key or "").strip().lower()
        if key_text == "data" and isinstance(value, (dict, list, tuple)):
            return False
        return bool(key_text) and any(word in key_text for word in cls.VIDEO_DEBUG_SENSITIVE_KEYS)

    @classmethod
    def _video_debug_value(cls, key: Any, value: Any) -> str:
        if cls._video_debug_key_sensitive(key, value):
            return "<redacted>"
        if isinstance(value, (bytes, bytearray, memoryview)):
            return f"<字节:{len(value)}>"
        if isinstance(value, dict):
            keys = ",".join(str(item) for item in list(value)[:8])
            suffix = ",..." if len(value) > 8 else ""
            return f"<字典:{len(value)} 键={keys}{suffix}>"
        if isinstance(value, (list, tuple)):
            return f"<列表:{len(value)}>"
        text = " ".join(str(value if value is not None else "").split())
        if not text:
            return "<空>"
        return text[:117] + "..." if len(text) > 120 else text

    @classmethod
    def _video_debug_shape(cls, payload: Any) -> str:
        if isinstance(payload, dict):
            keys = [str(key) for key in payload.keys()]
            preview = ",".join(keys[:12])
            suffix = ",..." if len(keys) > 12 else ""
            return f"字典({len(keys)} 个键: {preview}{suffix})"
        if isinstance(payload, (list, tuple)):
            return f"列表({len(payload)})"
        return type(payload).__name__

    @classmethod
    def _collect_video_debug_items(
        cls,
        payload: Any,
        *,
        path: str = "",
        items: list[str] | None = None,
        depth: int = 0,
    ) -> list[str]:
        items = items if items is not None else []
        if len(items) >= cls.VIDEO_DEBUG_MAX_ITEMS or depth > 10:
            return items
        if isinstance(payload, dict):
            for key, value in payload.items():
                if len(items) >= cls.VIDEO_DEBUG_MAX_ITEMS:
                    break
                key_text = str(key)
                current_path = f"{path}.{key_text}" if path else key_text
                if cls._video_debug_key_interesting(key_text):
                    items.append(f"{current_path}={cls._video_debug_value(key_text, value)}")
                if isinstance(value, (dict, list, tuple)) and not cls._video_debug_key_sensitive(key_text, value):
                    cls._collect_video_debug_items(value, path=current_path, items=items, depth=depth + 1)
        elif isinstance(payload, (list, tuple)):
            for index, value in enumerate(payload[:20]):
                if len(items) >= cls.VIDEO_DEBUG_MAX_ITEMS:
                    break
                cls._collect_video_debug_items(value, path=f"{path}[{index}]", items=items, depth=depth + 1)
        return items

    def _debug_qzone_video_payload(self, label: str, payload: Any) -> None:
        shape = self._video_debug_shape(payload)
        items = self._collect_video_debug_items(payload)
        detail = "；".join(items) if items else "未找到候选字段"
        self._qzone_debug_logger().debug(f"[每日分享] QQ 空间视频返回探针({label}): {shape}; {detail}")

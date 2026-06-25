from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import urlparse


class QzoneAlbumProbeBaseMixin:
    """相册视频公开性探测的通用解析能力。"""

    @staticmethod
    def _normalized_qzone_key(value: Any) -> str:
        return re.sub(r"[^a-z0-9]", "", str(value or "").lower())

    @staticmethod
    def _visibility_text(value: Any) -> str:
        if isinstance(value, bool) or value is None:
            return ""
        text = str(value).strip()
        return text[:-2] if text.endswith(".0") else text

    @classmethod
    def _item_contains_text(cls, value: Any, text: str, *, depth: int = 0) -> bool:
        needle = str(text or "").strip()
        if not needle or depth > 8:
            return False
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8", errors="replace")
        if isinstance(value, str):
            return needle in value
        if isinstance(value, dict):
            return any(
                cls._item_contains_text(key, needle, depth=depth + 1)
                or cls._item_contains_text(item, needle, depth=depth + 1)
                for key, item in value.items()
            )
        if isinstance(value, (list, tuple, set)):
            return any(cls._item_contains_text(item, needle, depth=depth + 1) for item in value)
        return needle in str(value or "")

    @classmethod
    def _extract_album_video_urls(cls, value: Any, *, depth: int = 0) -> list[str]:
        if depth > 8:
            return []
        urls: list[str] = []
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8", errors="replace")
        if isinstance(value, str):
            text = unescape(value).replace("\\/", "/")
            for match in re.finditer(r"https?://[^\s\"'<>]+", text, re.I):
                candidate = str(match.group(0) or "").strip().rstrip(".,)")
                if cls._http_video_urls([candidate]):
                    urls.append(candidate)
            return list(dict.fromkeys(urls))
        if isinstance(value, dict):
            for key, item in value.items():
                key_norm = cls._normalized_qzone_key(key)
                if key_norm in cls.ALBUM_URL_KEYS or isinstance(item, (dict, list, tuple, str, bytes, bytearray)):
                    urls.extend(cls._extract_album_video_urls(item, depth=depth + 1))
            return list(dict.fromkeys(urls))
        if isinstance(value, (list, tuple, set)):
            for item in value:
                urls.extend(cls._extract_album_video_urls(item, depth=depth + 1))
        return list(dict.fromkeys(urls))

    @classmethod
    def _contains_public_album_video_url(cls, value: Any) -> bool:
        for url in cls._extract_album_video_urls(value):
            host = (urlparse(url).hostname or "").lower()
            if any(marker in host for marker in cls.APPID4_PUBLIC_VIDEO_URL_MARKERS):
                return True
        return False

    @classmethod
    def _video_payload_items(cls, value: Any, *, depth: int = 0) -> list[dict[str, Any]]:
        if depth > 8:
            return []
        if isinstance(value, list):
            items: list[dict[str, Any]] = []
            for item in value:
                if isinstance(item, dict):
                    items.append(item)
                elif isinstance(item, (list, tuple)):
                    items.extend(cls._video_payload_items(item, depth=depth + 1))
            return items[:100]
        if isinstance(value, dict):
            items = []
            for key, item in value.items():
                key_norm = cls._normalized_qzone_key(key)
                if key_norm in {"data", "items", "list", "photo", "photos", "video", "videos", "videolist", "vlist"} and isinstance(
                    item,
                    (list, tuple, dict),
                ):
                    items.extend(cls._video_payload_items(item, depth=depth + 1))
                elif isinstance(item, dict):
                    if cls._item_contains_text(item, "107") or cls._contains_public_album_video_url(item):
                        items.append(item)
                    else:
                        items.extend(cls._video_payload_items(item, depth=depth + 1))
            return items[:100]
        return []

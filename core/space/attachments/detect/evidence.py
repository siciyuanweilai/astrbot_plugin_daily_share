from __future__ import annotations

import re
from typing import Any


class QzoneAlbumProbeEvidenceMixin:
    """从相册、视频接口响应中提取公开性证据。"""

    @classmethod
    def _album_video_public_evidence(cls, item: dict[str, Any]) -> dict[str, Any]:
        public_markers: list[str] = []
        non_public_markers: list[str] = []
        found_visibility_marker = False
        for mapping in cls._walk_mappings(item):
            for key, value in mapping.items():
                key_norm = cls._normalized_qzone_key(key)
                text = cls._visibility_text(value)
                if key_norm in cls.ALBUM_PUBLIC_VISIBILITY_KEYS:
                    found_visibility_marker = True
                    if text in {"0", "1"}:
                        public_markers.append(f"{key}={text}")
                    elif text:
                        non_public_markers.append(f"{key}={text}")
                elif key_norm in cls.ALBUM_PUBLIC_OWNER_KEYS:
                    found_visibility_marker = True
                    if text == "1":
                        public_markers.append(f"{key}=1")
                    elif text:
                        non_public_markers.append(f"{key}={text}")
                elif key_norm in {"videoright", "video_right"} and text:
                    found_visibility_marker = True
                    if text not in {"0", "1"}:
                        non_public_markers.append(f"{key}={text}")
        has_public_url = cls._contains_public_album_video_url(item)
        if has_public_url and not found_visibility_marker:
            public_markers.append("public_video_url=yes")
        urls = cls._extract_album_video_urls(item)
        return {
            "public": bool(has_public_url and public_markers and not non_public_markers),
            "has_public_url": has_public_url,
            "urls": urls,
            "public_markers": list(dict.fromkeys(public_markers))[:5],
            "non_public_markers": list(dict.fromkeys(non_public_markers))[:5],
        }

    @classmethod
    def _mood_log_album_name(cls, value: Any) -> bool:
        text = re.sub(r"\s+", "", str(value or ""))
        if not text:
            return False
        if "说说" in text and "日志" in text and "相册" in text:
            return True
        default_name = re.sub(r"\s+", "", str(cls.DEFAULT_VIDEO_ALBUM_NAME or ""))
        if default_name and default_name in text:
            return True
        return False

    @classmethod
    def _album_video_non_public_context_markers(cls, payload: Any) -> list[str]:
        markers: list[str] = []
        for mapping in cls._walk_mappings(payload):
            for key, value in mapping.items():
                key_norm = cls._normalized_qzone_key(key)
                text = cls._visibility_text(value)
                if key_norm in cls.ALBUM_PUBLIC_VISIBILITY_KEYS and text:
                    if text not in {"0", "1"}:
                        markers.append(f"{key}={text}")
                elif key_norm in cls.ALBUM_TITLE_KEYS and cls._mood_log_album_name(value):
                    markers.append(f"{key}=mood_log_album")
                elif key_norm == "defaultalbum" and str(value).strip().lower() in {"1", "true", "yes", "on"}:
                    markers.append(f"{key}=true")
        return list(dict.fromkeys(markers))[:8]

    @classmethod
    def _album_video_evidence_payload(cls, payload: Any, item: dict[str, Any]) -> dict[str, Any]:
        evidence: dict[str, Any] = {"item": item}
        if not isinstance(payload, dict):
            return evidence
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        for key in ("topic", "album", "albumInfo", "album_info", "photoTopic"):
            value = data.get(key) if isinstance(data, dict) else None
            if isinstance(value, dict):
                evidence[key] = value
        return evidence

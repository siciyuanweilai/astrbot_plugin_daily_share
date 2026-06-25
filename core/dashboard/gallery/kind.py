from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlparse

from ...config import ShareType
from ..common import _PAGE_IMAGE_EXTS, _PAGE_VIDEO_EXTS


class DashboardMediaKindMixin:
    def _page_media_kind_from_ref(self, ref: str) -> str:
        ref = str(ref or "").strip()
        if not ref:
            return ""
        lower = ref.lower()
        if lower.startswith("data:image/"):
            return "image"
        if lower.startswith("data:video/"):
            return "video"
        clean_ref = ref.split("?", 1)[0].split("#", 1)[0]
        mime = mimetypes.guess_type(clean_ref)[0] or ""
        if mime.startswith("image/"):
            return "image"
        if mime.startswith("video/"):
            return "video"
        suffix = Path(clean_ref).suffix.lower()
        if suffix in _PAGE_IMAGE_EXTS:
            return "image"
        if suffix in _PAGE_VIDEO_EXTS:
            return "video"
        return ""

    def _page_media_kind(self, item: dict) -> str:
        raw_type = str(item.get("media_type") or "").strip().lower()
        if "image" in raw_type:
            return "image"
        if "video" in raw_type:
            return "video"
        return (
            self._page_media_kind_from_ref(item.get("media_url", ""))
            or self._page_media_kind_from_ref(item.get("media_path", ""))
        )

    @staticmethod
    def _page_local_media_ref(ref: str) -> str:
        text = str(ref or "").strip()
        if not text:
            return ""
        lower = text.lower()
        if lower.startswith(("http://", "https://", "data:", "base64://")):
            return ""
        if lower.startswith("file://"):
            parsed = urlparse(text)
            path = unquote(parsed.path or "")
            if parsed.netloc:
                path = f"//{parsed.netloc}{path}"
            if len(path) >= 3 and path[0] == "/" and path[2] == ":":
                path = path[1:]
            return path
        return text

    @staticmethod
    def _page_dynamic_media_kind(value: str) -> str:
        raw = str(value or "all").strip().lower()
        return raw if raw in {"all", "today", "text", "image", "video"} else "all"

    @staticmethod
    def _page_dynamic_share_type(value: str) -> str:
        raw = str(value or "all").strip().lower()
        allowed = {"all", "auto", "briefing", *(item.value for item in ShareType)}
        return raw if raw in allowed else "all"

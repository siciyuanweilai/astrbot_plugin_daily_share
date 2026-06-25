from __future__ import annotations

from typing import Any

from ..models import QzoneContext


class QzoneVideoConfirmMixin:
    """视频上传后的相册动态与链接确认。"""

    async def _confirm_uploaded_album_video(
        self,
        ctx: QzoneContext,
        vid: str,
        cover_result: dict[str, Any] | None,
        *,
        submitted_at: int,
    ) -> tuple[Any, dict[str, Any]]:
        if not vid or not cover_result:
            return None, {}
        self._last_album_video_public_evidence = {}
        album_video_post = await self._confirm_album_video_public(
            ctx,
            vid,
            cover_result=cover_result,
            submitted_at=submitted_at,
        )
        return album_video_post, dict(getattr(self, "_last_album_video_public_evidence", {}) or {})

    async def _collect_uploaded_video_urls(
        self,
        ctx: QzoneContext,
        vid: str,
        upload_result: dict[str, Any],
        cover_result: dict[str, Any] | None,
    ) -> tuple[list[str], dict[str, Any]]:
        combined = {"video": upload_result, "cover": cover_result}
        urls = self._nested_urls(combined)
        library_confirm: dict[str, Any] = {}
        if vid and not self._http_video_urls(urls):
            library_confirm = await self._confirm_uploaded_video_in_library(ctx, vid)
            urls.extend(list(library_confirm.get("urls") or []) if library_confirm.get("confirmed") else [])
        return self._http_video_urls(urls), library_confirm

from __future__ import annotations

from typing import Any

from ...models import QzoneContext


class QzoneVideoCoverUploadMixin:
    """上传 QQ 空间视频封面分片。"""

    async def _upload_video_cover_chunks(
        self,
        ctx: QzoneContext,
        cover_payload: dict[str, Any],
        init: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        data = init.get("data") if isinstance(init.get("data"), dict) else {}
        if data.get("flag") == 1:
            return init
        session_id = str(data.get("session") or "").strip()
        if not session_id:
            raise RuntimeError("QQ 空间视频封面上传初始化缺少 session")
        slice_size = max(1, int(data.get("slice_size") or self.H5_UPLOAD_SLICE_SIZE))
        try:
            return await self._upload_h5_file_chunks(
                ctx,
                cover_payload,
                session_id=session_id,
                slice_size=slice_size,
                is_video=False,
                include_image_cmd=False,
                prefer_native_h2=True,
                headers=headers,
            )
        except Exception as exc:
            raise RuntimeError(self._with_h5_phase(exc, "cover-chunk")) from exc

    async def _upload_video_cover(
        self,
        ctx: QzoneContext,
        cover: Any,
        *,
        filename: str,
        vid: str,
        album_id: str,
        album_name: str,
        client_key: str = "",
        upload_time: int = 0,
        description: str = "",
        album_type_id: int | None = None,
        default_album: bool = False,
        video_size: int = 0,
        duration_ms: int = 0,
        need_feeds: int = 0,
    ) -> dict[str, Any]:
        cover_payload = await self._local_media_payload(cover, default_name="cover.jpg", label="视频封面")
        checksum, payload = self._build_video_cover_upload_payload(
            ctx,
            cover_payload,
            filename=filename,
            vid=vid,
            album_id=album_id,
            album_name=album_name,
            client_key=client_key,
            upload_time=upload_time,
            description=description,
            album_type_id=album_type_id,
            default_album=default_album,
            video_size=video_size,
            duration_ms=duration_ms,
            need_feeds=need_feeds,
        )
        cover_ctx, cover_headers, init = await self._init_video_cover_upload_with_cookie_variants(ctx, checksum, payload)
        return await self._upload_video_cover_chunks(cover_ctx, cover_payload, init, cover_headers)

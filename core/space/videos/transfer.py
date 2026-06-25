from __future__ import annotations

import time
from typing import Any

from astrbot.api import logger

from ..models import QzoneContext


class QzoneVideoUploadMixin:
    """本地视频上传主流程。"""

    async def _upload_local_video(self, ctx: QzoneContext, video: Any) -> dict[str, Any]:
        video_payload = await self._local_media_payload(video, default_name="video.mp4", label="视频")
        title = self._video_title(video, str(video_payload["filename"]))
        description = self._video_description(video)
        play_time = await self._resolve_video_play_time(video, video_payload)
        now_ms = int(time.time() * 1000)
        upload_time = now_ms // 1000
        client_key = f"{int(ctx.uin or 0)}_{now_ms}"
        logger.info(
            f"[每日分享] 正在上传 QQ 空间视频: {video_payload['filename']} ({int(video_payload['size'])} bytes)"
        )
        upload_result = await self._upload_h5_video_payload(
            ctx,
            video_payload,
            title=title,
            description=description,
            play_time=play_time,
            client_key=client_key,
            upload_time=upload_time,
        )

        vid = self._first_nested_text(upload_result, self.VIDEO_ID_KEYS)
        cover_result = None
        cover = self._video_cover(video)
        extracted_cover = ""
        if vid:
            cover, extracted_cover = await self._resolve_uploaded_video_cover(video_payload, cover)
        if vid and cover:
            try:
                cover_result = await self._upload_cover_for_uploaded_video(
                    ctx,
                    video,
                    video_payload,
                    cover,
                    vid=vid,
                    client_key=client_key,
                    upload_time=upload_time,
                    description=description,
                    play_time=play_time,
                )
            finally:
                self._cleanup_extracted_video_cover(extracted_cover)

        album_video_post, album_video_evidence = await self._confirm_uploaded_album_video(
            ctx,
            vid,
            cover_result,
            submitted_at=upload_time,
        )
        urls, library_confirm = await self._collect_uploaded_video_urls(ctx, vid, upload_result, cover_result)
        if not album_video_post:
            self._debug_qzone_video_payload("upload", upload_result)
            if cover_result is not None:
                self._debug_qzone_video_payload("cover", cover_result)
        logger.info(
            f"[每日分享] QQ 空间视频上传完成: 视频ID={vid or '未知'}，相册动态={'有' if album_video_post else '无'}"
        )
        return {
            "source": str(video_payload.get("source") or ""),
            "filename": str(video_payload["filename"]),
            "upload_result": upload_result,
            "cover_upload_result": cover_result,
            "feed_post": album_video_post,
            "album_video_evidence": album_video_evidence,
            "vid": vid,
            "client_key": client_key,
            "urls": urls,
            "library_confirm": library_confirm,
        }

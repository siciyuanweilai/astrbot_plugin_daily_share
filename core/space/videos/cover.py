from __future__ import annotations

from pathlib import Path
from typing import Any

from astrbot.api import logger

from ..models import QzoneContext


class QzoneVideoCoverUploadMixin:
    """已上传视频的封面绑定。"""

    async def _resolve_uploaded_video_cover(self, video_payload: dict[str, Any], cover: Any) -> tuple[Any, str]:
        extracted_cover = ""
        try:
            extracted_cover = await self._extract_video_cover_frame(video_payload)
        except Exception as exc:
            logger.debug(f"[每日分享] 截取 QQ 空间视频封面失败，继续使用原封面: {exc}")
        return (extracted_cover or cover), extracted_cover

    def _cleanup_extracted_video_cover(self, extracted_cover: str) -> None:
        if not extracted_cover:
            return
        try:
            Path(extracted_cover).unlink(missing_ok=True)
        except Exception as cleanup_exc:
            logger.debug(f"[每日分享] 清理 QQ 空间视频截帧封面失败: {cleanup_exc}")

    async def _upload_cover_for_uploaded_video(
        self,
        ctx: QzoneContext,
        video: Any,
        video_payload: dict[str, Any],
        cover: Any,
        *,
        vid: str,
        client_key: str,
        upload_time: int,
        description: str,
        play_time: int,
    ) -> dict[str, Any] | None:
        try:
            album = await self._qzone_album_for_video(ctx, video)
            if not album:
                logger.warning("[每日分享] QQ 空间视频已上传，但没有找到可用于封面上传的相册；将继续尝试发布文字说说。")
                return None
            cover_result = await self._upload_video_cover(
                ctx,
                cover,
                filename=str(video_payload["filename"]),
                vid=vid,
                album_id=album["id"],
                album_name=album["name"],
                client_key=client_key,
                upload_time=upload_time,
                description=description,
                album_type_id=album.get("album_type_id"),
                default_album=bool(album.get("default")),
                video_size=int(video_payload["size"]),
                duration_ms=play_time,
                need_feeds=1,
            )
            logger.info("[每日分享] QQ 空间视频封面上传完成。")
            return {
                **(cover_result if isinstance(cover_result, dict) else {}),
                "vid": vid,
            }
        except Exception as exc:
            if self._write_response_without_json_message(str(exc)):
                logger.debug(f"[每日分享] QQ 空间视频封面上传接口返回为空，继续确认相册视频动态: {exc}")
                return {"ret": 0, "vid": vid, "empty_response": True}
            logger.warning(f"[每日分享] QQ 空间视频已上传，但封面上传失败: {exc}")
            return None

from __future__ import annotations

import asyncio
import base64
from typing import Any

from astrbot.api import logger

from .attachments import QzoneLocalMediaMixin, QzoneMultipartMixin, QzoneVideoMetaMixin
from .models import QzoneContext, QzonePost
from .video import QzoneVideoMixin


class QzoneMediaUploadMixin(QzoneLocalMediaMixin, QzoneMultipartMixin, QzoneVideoMetaMixin, QzoneVideoMixin):
    async def _image_bytes(self, image) -> bytes:
        if isinstance(image, (bytes, bytearray, memoryview)):
            return bytes(image)
        text = str(image or "").strip()
        if not text:
            raise RuntimeError("QQ 空间图片为空")
        if text.startswith(("http://", "https://")):
            session = await self._http()
            async with session.get(text) as resp:
                if resp.status >= 400:
                    raise RuntimeError(f"下载 QQ 空间图片失败，接口状态码: {resp.status}")
                return await resp.read()
        if text.startswith("base64://"):
            return base64.b64decode(text.removeprefix("base64://"))
        path = Path(text)
        if path.is_file():
            return await asyncio.to_thread(path.read_bytes)
        raise RuntimeError(f"QQ 空间图片不存在: {text}")

    @staticmethod
    def _qzone_video_requires_album_dynamic(video: Any) -> bool:
        if not isinstance(video, dict):
            return False
        for key in (
            "require_album_dynamic",
            "requireAlbumDynamic",
            "qzone_require_album_dynamic",
            "qzoneRequireAlbumDynamic",
        ):
            value = video.get(key)
            if isinstance(value, bool):
                return value
            if str(value).strip().lower() in {"1", "true", "yes", "on"}:
                return True
        return False

    @staticmethod
    def _h5_token(ctx: QzoneContext) -> dict[str, Any]:
        return {"type": 4, "data": ctx.p_skey, "appid": 5}

    @staticmethod
    def _video_title(video: Any, filename: str) -> str:
        if isinstance(video, dict):
            for key in ("title", "name"):
                value = str(video.get(key) or "").strip()
                if value:
                    return value[:128]
        return filename[:128] or "video.mp4"

    @staticmethod
    def _video_description(video: Any) -> str:
        if isinstance(video, dict):
            for key in ("publish_text", "post_text", "qzone_text", "text", "content", "description", "desc"):
                value = str(video.get(key) or "").strip()
                if value:
                    return value[:512]
        return ""

    @staticmethod
    def _video_publish_text(video: Any, fallback: str = "") -> str:
        if isinstance(video, dict):
            for key in ("publish_text", "post_text", "qzone_text", "text", "content", "description", "desc"):
                value = str(video.get(key) or "").strip()
                if value:
                    return value
        return str(fallback or "").strip()

    @staticmethod
    def _video_with_publish_text(video: Any, text: str) -> Any:
        content = str(text or "").strip()
        if not content:
            return video
        if isinstance(video, dict):
            return {**video, "publish_text": content}
        return {"source": video, "publish_text": content}

    @staticmethod
    def _video_play_time(video: Any) -> int:
        if not isinstance(video, dict):
            return 0
        for key in ("duration_ms", "durationMs", "play_time", "playTime", "duration"):
            value = video.get(key)
            if value in (None, ""):
                continue
            try:
                number = int(float(value))
            except (TypeError, ValueError):
                continue
            if key == "duration" and 0 < number < 10_000:
                number *= 1000
            return max(0, number)
        return 0

    @staticmethod
    def _video_cover(video: Any) -> Any:
        if not isinstance(video, dict):
            return None
        for key in ("cover", "cover_path", "coverPath", "thumbnail", "thumb", "image"):
            value = video.get(key)
            if value not in (None, ""):
                return value
        return None

    async def _prepare_publish_videos(
        self,
        ctx: QzoneContext,
        videos: list | None,
        *,
        text: str = "",
        submitted_at: int = 0,
    ) -> tuple[list[str], list[str], QzonePost | None]:
        text_video_links: list[str] = []
        post_videos: list[str] = []
        album_video_post: QzonePost | None = None
        for video in videos or []:
            source = self._media_source(video)
            if not source:
                continue
            if source.startswith(("http://", "https://")):
                text_video_links.append(source)
                post_videos.append(source)
                continue
            upload_video = self._video_with_publish_text(video, text)
            uploaded = await self._upload_local_video(ctx, upload_video)
            uploaded_post = uploaded.get("feed_post") if isinstance(uploaded.get("feed_post"), QzonePost) else None
            if uploaded_post is not None:
                album_video_post = uploaded_post
            vid = str(uploaded.get("vid") or "").strip()
            if uploaded_post is not None:
                vid = str(uploaded.get("vid") or uploaded_post.busi_param.get("daily_share_vid") or "").strip()
                if not uploaded_post.text:
                    uploaded_post.text = text or ""
                if vid:
                    uploaded_post.busi_param = {
                        **(uploaded_post.busi_param or {}),
                        "daily_share_result_type": self.RESULT_TYPE_ALBUM_VIDEO_DYNAMIC,
                        "daily_share_vid": vid,
                    }
                album_video_post = uploaded_post
                post_videos.extend(uploaded_post.videos or [])
                logger.info("[每日分享] QQ 空间已通过公开相册发布视频动态。")
                return [], list(dict.fromkeys(post_videos)), album_video_post
            if self._qzone_video_requires_album_dynamic(video):
                raise RuntimeError(self._album_video_dynamic_failure(uploaded))
            post_videos.extend([f"qzone://video/{vid}"] if vid else [source])
            logger.warning("[每日分享] QQ 空间本地视频已上传，但未确认相册视频可公开展示；将继续发送说说。")
        return list(dict.fromkeys(text_video_links))[: self.MAX_VIDEO_LINKS], list(dict.fromkeys(post_videos)), album_video_post


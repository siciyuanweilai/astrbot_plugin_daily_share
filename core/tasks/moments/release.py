from astrbot.api import logger

from ...config import ShareType
from ...database.keys import MEDIA_IMAGE, MEDIA_TEXT, MEDIA_VIDEO, QZONE_TARGET_ID
from ...toolkit import log_exception


class TaskQzonePublishMixin:
    """QQ 空间发布与历史记录。"""

    async def _publish_qzone_best_effort(
        self,
        *,
        text: str,
        images: list,
        videos: list,
    ) -> tuple[str, bool, bool]:
        image_payloads = list(images or [])
        video_payloads = list(videos or [])
        if video_payloads:
            try:
                await self.plugin._safe_publish_qzone(text=text, images=[], videos=video_payloads)
                return MEDIA_VIDEO, False, False
            except Exception as exc:
                logger.warning("[每日分享] QQ 空间视频发布失败，继续发送说说")
                log_exception("[每日分享] QQ 空间视频发布失败详情", exc, level="debug", with_traceback=False)

        if image_payloads:
            try:
                await self.plugin._safe_publish_qzone(text=text, images=image_payloads, videos=[])
                return MEDIA_IMAGE, bool(video_payloads), False
            except Exception as exc:
                logger.warning("[每日分享] QQ 空间配图发布失败，继续发送说说")
                log_exception("[每日分享] QQ 空间配图发布失败详情", exc, level="debug", with_traceback=False)

        await self.plugin._safe_publish_qzone(text=text, images=[], videos=[])
        return MEDIA_TEXT, bool(video_payloads), bool(image_payloads)

    async def _publish_and_record_qzone_share(
        self,
        *,
        progress_id: str,
        stype: ShareType,
        content: str,
        qzone_images: list,
        qzone_videos: list,
        target_local_img: str = None,
        qzone_video_url: str = None,
        history_source: str,
    ) -> str:
        logger.info("[每日分享] 正在登录 QQ 空间...")
        self._update_share_progress(progress_id, "send", message="正在登录 QQ 空间")
        sent_media_type, video_downgraded, image_downgraded = await self._publish_qzone_best_effort(
            text=content,
            images=qzone_images,
            videos=qzone_videos,
        )
        if video_downgraded:
            self._fail_share_progress_step(progress_id, "video", "视频发布失败，继续发送")
        if image_downgraded:
            self._fail_share_progress_step(progress_id, "image", "配图发布失败，继续发送")
        logger.info("[每日分享] 成功分享内容到 QQ 空间！")

        await self._record_share_history(
            target_id=QZONE_TARGET_ID,
            share_type=stype.value,
            content=content,
            success=True,
            source_type=history_source,
            image_ref=target_local_img if sent_media_type == MEDIA_IMAGE else None,
            video_ref=qzone_video_url if sent_media_type == MEDIA_VIDEO else None,
        )
        return sent_media_type

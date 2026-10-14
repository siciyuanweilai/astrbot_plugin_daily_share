from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.api import logger

from ...config import ShareType
from ...database.keys import MEDIA_IMAGE, MEDIA_TEXT, QZONE_TARGET_ID
from ...space.errors import QzoneImageUploadError
from ...toolkit import log_exception

if TYPE_CHECKING:
    from . import TaskQzoneService


class TaskQzonePublishService:
    """QQ 空间发布与历史记录。"""

    def __init__(self, owner: TaskQzoneService) -> None:
        self.owner = owner

    async def _publish_qzone_best_effort(
        self,
        *,
        text: str,
        images: list,
    ) -> tuple[str, bool]:
        image_payloads = list(images or [])

        if image_payloads:
            try:
                await self.owner.plugin.publish_qzone(text=text, images=image_payloads)
                return MEDIA_IMAGE, False
            except QzoneImageUploadError as exc:
                logger.warning("[日常分享] QQ 空间配图上传失败，改发纯文字说说")
                log_exception(
                    "[日常分享] QQ 空间配图发布失败详情",
                    exc,
                    level="debug",
                    with_traceback=False,
                )

        await self.owner.plugin.publish_qzone(text=text, images=[])
        return MEDIA_TEXT, bool(image_payloads)

    async def _publish_and_record_qzone_share(
        self,
        *,
        progress_id: str,
        stype: ShareType,
        content: str,
        qzone_images: list,
        target_local_img: str | None = None,
        history_source: str,
        news_snapshot_data: dict | None = None,
    ) -> str:
        logger.info("[日常分享] 正在登录 QQ 空间...")
        self.owner.services.progress.update_share_progress(
            progress_id, "send", message="正在登录 QQ 空间"
        )
        sent_media_type, image_downgraded = await self.owner._publish_qzone_best_effort(
            text=content,
            images=qzone_images,
        )
        if image_downgraded:
            self.owner.services.progress.fail_share_progress_step(
                progress_id, "image", "配图发布失败，继续发送"
            )
        logger.info("[日常分享] 成功分享内容到 QQ 空间！")

        await self.owner.services.executor_helpers.records.record_share_history(
            target_id=QZONE_TARGET_ID,
            share_type=stype.value,
            content=content,
            success=True,
            source_type=history_source,
            image_ref=target_local_img if sent_media_type == MEDIA_IMAGE else None,
            news_snapshot_data=(
                news_snapshot_data if sent_media_type == MEDIA_IMAGE else None
            ),
            news_image_url=(
                target_local_img if sent_media_type == MEDIA_IMAGE else None
            ),
            degradation_reason=self.owner.services.progress.share_progress_degradation_reason(
                progress_id
            ),
        )
        return sent_media_type

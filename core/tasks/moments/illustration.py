from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ...config import ShareType
from ...constants import normalize_share_type_sequence, share_type_label
from ...database.keys import QZONE_TARGET_ID
from ...image import GeneratedImage
from ...toolkit import format_exception, log_exception
from .release import TaskQzonePublishService


class TaskQzoneMediaService(TaskQzonePublishService):
    """QQ 空间媒体生成与准备。"""

    async def _generate_qzone_image(
        self,
        *,
        stype: ShareType,
        content: str,
        life_ctx,
        news_data,
        progress_id: str,
        event: AstrMessageEvent | None = None,
    ) -> str | None:
        target_local_img = None
        enable_img_qzone = self.qzone_conf.get("qzone_enable_image", False)
        enable_img_global = self.image_conf.get("enable_ai_image", False)
        qzone_img_allowed_types = self.qzone_conf.get(
            "qzone_image_enabled_types",
            self.image_conf.get(
                "image_enabled_types", ["问候", "心情", "知识", "推荐"]
            ),
        )
        qzone_img_allowed_types = normalize_share_type_sequence(qzone_img_allowed_types)

        if enable_img_qzone and enable_img_global:
            if stype.value in qzone_img_allowed_types:
                logger.info("[日常分享] 正在为 QQ 空间生成配图...")
                self.services.progress.update_share_progress(
                    progress_id, "image", message="QQ 空间配图生成中"
                )
                try:
                    generated_image = await self.image_service.generate_image(
                        content,
                        stype,
                        life_ctx,
                        target_umo=QZONE_TARGET_ID,
                        event=event,
                    )
                    if isinstance(generated_image, GeneratedImage):
                        new_img_path = generated_image.path
                    else:
                        new_img_path = str(generated_image or "") or None
                    if new_img_path:
                        target_local_img = new_img_path
                        self.services.progress.complete_share_progress_step(
                            progress_id, "image", "配图已生成"
                        )
                    else:
                        self.services.progress.fail_share_progress_step(
                            progress_id, "image", "配图生成失败，继续发送"
                        )
                except Exception as e:
                    log_exception(
                        "[日常分享] QQ 空间配图生成失败", e, with_traceback=False
                    )
                    self.services.progress.fail_share_progress_step(
                        progress_id, "image", "配图生成失败，继续发送"
                    )
            else:
                logger.info(
                    f"[日常分享] 当前类型 {share_type_label(stype)} 不在 QQ 空间配图允许列表，跳过配图。"
                )
                self.services.progress.skip_share_progress_step(
                    progress_id, "image", "当前类型未开启配图"
                )
        else:
            self.services.progress.skip_share_progress_step(
                progress_id, "image", "配图未开启"
            )

        if (
            target_local_img
            or stype != ShareType.NEWS
            or not self.qzone_conf.get("qzone_attach_hot_news_image", True)
        ):
            return target_local_img

        try:
            if news_data:
                self.services.progress.update_share_progress(
                    progress_id, "image", message="获取新闻配图中"
                )
                img_url, _ = self.news_service.get_hot_news_image_url(news_data[1])
                target_local_img = img_url
                if target_local_img:
                    self.services.progress.complete_share_progress_step(
                        progress_id, "image", "新闻配图已获取"
                    )
        except Exception as e:
            logger.warning(f"[日常分享] QQ 空间获取新闻配图失败: {format_exception(e)}")
            self.services.progress.fail_share_progress_step(
                progress_id, "image", "新闻配图获取失败，继续发送"
            )

        return target_local_img

    async def _prepare_qzone_publish_media(
        self, *, target_local_img: str | None = None
    ) -> list:
        qzone_images: list = []
        if not target_local_img:
            return qzone_images

        prepared_image = await self.services.delivery_assets.prepare_qzone_image(
            target_local_img
        )
        if prepared_image:
            qzone_images.append(prepared_image)
        return qzone_images

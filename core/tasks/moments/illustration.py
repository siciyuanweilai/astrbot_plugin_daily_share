from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ...config import ShareType
from ...constants import normalize_share_type_sequence, share_type_label
from ...database.keys import QZONE_TARGET_ID
from ...toolkit import format_exception, log_exception


class TaskQzoneMediaMixin:
    """QQ 空间媒体生成与准备。"""

    async def _generate_qzone_image(
        self,
        *,
        stype: ShareType,
        content: str,
        life_ctx,
        news_data,
        progress_id: str,
        event: AstrMessageEvent = None,
    ) -> str | None:
        target_local_img = None
        enable_img_qzone = self.qzone_conf.get("qzone_enable_image", False)
        enable_img_global = self.image_conf.get("enable_ai_image", False)
        qzone_img_allowed_types = self.qzone_conf.get(
            "qzone_image_enabled_types",
            self.image_conf.get("image_enabled_types", ["问候", "心情", "知识", "推荐"]),
        )
        qzone_img_allowed_types = normalize_share_type_sequence(qzone_img_allowed_types)

        if enable_img_qzone and enable_img_global:
            if stype.value in qzone_img_allowed_types:
                logger.info("[每日分享] 正在为 QQ 空间生成配图...")
                self._update_share_progress(progress_id, "image", message="QQ 空间配图生成中")
                try:
                    new_img_path = await self.image_service.generate_image(
                        content,
                        stype,
                        life_ctx,
                        target_umo=QZONE_TARGET_ID,
                        event=event,
                    )
                    if new_img_path:
                        target_local_img = new_img_path
                        self._complete_share_progress_step(progress_id, "image", "配图已生成")
                    else:
                        self._fail_share_progress_step(progress_id, "image", "配图生成失败，继续发送")
                except Exception as e:
                    log_exception("[每日分享] QQ 空间配图生成失败", e, with_traceback=False)
                    self._fail_share_progress_step(progress_id, "image", "配图生成失败，继续发送")
            else:
                logger.info(f"[每日分享] 当前类型 {share_type_label(stype)} 不在 QQ 空间配图允许列表，跳过配图。")
                self._skip_share_progress_step(progress_id, "image", "当前类型未开启配图")
        else:
            self._skip_share_progress_step(progress_id, "image", "配图未开启")

        if target_local_img or stype != ShareType.NEWS or not self.qzone_conf.get("qzone_attach_hot_news_image", True):
            return target_local_img

        try:
            if news_data:
                self._update_share_progress(progress_id, "image", message="获取新闻配图中")
                img_url, _ = self.news_service.get_hot_news_image_url(news_data[1])
                target_local_img = img_url
                if target_local_img:
                    self._complete_share_progress_step(progress_id, "image", "新闻配图已获取")
                snapshot_data = await self.news_service.get_hot_news(
                    news_data[1],
                    limit=self.get_news_snapshot_limit(),
                    allow_fallback=False,
                )
                await self._cache_news_snapshot_for_targets(
                    QZONE_TARGET_ID,
                    news_data=snapshot_data,
                    source_key=news_data[1],
                    image_url=img_url,
                    event=event,
                )
        except Exception as e:
            logger.warning(f"[每日分享] QQ 空间获取新闻配图失败: {format_exception(e)}")
            self._fail_share_progress_step(progress_id, "image", "新闻配图获取失败，继续发送")

        return target_local_img

    async def _generate_qzone_video_payloads(
        self,
        *,
        stype: ShareType,
        content: str,
        target_local_img: str = None,
        progress_id: str,
        need_video: bool = False,
        event: AstrMessageEvent = None,
    ) -> tuple[list, str | None]:
        qzone_videos = []
        qzone_video_url = None
        enable_video_qzone = need_video or self.qzone_conf.get("qzone_enable_video", False)
        enable_video_global = self.image_conf.get("enable_ai_video", False)
        qzone_video_allowed_types = normalize_share_type_sequence(
            self.qzone_conf.get(
                "qzone_video_enabled_types",
                self.image_conf.get("video_enabled_types", []),
            )
        ) or ["greeting", "mood"]

        if not (enable_video_qzone and enable_video_global):
            self._skip_share_progress_step(progress_id, "video", "视频未开启")
            return qzone_videos, qzone_video_url
        if stype.value not in qzone_video_allowed_types:
            self._skip_share_progress_step(progress_id, "video", "当前类型未开启视频")
            return qzone_videos, qzone_video_url
        if not target_local_img:
            self._skip_share_progress_step(progress_id, "video", "缺少配图，跳过视频")
            return qzone_videos, qzone_video_url
        if str(target_local_img).startswith(("http://", "https://")):
            self._skip_share_progress_step(progress_id, "video", "远程配图不支持生成视频")
            return qzone_videos, qzone_video_url

        try:
            qzone_video_url = await self._generate_share_video_step(
                progress_id=progress_id,
                img_path=target_local_img,
                content=content,
                target_umo=QZONE_TARGET_ID,
                event=event,
                progress_message="QQ 空间视频生成中",
            )
            if qzone_video_url:
                qzone_videos.append(
                    {
                        "source": qzone_video_url,
                        "cover": target_local_img,
                        "title": share_type_label(stype),
                        "description": content,
                        "require_album_dynamic": True,
                    }
                )
        except Exception as e:
            log_exception("[每日分享] QQ 空间视频生成失败", e, with_traceback=False)
            self._fail_share_progress_step(progress_id, "video", "视频生成失败，继续发送")

        return qzone_videos, qzone_video_url

    async def _prepare_qzone_publish_media(self, *, target_local_img: str = None, qzone_videos: list = None) -> list:
        qzone_images = []
        qzone_videos = qzone_videos or []
        if not target_local_img:
            return qzone_images

        prepared_image = await self._prepare_qzone_image(target_local_img)
        if prepared_image:
            qzone_images.append(prepared_image)
        if qzone_videos:
            logger.info("[每日分享] QQ 空间视频和配图将分开发送，已优先发布视频载荷。")
        return qzone_images

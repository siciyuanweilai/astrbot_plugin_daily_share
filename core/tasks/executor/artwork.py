from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ...config import ShareType, TimePeriod
from ...constants import normalize_share_type_sequence, share_type_label
from .send import TaskExecutorSendService


class TaskExecutorMediaService(TaskExecutorSendService):
    """分享媒体生成。"""

    async def _generate_execute_share_media(
        self,
        *,
        progress_id: str,
        content: str,
        stype: ShareType,
        life_ctx: str,
        target_umo: str,
        event: AstrMessageEvent | None = None,
        period: TimePeriod,
        initial_img_path: str | None = None,
    ) -> tuple[str | None, str | None, str | None, str | None, str]:
        img_path = initial_img_path
        send_img_path = None
        video_url = None
        image_description = ""

        enable_img_global = self.image_conf.get("enable_ai_image", False)
        img_allowed_types = normalize_share_type_sequence(
            self.image_conf.get("image_enabled_types", ["问候", "心情", "知识", "推荐"])
        )
        if enable_img_global:
            if stype.value in img_allowed_types:
                (
                    img_path,
                    send_img_path,
                    image_description,
                ) = await self.services.executor_helpers.generate_share_image_step(
                    progress_id=progress_id,
                    content=content,
                    share_type=stype,
                    life_ctx=life_ctx,
                    target_umo=target_umo,
                    current_img_path=img_path,
                    event=event,
                )
                if img_path and self.image_conf.get("enable_ai_video", False):
                    video_allowed = normalize_share_type_sequence(
                        self.image_conf.get("video_enabled_types", ["问候", "心情"])
                    )
                    if stype.value in video_allowed:
                        video_url = await self.services.executor_helpers.generate_share_video_step(
                            progress_id=progress_id,
                            img_path=img_path,
                            content=content,
                            image_description=image_description,
                            target_umo=target_umo,
                            event=event,
                        )
                    else:
                        self.services.progress.skip_share_progress_step(
                            progress_id, "video", "当前类型未开启视频"
                        )
                else:
                    self.services.progress.skip_share_progress_step(
                        progress_id, "video", "未生成视频"
                    )
            else:
                logger.info(
                    f"[日常分享] 当前类型 {share_type_label(stype)} 不在配图允许列表，跳过配图。"
                )
                self.services.progress.skip_share_progress_step(
                    progress_id, "image", "当前类型未开启配图"
                )
                self.services.progress.skip_share_progress_step(
                    progress_id, "video", "未生成视频"
                )
        else:
            self.services.progress.skip_share_progress_step(
                progress_id, "image", "配图未开启"
            )
            self.services.progress.skip_share_progress_step(
                progress_id, "video", "视频未开启"
            )

        audio_path = None
        enable_tts_global = self.tts_conf.get("enable_tts", False)
        tts_allowed_types = normalize_share_type_sequence(
            self.tts_conf.get("tts_enabled_types", ["问候", "心情"])
        )
        if enable_tts_global:
            if stype.value in tts_allowed_types:
                audio_path = (
                    await self.services.executor_helpers.generate_share_audio_step(
                        progress_id=progress_id,
                        content=content,
                        target_umo=target_umo,
                        share_type=stype,
                        period=period,
                        event=event,
                    )
                )
            else:
                logger.info(
                    f"[日常分享] 当前类型 {share_type_label(stype)} 不在语音允许列表，跳过语音。"
                )
                self.services.progress.skip_share_progress_step(
                    progress_id, "audio", "当前类型未开启语音"
                )
        else:
            self.services.progress.skip_share_progress_step(
                progress_id, "audio", "语音未开启"
            )

        return img_path, send_img_path, video_url, audio_path, image_description

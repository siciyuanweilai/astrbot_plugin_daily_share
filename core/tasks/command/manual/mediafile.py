from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.api.event import AstrMessageEvent

from ....config import ShareType, TimePeriod
from ....integrations.mediajob import current_share_job

if TYPE_CHECKING:
    from .. import TaskCommandShareService


class TaskCommandLocalMediaService:
    def __init__(self, owner: TaskCommandShareService) -> None:
        self.owner = owner

    async def _generate_command_media(
        self,
        *,
        progress_id: str,
        content: str,
        target_type_enum: ShareType,
        life_ctx: str,
        target_umo: str,
        period: TimePeriod,
        event: AstrMessageEvent,
        img_path: str | None = None,
        need_image: bool,
        need_video: bool,
        need_voice: bool,
    ) -> tuple[str | None, str | None, str | None, str | None, str]:
        job = current_share_job.get()
        if job is not None and "prepared_media" in job:
            return tuple(job["prepared_media"])
        video_url = None
        send_img_path = img_path
        image_description = ""
        should_gen_visual = bool(
            self.owner.image_conf.get("enable_ai_image", False)
            and (need_image or need_video)
        )

        if should_gen_visual:
            (
                img_path,
                send_img_path,
                image_description,
            ) = await self.owner.services.executor_helpers.media.generate_share_image_step(
                progress_id=progress_id,
                content=content,
                share_type=target_type_enum,
                life_ctx=life_ctx,
                target_umo=target_umo,
                current_img_path=img_path,
                event=event,
            )
            video_url = await self.owner._generate_command_video(
                progress_id=progress_id,
                content=content,
                target_umo=target_umo,
                event=event,
                img_path=img_path,
                image_description=image_description,
                need_video=need_video,
            )
        else:
            self.owner.services.progress.skip_share_progress_step(
                progress_id, "image", "未请求配图"
            )
            self.owner.services.progress.skip_share_progress_step(
                progress_id, "video", "未请求视频"
            )

        audio_path = await self.owner._generate_command_audio(
            progress_id=progress_id,
            content=content,
            target_umo=target_umo,
            share_type=target_type_enum,
            period=period,
            event=event,
            need_voice=need_voice,
        )
        media = img_path, send_img_path, video_url, audio_path, image_description
        if job is not None:
            job["prepared_media"] = list(media)
            await job["service"].save(job)
        return media

    async def _generate_command_video(
        self,
        *,
        progress_id: str,
        content: str,
        target_umo: str,
        event: AstrMessageEvent,
        img_path: str | None,
        image_description: str,
        need_video: bool,
    ) -> str | None:
        if not need_video:
            self.owner.services.progress.skip_share_progress_step(
                progress_id, "video", "未请求视频"
            )
            return None
        if img_path and self.owner.image_conf.get("enable_ai_video", False):
            return await self.owner.services.executor_helpers.media.generate_share_video_step(
                progress_id=progress_id,
                img_path=img_path,
                content=content,
                image_description=image_description,
                target_umo=target_umo,
                event=event,
            )
        if not img_path:
            self.owner.services.progress.skip_share_progress_step(
                progress_id, "video", "缺少配图，跳过视频"
            )
        else:
            self.owner.services.progress.skip_share_progress_step(
                progress_id, "video", "视频未开启"
            )
        return None

    async def _generate_command_audio(
        self,
        *,
        progress_id: str,
        content: str,
        target_umo: str,
        share_type: ShareType,
        period: TimePeriod,
        event: AstrMessageEvent,
        need_voice: bool,
    ) -> str | None:
        if not self.owner.tts_conf.get("enable_tts", False):
            self.owner.services.progress.skip_share_progress_step(
                progress_id, "audio", "语音未开启"
            )
            return None
        if not need_voice:
            self.owner.services.progress.skip_share_progress_step(
                progress_id, "audio", "未请求语音"
            )
            return None
        return (
            await self.owner.services.executor_helpers.media.generate_share_audio_step(
                progress_id=progress_id,
                content=content,
                target_umo=target_umo,
                share_type=share_type,
                period=period,
                event=event,
            )
        )

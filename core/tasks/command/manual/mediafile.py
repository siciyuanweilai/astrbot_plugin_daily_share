from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from ....config import ShareType


class TaskCommandLocalMediaMixin:
    async def _generate_command_media(
        self,
        *,
        progress_id: str,
        content: str,
        target_type_enum: ShareType,
        life_ctx: str,
        target_umo: str,
        period: str,
        event: AstrMessageEvent,
        img_path: str = None,
        need_image: bool,
        need_video: bool,
        need_voice: bool,
    ) -> tuple[str | None, str | None, str | None, str | None]:
        video_url = None
        send_img_path = img_path
        should_gen_visual = bool(self.image_conf.get("enable_ai_image", False) and (need_image or need_video))

        if should_gen_visual:
            img_path, send_img_path = await self._generate_share_image_step(
                progress_id=progress_id,
                content=content,
                share_type=target_type_enum,
                life_ctx=life_ctx,
                target_umo=target_umo,
                current_img_path=img_path,
                event=event,
            )
            video_url = await self._generate_command_video(
                progress_id=progress_id,
                content=content,
                target_umo=target_umo,
                event=event,
                img_path=img_path,
                need_video=need_video,
            )
        else:
            self._skip_share_progress_step(progress_id, "image", "未请求配图")
            self._skip_share_progress_step(progress_id, "video", "未请求视频")

        audio_path = await self._generate_command_audio(
            progress_id=progress_id,
            content=content,
            target_umo=target_umo,
            share_type=target_type_enum,
            period=period,
            event=event,
            need_voice=need_voice,
        )
        return img_path, send_img_path, video_url, audio_path

    async def _generate_command_video(
        self,
        *,
        progress_id: str,
        content: str,
        target_umo: str,
        event: AstrMessageEvent,
        img_path: str,
        need_video: bool,
    ) -> str | None:
        if not need_video:
            self._skip_share_progress_step(progress_id, "video", "未请求视频")
            return None
        if img_path and self.image_conf.get("enable_ai_video", False):
            return await self._generate_share_video_step(
                progress_id=progress_id,
                img_path=img_path,
                content=content,
                target_umo=target_umo,
                event=event,
            )
        if not img_path:
            self._skip_share_progress_step(progress_id, "video", "缺少配图，跳过视频")
        else:
            self._skip_share_progress_step(progress_id, "video", "视频未开启")
        return None

    async def _generate_command_audio(
        self,
        *,
        progress_id: str,
        content: str,
        target_umo: str,
        share_type: ShareType,
        period: str,
        event: AstrMessageEvent,
        need_voice: bool,
    ) -> str | None:
        if not self.tts_conf.get("enable_tts", False):
            self._skip_share_progress_step(progress_id, "audio", "语音未开启")
            return None
        if not need_voice:
            self._skip_share_progress_step(progress_id, "audio", "未请求语音")
            return None
        return await self._generate_share_audio_step(
            progress_id=progress_id,
            content=content,
            target_umo=target_umo,
            share_type=share_type,
            period=period,
            event=event,
        )

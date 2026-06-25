from astrbot.api.event import AstrMessageEvent


class TaskHelperMediaMixin:
    """分享媒体生成步骤辅助。"""

    async def _generate_share_image_step(
        self,
        *,
        progress_id: str,
        content: str,
        share_type,
        life_ctx: str,
        target_umo: str,
        current_img_path: str = None,
        event: AstrMessageEvent = None,
        progress_message: str = "配图生成中",
        fail_message: str = "配图生成失败，继续发送文案",
    ) -> tuple[str, str]:
        self._update_share_progress(progress_id, "image", message=progress_message)
        img_path = current_img_path
        ai_img_path = await self.image_service.generate_image(
            content,
            share_type,
            life_ctx,
            target_umo=target_umo,
            event=event,
        )
        if ai_img_path:
            img_path = ai_img_path
            self._complete_share_progress_step(progress_id, "image", "配图已生成")
        else:
            self._fail_share_progress_step(progress_id, "image", fail_message)

        send_img_path = await self._prepare_image_for_target(target_umo, img_path) if img_path else None
        return img_path, send_img_path

    async def _generate_share_video_step(
        self,
        *,
        progress_id: str,
        img_path: str,
        content: str,
        target_umo: str,
        event: AstrMessageEvent = None,
        progress_message: str = "视频生成中",
    ) -> str:
        self._update_share_progress(progress_id, "video", message=progress_message)
        video_url = await self.image_service.generate_video_from_image(
            img_path,
            content,
            target_umo=target_umo,
            event=event,
        )
        if video_url:
            self._complete_share_progress_step(progress_id, "video", "视频已生成")
        else:
            self._fail_share_progress_step(progress_id, "video", "视频生成失败，继续发送")
        return video_url

    async def _generate_share_audio_step(
        self,
        *,
        progress_id: str,
        content: str,
        target_umo: str,
        share_type,
        period,
        event: AstrMessageEvent = None,
        progress_message: str = "语音生成中",
    ) -> str:
        self._update_share_progress(progress_id, "audio", message=progress_message)
        audio_path = await self.ctx_service.text_to_speech(
            content,
            target_umo,
            share_type,
            period,
            event=event,
        )
        if audio_path:
            self._complete_share_progress_step(progress_id, "audio", "语音已生成")
        else:
            self._fail_share_progress_step(progress_id, "audio", "语音生成失败，继续发送")
        return audio_path

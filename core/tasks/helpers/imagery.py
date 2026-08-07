from astrbot.api.event import AstrMessageEvent

from ...image import GeneratedImage
from .sync import TaskHelperSyncService


class TaskHelperMediaService(TaskHelperSyncService):
    """分享媒体生成步骤辅助。"""

    def _media_failure_message(self, media_kind: str, default: str) -> str:
        bridge = getattr(self.plugin, "daily_life_bridge", None)
        media_result = getattr(bridge, "media_result", None)
        if callable(media_result):
            status, reason = media_result(media_kind)
            if status in {"unavailable", "empty", "error"} and reason:
                suffix = "继续发送文案" if media_kind == "image" else "继续发送其余内容"
                return f"{reason}，{suffix}"

        media_available = getattr(bridge, "media_available", None)
        if (
            bridge is None
            or not callable(media_available)
            or media_available(media_kind)
        ):
            return default
        labels = {"image": "配图", "video": "视频", "audio": "语音"}
        label = labels.get(media_kind, "媒体")
        suffix = "继续发送文案" if media_kind == "image" else "继续发送其余内容"
        return f"生活插件未安装、未启用或正在重载，无法使用{label}能力，{suffix}"

    async def generate_share_image_step(
        self,
        *,
        progress_id: str,
        content: str,
        share_type,
        life_ctx: str,
        target_umo: str,
        current_img_path: str | None = None,
        event: AstrMessageEvent | None = None,
        progress_message: str = "配图生成中",
        fail_message: str = "配图生成失败，继续发送文案",
    ) -> tuple[str | None, str | None, str]:
        self.services.progress.update_share_progress(
            progress_id, "image", message=progress_message
        )
        img_path = current_img_path
        generated_image = await self.image_service.generate_image(
            content,
            share_type,
            life_ctx,
            target_umo=target_umo,
            event=event,
        )
        image_description = ""
        if isinstance(generated_image, GeneratedImage):
            ai_img_path = generated_image.path
            image_description = generated_image.description
        else:
            ai_img_path = str(generated_image or "") or None
        if ai_img_path:
            img_path = ai_img_path
            self.services.progress.complete_share_progress_step(
                progress_id, "image", "配图已生成"
            )
        else:
            self.services.progress.fail_share_progress_step(
                progress_id,
                "image",
                self._media_failure_message("image", fail_message),
            )

        send_img_path = (
            await self.services.weixin_delivery.prepare_image_for_target(
                target_umo, img_path
            )
            if img_path
            else None
        )
        return img_path, send_img_path, image_description

    async def generate_share_video_step(
        self,
        *,
        progress_id: str,
        img_path: str,
        content: str,
        image_description: str = "",
        target_umo: str,
        event: AstrMessageEvent | None = None,
        progress_message: str = "视频生成中",
    ) -> str:
        self.services.progress.update_share_progress(
            progress_id, "video", message=progress_message
        )
        video_url = await self.image_service.generate_video_from_image(
            img_path,
            content,
            image_description=image_description,
            target_umo=target_umo,
            event=event,
        )
        if video_url:
            self.services.progress.complete_share_progress_step(
                progress_id, "video", "视频已生成"
            )
        else:
            self.services.progress.fail_share_progress_step(
                progress_id,
                "video",
                self._media_failure_message("video", "视频生成失败，继续发送"),
            )
        return video_url

    async def generate_share_audio_step(
        self,
        *,
        progress_id: str,
        content: str,
        target_umo: str,
        share_type,
        period,
        event: AstrMessageEvent | None = None,
        progress_message: str = "语音生成中",
    ) -> str:
        self.services.progress.update_share_progress(
            progress_id, "audio", message=progress_message
        )
        audio_path = await self.ctx_service.text_to_speech(
            content,
            target_umo,
            share_type,
            period,
            event=event,
        )
        if audio_path:
            self.services.progress.complete_share_progress_step(
                progress_id, "audio", "语音已生成"
            )
        else:
            self.services.progress.fail_share_progress_step(
                progress_id,
                "audio",
                self._media_failure_message("audio", "语音生成失败，继续发送"),
            )
        return audio_path

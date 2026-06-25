from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from ....config import ShareType


class TaskCommandLocalRecordMixin:
    async def _send_command_generated_share(
        self,
        *,
        target_umo: str,
        content: str,
        send_img_path: str = None,
        audio_path: str = None,
        video_url: str = None,
        event: AstrMessageEvent,
        progress_id: str,
    ) -> tuple[bool, dict]:
        media_result = {}
        self._update_share_progress(progress_id, "send", message="发送中")
        sent = await self.send(
            target_umo,
            content,
            send_img_path,
            audio_path,
            video_url,
            event=event,
            media_result=media_result,
        )
        return bool(sent), media_result

    async def _record_command_share_success(
        self,
        *,
        target_umo: str,
        target_type_enum: ShareType,
        content: str,
        history_source: str,
        media_result: dict,
        img_path: str = None,
        video_url: str = None,
    ) -> None:
        img_desc = self.image_service.get_last_description()
        await self.ctx_service.record_bot_reply_to_history(target_umo, content, image_desc=img_desc)
        await self.ctx_service.record_to_memos(target_umo, content, img_desc)
        await self._record_share_history(
            target_id=target_umo,
            share_type=target_type_enum.value,
            content=content,
            success=True,
            source_type=history_source,
            media_result=media_result,
            image_ref=img_path,
            video_ref=video_url,
        )

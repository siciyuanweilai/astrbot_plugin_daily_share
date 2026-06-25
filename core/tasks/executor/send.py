from astrbot.api.event import AstrMessageEvent

from ...config import ShareType


class TaskExecutorSendMixin:
    """分享发送与记录。"""

    async def _send_execute_share_result(
        self,
        *,
        uid: str,
        content: str,
        send_img_path: str = None,
        audio_path: str = None,
        video_url: str = None,
        event: AstrMessageEvent = None,
        progress_id: str,
    ) -> tuple[bool, dict]:
        media_result = {}
        self._update_share_progress(progress_id, "send", message="发送中")
        sent = await self.send(
            uid,
            content,
            send_img_path,
            audio_path,
            video_url,
            event=event,
            media_result=media_result,
        )
        return bool(sent), media_result

    async def _record_execute_share_success(
        self,
        *,
        uid: str,
        stype: ShareType,
        content: str,
        history_source: str,
        media_result: dict,
        image_ref: str = None,
        video_ref: str = None,
    ) -> None:
        img_desc = self.image_service.get_last_description()
        await self.ctx_service.record_bot_reply_to_history(uid, content, image_desc=img_desc)
        await self.ctx_service.record_to_memos(uid, content, img_desc)
        await self._record_share_history(
            target_id=uid,
            share_type=stype.value,
            content=content,
            success=True,
            source_type=history_source,
            media_result=media_result,
            image_ref=image_ref,
            video_ref=video_ref,
        )

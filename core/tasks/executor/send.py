from astrbot.api.event import AstrMessageEvent

from ...config import ShareType
from .flow import TaskExecutorFlowService


class TaskExecutorSendService(TaskExecutorFlowService):
    """分享发送与记录。"""

    async def _send_execute_share_result(
        self,
        *,
        uid: str,
        content: str,
        send_img_path: str | None = None,
        audio_path: str | None = None,
        video_url: str | None = None,
        event: AstrMessageEvent | None = None,
        progress_id: str,
    ) -> tuple[bool, dict]:
        media_result: dict = {}
        self.services.progress.update_share_progress(
            progress_id, "send", message="发送中"
        )
        sent = await self.services.delivery.send(
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
        image_ref: str | None = None,
        video_ref: str | None = None,
        news_snapshot_data: dict | None = None,
        news_image_url: str | None = None,
        image_description: str = "",
    ) -> None:
        await self.ctx_service.record_bot_reply_to_history(
            uid, content, image_desc=image_description
        )
        media_kind = (
            "video"
            if media_result.get("video_sent")
            else "audio"
            if media_result.get("audio_sent")
            else "image"
            if media_result.get("image_sent")
            else ""
        )
        await self.ctx_service.record_external_share(
            uid,
            content,
            image_description,
            image_sent=bool(media_result.get("image_sent")),
            media_kind=media_kind,
        )
        await self.services.executor_helpers.record_share_history(
            target_id=uid,
            share_type=stype.value,
            content=content,
            success=True,
            source_type=history_source,
            media_result=media_result,
            image_ref=image_ref,
            video_ref=video_ref,
            news_snapshot_data=news_snapshot_data,
            news_image_url=news_image_url,
        )

from astrbot.api.event import AstrMessageEvent

from ...config import ShareType
from ...integrations.delivery import record_confirmed_history, record_confirmed_share
from ..taskbase import TaskServiceBase


class TaskExecutorSendService(TaskServiceBase):
    """分享发送与记录。"""

    async def send(
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

    async def record_success(
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
        degradation_reason: str = "",
    ) -> None:
        await record_confirmed_history(
            self.ctx_service, uid, content, image_description, media_result
        )
        await record_confirmed_share(
            self.ctx_service, uid, content, image_description, media_result
        )
        await self.services.executor_helpers.records.record_share_history(
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
            degradation_reason=degradation_reason,
        )

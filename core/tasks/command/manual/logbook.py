from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.api.event import AstrMessageEvent

from ....config import ShareType
from ....integrations.delivery import record_confirmed_share

if TYPE_CHECKING:
    from .. import TaskCommandShareService


class TaskCommandLocalRecordService:
    def __init__(self, owner: TaskCommandShareService) -> None:
        self.owner = owner

    async def _send_command_generated_share(
        self,
        *,
        target_umo: str,
        content: str,
        send_img_path: str | None = None,
        audio_path: str | None = None,
        video_url: str | None = None,
        event: AstrMessageEvent,
        progress_id: str,
    ) -> tuple[bool, dict]:
        media_result: dict = {}
        self.owner.services.progress.update_share_progress(
            progress_id, "send", message="发送中"
        )
        sent = await self.owner.services.delivery.send(
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
        img_path: str | None = None,
        video_url: str | None = None,
        news_snapshot_data: dict | None = None,
        news_image_url: str | None = None,
        image_description: str = "",
        degradation_reason: str = "",
    ) -> None:
        await self.owner.ctx_service.record_bot_reply_to_history(
            target_umo, content, image_desc=image_description
        )
        await record_confirmed_share(
            self.owner.ctx_service, target_umo, content, image_description, media_result
        )
        await self.owner.services.executor_helpers.records.record_share_history(
            target_id=target_umo,
            share_type=target_type_enum.value,
            content=content,
            success=True,
            source_type=history_source,
            media_result=media_result,
            image_ref=img_path,
            video_ref=video_url,
            news_snapshot_data=news_snapshot_data,
            news_image_url=news_image_url,
            degradation_reason=degradation_reason,
        )

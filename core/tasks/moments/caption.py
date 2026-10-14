from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ...config import ShareType, TimePeriod
from ...database.keys import QZONE_TARGET_ID

if TYPE_CHECKING:
    from . import TaskQzoneService


class TaskQzoneContentService:
    """QQ 空间文案生成。"""

    def __init__(self, owner: TaskQzoneService) -> None:
        self.owner = owner

    async def _generate_qzone_content(
        self,
        *,
        stype: ShareType,
        period: TimePeriod,
        post_ctx: str,
        news_data,
        progress_id: str,
        event: AstrMessageEvent | None = None,
    ) -> str:
        recent_post_contents = (
            await self.owner.services.executor_helpers.context.get_recent_post_contents(
                QZONE_TARGET_ID
            )
        )

        logger.info("[日常分享] 正在为 QQ 空间生成自然状态文案（daily_life 联动）...")
        self.owner.services.progress.update_share_progress(
            progress_id, "content", message="QQ 空间文案生成中"
        )
        qzone_content = await self.owner.content_service.generate(
            stype,
            period,
            QZONE_TARGET_ID,
            False,
            post_ctx,
            news_data,
            nickname="",
            recent_post_contents=recent_post_contents,
            structured_history="",
        )
        if not qzone_content:
            logger.error("[日常分享] QQ 空间文案生成失败")
            if event:
                await self.owner.send_event(
                    event, event.plain_result("QQ空间文案生成失败")
                )
            self.owner.services.progress.finish_share_progress(
                progress_id, success=False, message="文案生成失败"
            )
            return ""

        self.owner.services.progress.complete_share_progress_step(
            progress_id, "content", "文案已生成"
        )
        return str(qzone_content or "").strip()

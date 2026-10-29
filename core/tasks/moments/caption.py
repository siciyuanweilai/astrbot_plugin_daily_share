from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ...config import ShareType, TimePeriod
from ...database.keys import QZONE_TARGET_ID
from ..opportunity import opportunity_materials, opportunity_prompt, opportunity_query

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
        (
            recent_post_contents,
            history_prompt,
        ) = await self.owner.services.executor_helpers.context.recent_share_context(
            QZONE_TARGET_ID
        )

        logger.info("[日常分享] 正在生成 QQ 空间文案...")
        self.owner.services.progress.update_share_progress(
            progress_id, "content", message="QQ 空间文案生成中"
        )
        bridge = getattr(self.owner.plugin, "daily_life_bridge", None)
        memory_getter = getattr(bridge, "related_memory_prompt", None)
        if callable(memory_getter):
            memory = await memory_getter(
                opportunity_query(QZONE_TARGET_ID, post_ctx), QZONE_TARGET_ID
            )
            if memory:
                post_ctx += "\n\n" + memory
        post_ctx += history_prompt
        qzone_content = await self.owner.content_service.generate(
            stype,
            period,
            QZONE_TARGET_ID,
            False,
            post_ctx + opportunity_prompt(QZONE_TARGET_ID),
            news_data,
            nickname="",
            recent_post_contents=recent_post_contents,
            structured_history="",
            share_materials=opportunity_materials(QZONE_TARGET_ID),
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

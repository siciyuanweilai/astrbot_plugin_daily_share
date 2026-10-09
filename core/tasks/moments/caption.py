from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ...config import ShareType, TimePeriod
from ...database.keys import QZONE_TARGET_ID
from .illustration import TaskQzoneMediaService


class TaskQzoneContentService(TaskQzoneMediaService):
    """QQ 空间文案生成。"""

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
            await self.services.executor_helpers.get_recent_post_contents(
                QZONE_TARGET_ID
            )
        )

        logger.info("[日常分享] 正在为 QQ 空间生成自然状态文案（daily_life 联动）...")
        self.services.progress.update_share_progress(
            progress_id, "content", message="QQ 空间文案生成中"
        )
        qzone_content = await self.content_service.generate(
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
                await self.send_event(event, event.plain_result("QQ空间文案生成失败"))
            self.services.progress.finish_share_progress(
                progress_id, success=False, message="文案生成失败"
            )
            return ""

        self.services.progress.complete_share_progress_step(
            progress_id, "content", "文案已生成"
        )
        return str(qzone_content or "").strip()

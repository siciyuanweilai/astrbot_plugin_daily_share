from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ...config import ShareType, TimePeriod
from ...database.keys import QZONE_TARGET_ID
from ...prompt import build_qzone_diary_prompt
from .illustration import TaskQzoneMediaService


class TaskQzoneContentService(TaskQzoneMediaService):
    """QQ 空间文案生成。"""

    async def _generate_qzone_content(
        self,
        *,
        stype: ShareType,
        period: TimePeriod,
        life_ctx,
        news_data,
        progress_id: str,
        event: AstrMessageEvent | None = None,
    ) -> str:
        qzone_life_prompt = self.ctx_service.format_life_context(
            life_ctx, stype, False, None
        )
        qzone_life_prompt += f"\n\n{build_qzone_diary_prompt()}"
        qzone_recent_dynamics_str = (
            await self.services.executor_helpers.format_recent_dynamics(QZONE_TARGET_ID)
        )

        logger.info("[日常分享] 正在为 QQ 空间生成文案...")
        self.services.progress.update_share_progress(
            progress_id, "content", message="QQ 空间文案生成中"
        )
        qzone_content = await self.content_service.generate(
            stype,
            period,
            QZONE_TARGET_ID,
            False,
            qzone_life_prompt,
            news_data,
            nickname="",
            recent_dynamics=qzone_recent_dynamics_str,
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

from astrbot.api.event import AstrMessageEvent

from ...context.relevance import recent_share_prompt
from ..opportunity import opportunity_query
from ..taskbase import TaskServiceBase


class TaskHelperContextService(TaskServiceBase):
    """文案上下文和新闻快照辅助。"""

    async def _recent_share_history(self, target_id: str) -> list[dict]:
        try:
            ref_count = int(self.context_conf.get("reference_history_count", 3))
        except Exception:
            ref_count = 3
        if ref_count <= 0:
            return []
        return await self.db.get_recent_history_by_target(
            target_id, limit=min(12, ref_count)
        )

    async def get_recent_post_contents(self, target_id: str) -> list[str]:
        history = await self._recent_share_history(target_id)
        return [str(item.get("content") or "").strip() for item in history]

    async def recent_share_context(self, target_id: str) -> tuple[list[str], str]:
        history = await self._recent_share_history(target_id)
        return [
            str(row.get("content") or "").strip() for row in history
        ], recent_share_prompt(history)

    async def prepare_content_context(
        self,
        *,
        target_umo: str,
        share_type,
        life_ctx: str,
        is_group: bool,
        event: AstrMessageEvent | None = None,
        nickname: str = "",
        recent_target_id: str = "",
    ) -> dict:
        """准备生成文案所需的上下文。"""
        hist_data = await self.ctx_service.get_history_data(
            target_umo, is_group, event=event
        )
        structured_history = self.ctx_service.format_structured_history_context(
            hist_data, limit=6, query=opportunity_query(target_umo, life_ctx)
        )
        group_info = hist_data.get("group_info")
        life_prompt = self.ctx_service.format_life_context(
            life_ctx,
            share_type,
            is_group,
            group_info,
        )
        _, real_id = self.ctx_service.parse_umo(target_umo)
        history = await self._recent_share_history(recent_target_id or target_umo)
        recent_post_contents = [
            str(row.get("content") or "").strip() for row in history
        ]
        life_prompt += recent_share_prompt(history)
        return {
            "hist_data": hist_data,
            "structured_history": structured_history,
            "life_prompt": life_prompt,
            "recent_post_contents": recent_post_contents,
            "group_info": group_info,
            "real_id": real_id,
        }

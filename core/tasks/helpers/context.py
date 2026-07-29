from astrbot.api.event import AstrMessageEvent

from .imagery import TaskHelperMediaService


class TaskHelperContextService(TaskHelperMediaService):
    """文案上下文和新闻快照辅助。"""

    async def format_recent_dynamics(self, target_id: str) -> str:
        try:
            ref_count = int(self.context_conf.get("reference_history_count", 3))
        except Exception:
            ref_count = 3
        if ref_count <= 0:
            return ""
        recent_hist = await self.db.get_recent_history_by_target(
            target_id, limit=ref_count
        )
        if not recent_hist:
            return ""
        return "\n".join(
            f"- [{h.get('type')}] {str(h.get('content', '') or '').strip()}"
            for h in reversed(recent_hist)
        )

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
            hist_data, limit=6
        )
        group_info = hist_data.get("group_info")
        life_prompt = self.ctx_service.format_life_context(
            life_ctx,
            share_type,
            is_group,
            group_info,
        )
        _, real_id = self.ctx_service.parse_umo(target_umo)
        recent_dynamics = await self.format_recent_dynamics(
            recent_target_id or target_umo
        )
        return {
            "hist_data": hist_data,
            "structured_history": structured_history,
            "life_prompt": life_prompt,
            "recent_dynamics": recent_dynamics,
            "group_info": group_info,
            "real_id": real_id,
        }

    async def commit_sent_news_snapshot_for_targets(
        self,
        *target_uids,
        snapshot_data=None,
        image_url: str | None = None,
        event: AstrMessageEvent | None = None,
    ):
        committed = set()
        for target_uid in target_uids:
            target = str(target_uid or "").strip()
            if target and target not in committed:
                await self.services.snapshots.commit_sent_news_snapshot(
                    target,
                    snapshot_data=snapshot_data,
                    image_url=image_url,
                )
                committed.add(target)
        if event:
            current_target = str(getattr(event, "unified_msg_origin", "") or "").strip()
            if current_target and current_target not in committed:
                await self.services.snapshots.commit_sent_news_snapshot(
                    current_target,
                    snapshot_data=snapshot_data,
                    image_url=image_url,
                )

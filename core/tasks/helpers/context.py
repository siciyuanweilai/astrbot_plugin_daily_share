from astrbot.api.event import AstrMessageEvent


class TaskHelperContextMixin:
    """文案上下文与新闻快照辅助。"""

    async def _format_recent_dynamics(self, target_id: str) -> str:
        try:
            ref_count = int(self.context_conf.get("reference_history_count", 3))
        except Exception:
            ref_count = 3
        if ref_count <= 0:
            return ""
        recent_hist = await self.db.get_recent_history_by_target(target_id, limit=ref_count)
        if not recent_hist:
            return ""
        return "\n".join(
            f"- [{h.get('type')}] {str(h.get('content', '') or '').strip()}"
            for h in reversed(recent_hist)
        )

    async def _prepare_content_context(
        self,
        *,
        target_umo: str,
        share_type,
        life_ctx: str,
        is_group: bool,
        event: AstrMessageEvent = None,
        nickname: str = "",
        recent_target_id: str = "",
    ) -> dict:
        """准备生成文案所需的上下文，统一自动任务和命令触发路径。"""
        hist_data = await self.ctx_service.get_history_data(target_umo, is_group, event=event)
        hist_prompt = self.ctx_service.format_history_prompt(hist_data, share_type)
        group_info = hist_data.get("group_info")
        _, real_id = self.ctx_service._parse_umo(target_umo)

        target_info = None
        if not is_group:
            target_info = {
                "target_id": target_umo,
                "real_id": real_id,
                "nickname": nickname,
            }
        life_prompt = self.ctx_service.format_life_context(
            life_ctx,
            share_type,
            is_group,
            group_info,
            target_info,
        )
        recent_dynamics = await self._format_recent_dynamics(recent_target_id or target_umo)
        return {
            "hist_data": hist_data,
            "hist_prompt": hist_prompt,
            "life_prompt": life_prompt,
            "recent_dynamics": recent_dynamics,
            "group_info": group_info,
            "real_id": real_id,
        }

    async def _cache_news_snapshot_for_targets(
        self,
        *target_uids,
        news_data=None,
        source_key: str = None,
        image_url: str = None,
        event: AstrMessageEvent = None,
    ):
        for target_uid in target_uids:
            if target_uid:
                await self.cache_news_snapshot(
                    target_uid,
                    news_data=news_data,
                    source_key=source_key,
                    image_url=image_url,
                )
        if event:
            current_target = str(getattr(event, "unified_msg_origin", "") or "").strip()
            if current_target and current_target not in target_uids:
                await self.cache_news_snapshot(
                    current_target,
                    news_data=news_data,
                    source_key=source_key,
                    image_url=image_url,
                )

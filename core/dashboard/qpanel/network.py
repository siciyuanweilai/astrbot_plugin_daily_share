from __future__ import annotations

from astrbot.api import logger


class DashboardQzoneRelationMixin:
    async def page_qzone_relation(self):
        async def handler():
            params = await self._page_query_params()
            relation_type = str(params.get("type") or "care").strip().lower()
            if relation_type not in {"care", "care_by", "careby"}:
                relation_type = "care"
            ctx = await self.qzone_service.context()
            relation = await self.qzone_service.query_relations(relation_type=relation_type)
            try:
                stats = await self.qzone_service.query_visit_stats()
            except Exception as exc:
                logger.debug(f"[每日分享] QQ 空间浏览统计暂不可用: {exc}")
                stats = {"available": False, "today_views": 0, "total_views": 0, "visitor_count": 0}
            return {
                "ok": True,
                "data": {
                    "account": self._page_qzone_account_payload(ctx),
                    "type": relation.get("type") or relation_type,
                    "items": relation.get("items") or [],
                    "stats": stats,
                },
            }

        return await self._page_json(handler)

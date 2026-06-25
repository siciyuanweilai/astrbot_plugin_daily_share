from __future__ import annotations


class DashboardRouteQueryMixin:
    async def page_history(self):
        async def handler():
            params = await self._page_query_params()
            try:
                limit = min(max(int(params.get("limit") or 30), 1), 100)
            except Exception:
                limit = 30
            target_id = str(params.get("target_id") or "").strip()
            history = (
                await self.db.get_recent_history_by_target(target_id, limit=limit)
                if target_id
                else await self.db.get_recent_history(limit=limit)
            )
            return {"ok": True, "data": {"items": await self._page_prepare_history_items(history)}}

        return await self._page_json(handler)

    async def page_failures(self):
        async def handler():
            params = await self._page_query_params()
            try:
                limit = min(max(int(params.get("limit") or 20), 1), 100)
            except Exception:
                limit = 20
            return {
                "ok": True,
                "data": {
                    "items": await self._page_prepare_history_items(
                        await self.db.get_recent_failures(limit=limit)
                    )
                },
            }

        return await self._page_json(handler)

    async def page_failures_clear(self):
        async def handler():
            deleted = await self.db.clear_failures()
            status = await self._build_page_status()
            return {
                "ok": True,
                "data": {
                    **status["data"],
                    "deleted": deleted,
                },
                "message": f"已清空 {deleted} 条失败记录",
            }

        return await self._page_json(handler)

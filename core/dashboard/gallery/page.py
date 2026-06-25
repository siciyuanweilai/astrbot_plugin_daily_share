from __future__ import annotations

from ...config import ShareType


class DashboardMediaPageMixin:
    def _page_dashboard_dynamic_days(self) -> int:
        try:
            days = int(self.basic_conf.get("dashboard_dynamic_days", 60))
        except Exception:
            days = 60
        return max(0, min(days, 3650))

    async def _page_media_page(
        self,
        limit: int,
        days: int = None,
        media_kind: str = "all",
        share_type: str = "all",
    ) -> dict:
        limit = min(max(int(limit), 1), 100)
        if days is None:
            days = self._page_dashboard_dynamic_days()
        media_kind = self._page_dynamic_media_kind(media_kind)
        share_type = self._page_dynamic_share_type(share_type)
        today_only = media_kind == "today"
        rows = await self.db.get_recent_dynamics(
            limit=limit + 1,
            days=days,
            media_kind="all" if today_only else media_kind,
            share_type=share_type,
            today_only=today_only,
        )
        return {
            "items": await self._page_prepare_media_items(rows[:limit]),
            "limit": limit,
            "has_more": len(rows) > limit,
            "dynamic_days": days,
            "media_kind": media_kind,
            "share_type": share_type,
            "today_only": today_only,
        }

    async def page_media(self):
        async def handler():
            params = await self._page_query_params()
            try:
                limit = min(max(int(params.get("limit") or 24), 1), 100)
            except Exception:
                limit = 24
            return {
                "ok": True,
                "data": await self._page_media_page(
                    limit,
                    media_kind=params.get("kind") or "all",
                    share_type=params.get("type") or "all",
                ),
            }

        return await self._page_json(handler)

    @staticmethod
    def _page_history_ids_from_body(body: dict) -> list:
        raw_ids = body.get("ids")
        if raw_ids is None and body.get("id") is not None:
            raw_ids = [body.get("id")]
        if isinstance(raw_ids, (str, int)):
            raw_ids = [raw_ids]
        if not isinstance(raw_ids, list):
            return []

        ids = []
        seen = set()
        for raw_id in raw_ids:
            try:
                history_id = int(raw_id)
            except Exception:
                continue
            if history_id > 0 and history_id not in seen:
                ids.append(history_id)
                seen.add(history_id)
        return ids

    async def page_media_delete(self):
        async def handler():
            body = await self._page_json_body()
            ids = self._page_history_ids_from_body(body)
            if not ids:
                raise RuntimeError("缺少要删除的记录")
            try:
                limit = min(max(int(body.get("limit") or 24), 1), 100)
            except Exception:
                limit = 24
            media_kind = body.get("kind") or "all"
            share_type = body.get("type") or "all"
            history_items = await self.db.get_history_by_ids(ids)
            deleted = await self.db.delete_history_by_ids(ids)
            file_delete = {
                "requested": True,
                "deleted": 0,
                "skipped": 0,
                "failed": 0,
                "bytes": 0,
            }
            if deleted > 0:
                file_delete = await self._page_delete_local_media_files(history_items)
            media_page = await self._page_media_page(
                limit,
                media_kind=media_kind,
                share_type=share_type,
            )
            self._page_emit_dashboard_event(
                "media",
                {"action": "delete", "ids": ids, "deleted": deleted, "files": file_delete},
            )
            return {
                "ok": True,
                "data": {
                    **media_page,
                    "deleted": deleted,
                    "files": file_delete,
                    "ids": ids,
                },
                "message": f"已删除 {deleted} 条记录",
            }

        return await self._page_json(handler)

    async def page_media_view(self):
        async def handler():
            body = await self._page_json_body()
            history_id = body.get("history_id")
            if history_id is None:
                raise RuntimeError("缺少 history_id")
            history_id = int(history_id)

            item = await self.db.get_history_by_id(history_id)
            if not item:
                raise RuntimeError("未找到媒体记录")
            if self._page_media_kind(item) != "image":
                raise RuntimeError("该媒体不是图片")

            return {
                "ok": True,
                "data": {
                    "id": item.get("id"),
                    "media_type": "image",
                    **await self._page_view_image_payload(item, history_id),
                },
            }

        return await self._page_json(handler, self._page_media_cache_headers())

from __future__ import annotations


class DashboardQzoneEntryMixin:
    async def page_qzone_entry(self):
        async def handler():
            params = await self._page_query_params()
            entry = str(params.get("entry") or "").strip().lower()
            pos, num = self._page_qzone_page_args(params)
            ctx = await self.qzone_service.context()

            if entry == "about":
                payload = await self._page_qzone_about_payload(ctx, pos=pos, num=num)
            elif entry == "today":
                payload = await self._page_qzone_today_payload(ctx, params=params, pos=pos, num=num)
            elif entry == "board":
                payload = await self._page_qzone_board_payload(params, pos=pos, num=num)
            else:
                raise RuntimeError("未知 QQ 空间入口")

            return {
                "ok": True,
                "data": {
                    "account": self._page_qzone_account_payload(ctx),
                    "entry": entry,
                    **payload,
                },
            }

        return await self._page_json(handler)

    async def _page_qzone_about_payload(self, ctx, *, pos: int, num: int) -> dict:
        result = await self.qzone_service.query_about_me(offset=pos, count=num)
        items = self._page_qzone_post_items(result.get("items") or [], self_uin=ctx.uin, include_comments=True)
        return {
            "kind": "posts",
            "items": items,
            "has_more": bool(result.get("has_more")),
            "next_pos": int(result.get("next_offset") or pos + len(items)),
            "message": result.get("message") or "",
        }

    async def _page_qzone_today_payload(self, ctx, *, params: dict, pos: int, num: int) -> dict:
        try:
            year = int(params.get("year") or 0) or None
        except Exception:
            year = None
        result = await self.qzone_service.query_last_year(year=year, count=num)
        items = self._page_qzone_post_items(result.get("items") or [], self_uin=ctx.uin, include_comments=True)
        return {
            "kind": "posts",
            "items": items,
            "has_more": bool(result.get("has_more")),
            "next_pos": pos + len(items),
            "message": result.get("message") or "",
        }

    async def _page_qzone_board_payload(self, params: dict, *, pos: int, num: int) -> dict:
        target_id = str(params.get("target_id") or "").strip()
        result = await self.qzone_service.query_message_board(target_id=target_id, start=pos, num=num)
        items = result.get("items") or []
        return {
            "kind": "messages",
            "items": items,
            "total": int(result.get("total") or 0),
            "has_more": bool(result.get("has_more")),
            "next_pos": pos + len(items),
            "message": result.get("message") or "",
        }

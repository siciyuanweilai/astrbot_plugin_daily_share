from __future__ import annotations


class DashboardQzoneActionMixin:
    async def page_qzone_like(self):
        async def handler():
            body = await self._page_json_body()
            post_id = self._page_qzone_required_post_id(body)
            await self.qzone_service.like(post_id)
            self._page_emit_dashboard_event("qzone", {"action": "like", "post_id": post_id})
            return {"ok": True, "data": {}, "message": "已点赞"}

        return await self._page_json(handler)

    async def page_qzone_comment(self):
        async def handler():
            body = await self._page_json_body()
            post_id = self._page_qzone_required_post_id(body)
            content = str(body.get("content") or body.get("text") or "").strip()
            if not content:
                raise RuntimeError("评论内容不能为空")
            await self.qzone_service.comment(post_id, content)
            self._page_emit_dashboard_event("qzone", {"action": "comment", "post_id": post_id})
            return {"ok": True, "data": {}, "message": "评论已发送"}

        return await self._page_json(handler)

    async def page_qzone_delete(self):
        async def handler():
            body = await self._page_json_body()
            post_id = self._page_qzone_required_post_id(body)
            await self.qzone_service.delete_post(post_id)
            self._page_emit_dashboard_event("qzone", {"action": "delete", "post_id": post_id})
            return {"ok": True, "data": {"id": post_id}, "message": "说说已删除"}

        return await self._page_json(handler)

    @staticmethod
    def _page_qzone_required_post_id(body: dict) -> str:
        post_id = str(body.get("id") or body.get("post_id") or "").strip()
        if not post_id:
            raise RuntimeError("缺少说说 ID")
        return post_id

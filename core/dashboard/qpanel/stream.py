from __future__ import annotations

from astrbot.api import logger


class DashboardQzoneFeedMixin:
    async def page_qzone_feed(self):
        async def handler():
            params = await self._page_query_params()
            scope = str(params.get("scope") or "").strip().lower()
            target_id = str(params.get("target_id") or "").strip()
            pos, num = self._page_qzone_page_args(params)
            fetch_num = min(num + 1, 20)
            with_detail = str(params.get("detail") or "").lower() in {"1", "true", "yes", "on"}

            try:
                ctx = await self.qzone_service.context()
            except Exception as exc:
                logger.debug(f"[每日分享] QQ 空间面板登录态暂不可用: {exc}")
                return {
                    "ok": True,
                    "data": {
                        "account": {"uin": 0, "nickname": ""},
                        "items": [],
                        "pos": pos,
                        "num": num,
                        "available": False,
                        "retryable": True,
                        "message": "QQ 空间登录态暂不可用",
                    },
                }

            try:
                if scope in {"friends", "feed"} and not target_id:
                    posts = await self.qzone_service.query_recent_posts(
                        pos=pos,
                        num=fetch_num,
                        with_detail=with_detail,
                    )
                else:
                    query_target_id = target_id or str(ctx.uin)
                    posts = await self.qzone_service.query_posts(
                        target_id=query_target_id,
                        pos=pos,
                        num=fetch_num,
                        with_detail=with_detail,
                    )
                has_more = len(posts) > num
                posts = posts[:num]
            except Exception as exc:
                logger.debug(f"[每日分享] QQ 空间面板说说暂不可用: {exc}")
                posts = []
                has_more = False
                error_message = str(exc) or "QQ 空间说说暂不可用"
            else:
                error_message = ""

            return {
                "ok": True,
                "data": {
                    "account": self._page_qzone_account_payload(ctx),
                    "items": self._page_qzone_post_items(posts, self_uin=ctx.uin, include_comments=True),
                    "pos": pos,
                    "num": num,
                    "has_more": has_more,
                    "available": not error_message,
                    "retryable": bool(error_message),
                    "message": error_message,
                },
            }

        return await self._page_json(handler)

    async def page_qzone_detail(self):
        async def handler():
            params = await self._page_query_params()
            post_id = str(params.get("id") or params.get("post_id") or "").strip()
            if not post_id:
                raise RuntimeError("缺少说说 ID")
            ctx = await self.qzone_service.context()
            post = await self.qzone_service.detail(post_id)
            return {
                "ok": True,
                "data": {
                    "item": self._page_qzone_post_payload(
                        post,
                        self_uin=ctx.uin,
                        include_comments=True,
                    )
                },
            }

        return await self._page_json(handler)

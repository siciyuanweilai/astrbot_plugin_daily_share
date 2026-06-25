from __future__ import annotations

from ..models import QzonePost
from ..parse import parse_feed_list


class QzoneFeedPostsMixin:
    """自己的说说列表。"""

    async def query_posts(
        self,
        *,
        target_id: str = "",
        pos: int = 0,
        num: int = 5,
        with_detail: bool = False,
    ) -> list[QzonePost]:
        ctx = await self.context()
        target = str(target_id or ctx.uin).strip()
        limit = max(1, min(int(num or 5), 20))
        payload = await self._request(
            "GET",
            self.LIST_URL,
            params={
                "g_tk": ctx.gtk,
                "uin": target,
                "ftype": 0,
                "sort": 0,
                "pos": max(0, int(pos or 0)),
                "num": limit,
                "replynum": 100,
                "callback": "_preloadCallback",
                "code_version": 1,
                "format": "json",
                "need_comment": 1,
                "need_private_comment": 1,
            },
        )
        if not self._ok(payload):
            raise RuntimeError(str(payload.get("message") or "获取 QQ 空间说说失败"))
        posts = parse_feed_list(payload.get("msglist") or [])
        if with_detail:
            posts = [self._merge_post_detail(post, await self._safe_post_detail(post)) for post in posts]
        self._remember_posts(posts)
        return posts

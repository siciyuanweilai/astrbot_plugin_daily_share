from __future__ import annotations

from ..methodset import QzoneMethodSet
from ..models import QzonePost
from ..parse import parse_feed_list


class QzoneFeedPostsService(QzoneMethodSet):
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
        offset = max(0, int(pos or 0))
        limit = max(1, min(int(num or 5), 20))
        cache_key = self._query_cache_key(
            "posts",
            target=target,
            pos=offset,
            num=limit,
            with_detail=int(bool(with_detail)),
        )
        cached_posts = self._cached_query_posts(cache_key)
        if cached_posts is not None:
            return cached_posts

        payload = await self._request(
            "GET",
            self.LIST_URL,
            params={
                "g_tk": ctx.gtk,
                "uin": target,
                "ftype": 0,
                "sort": 0,
                "pos": offset,
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
            posts = [
                self._merge_post_detail(post, await self._safe_post_detail(post))
                for post in posts
            ]
        self._remember_posts(posts, detailed=with_detail)
        self._store_query_posts(cache_key, posts)
        return posts

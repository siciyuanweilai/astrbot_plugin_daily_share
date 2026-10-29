from __future__ import annotations

from typing import TYPE_CHECKING

from ...concurrency import gather_readonly
from ..models import QzonePost
from ..parse import parse_feed_list

if TYPE_CHECKING:
    from ..qzone import QzoneService


class QzoneFeedPostsService:
    """自己的说说列表。"""

    def __init__(self, owner: QzoneService) -> None:
        self.owner = owner

    async def query_posts(
        self,
        *,
        target_id: str = "",
        pos: int = 0,
        num: int = 5,
        with_detail: bool = False,
    ) -> list[QzonePost]:
        ctx = await self.owner.context()
        target = str(target_id or ctx.uin).strip()
        offset = max(0, int(pos or 0))
        limit = max(1, min(int(num or 5), 20))
        cache_key = self.owner._query_cache_key(
            "posts",
            target=target,
            pos=offset,
            num=limit,
            with_detail=int(bool(with_detail)),
        )
        cached_posts = self.owner._cached_query_posts(cache_key)
        if cached_posts is not None:
            return cached_posts

        payload = await self.owner._request(
            "GET",
            self.owner.LIST_URL,
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
        if not self.owner._ok(payload):
            raise RuntimeError(str(payload.get("message") or "获取 QQ 空间说说失败"))
        posts = parse_feed_list(payload.get("msglist") or [])
        if with_detail:
            details = await gather_readonly(
                *(self.owner._safe_post_detail(post) for post in posts)
            )
            posts = [
                self.owner._merge_post_detail(post, detail)
                for post, detail in zip(posts, details)
            ]
        # 详情成功时由 detail() 标记；失败回退的列表内容不能冒充完整详情。
        self.owner._remember_posts(posts)
        self.owner._store_query_posts(cache_key, posts)
        return posts

from __future__ import annotations

from typing import TYPE_CHECKING

from ...concurrency import gather_readonly
from ..models import QzonePost
from ..parse import parse_recent_feed_list

if TYPE_CHECKING:
    from ..qzone import QzoneService


class QzoneFeedRecentService:
    """好友动态列表。"""

    def __init__(self, owner: QzoneService) -> None:
        self.owner = owner

    async def query_recent_posts(
        self,
        *,
        pos: int = 0,
        num: int = 5,
        with_detail: bool = False,
        cursor: str = "",
    ) -> list[QzonePost]:
        ctx = await self.owner.context()
        offset = max(0, int(pos or 0))
        limit = max(1, min(int(num or 5), 20))
        fetch_count = min(50, max(20, offset + limit))
        cache_key = self.owner._query_cache_key(
            "recent",
            pos=offset,
            num=limit,
            cursor=cursor,
            with_detail=int(bool(with_detail)),
        )
        cached_posts = self.owner._cached_query_posts(cache_key)
        if cached_posts is not None:
            return cached_posts

        payload = await self.owner._request(
            "GET",
            self.owner.RECENT_URL,
            params=self.owner._recent_posts_params(
                ctx, count=fetch_count, cursor=cursor
            ),
            headers=self.owner._feeds3_headers(ctx),
        )
        if not self.owner._ok(payload):
            self.owner._last_friend_feeds_meta = {
                "source": "recent_posts",
                "count": 0,
                "http_status": payload.get("_http_status"),
                "raw_length": payload.get("_raw_length"),
                "message": str(payload.get("message") or payload.get("msg") or ""),
            }
            raise RuntimeError(
                str(payload.get("message") or "获取 QQ 空间好友动态失败")
            )

        payload_meta = self.owner._friend_feeds_payload_meta(payload)
        all_posts = parse_recent_feed_list(payload)
        posts = all_posts[offset : offset + limit]
        if with_detail:
            posts = await self.owner._query_recent_post_details(posts)
        self.owner._last_friend_feeds_meta = {
            "source": "recent_posts",
            "count": len(posts),
            "parsed_count": len(all_posts),
            "http_status": payload.get("_http_status"),
            "raw_length": payload.get("_raw_length"),
            "has_more": self.owner._friend_feeds_has_more(payload, all_posts),
            "next_cursor": self.owner._friend_feeds_next_cursor(payload),
            **payload_meta,
        }
        self.owner._remember_posts(posts)
        self.owner._store_query_posts(
            cache_key, posts, meta=self.owner._last_friend_feeds_meta
        )
        return posts

    async def _query_recent_post_details(
        self, posts: list[QzonePost]
    ) -> list[QzonePost]:
        async def enrich(post):
            # 仅凭非说说动态的键无法重建 appid 和照片标识。
            if int(post.appid or 311) != 311:
                self.owner._remember_posts([post])
                self.owner._post_detail_cache_at.pop(post.key, None)
            try:
                detail = await self.owner.detail(post.key)
                detail.feed_key = detail.feed_key or post.feed_key
                detail.curkey = post.curkey or detail.curkey
                detail.unikey = post.unikey or detail.unikey
                detail.busi_param = detail.busi_param or post.busi_param
                return detail
            except Exception:
                return post

        return await gather_readonly(*(enrich(post) for post in posts))

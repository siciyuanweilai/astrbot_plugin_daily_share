from __future__ import annotations

from ..models import QzonePost
from ..parse import parse_recent_feed_list


class QzoneFeedRecentMixin:
    """好友动态列表。"""

    async def query_recent_posts(
        self,
        *,
        pos: int = 0,
        num: int = 5,
        with_detail: bool = False,
        cursor: str = "",
    ) -> list[QzonePost]:
        ctx = await self.context()
        offset = max(0, int(pos or 0))
        limit = max(1, min(int(num or 5), 20))
        fetch_count = min(50, max(20, offset + limit))
        payload = await self._request(
            "GET",
            self.RECENT_URL,
            params=self._recent_posts_params(ctx, count=fetch_count, cursor=cursor),
            headers=self._feeds3_headers(ctx),
        )
        if not self._ok(payload):
            self._last_friend_feeds_meta = {
                "source": "recent_posts",
                "count": 0,
                "http_status": payload.get("_http_status"),
                "raw_length": payload.get("_raw_length"),
                "message": str(payload.get("message") or payload.get("msg") or ""),
            }
            raise RuntimeError(str(payload.get("message") or "获取 QQ 空间好友动态失败"))

        payload_meta = self._friend_feeds_payload_meta(payload)
        all_posts = parse_recent_feed_list(payload)
        posts = all_posts[offset : offset + limit]
        if with_detail:
            posts = await self._query_recent_post_details(posts)
        self._last_friend_feeds_meta = {
            "source": "recent_posts",
            "count": len(posts),
            "parsed_count": len(all_posts),
            "http_status": payload.get("_http_status"),
            "raw_length": payload.get("_raw_length"),
            "has_more": self._friend_feeds_has_more(payload, all_posts),
            "next_cursor": self._friend_feeds_next_cursor(payload),
            **payload_meta,
        }
        self._remember_posts(posts)
        return posts

    async def query_friend_feeds(
        self,
        *,
        pos: int = 0,
        num: int = 5,
        with_detail: bool = False,
        cursor: str = "",
    ) -> list[QzonePost]:
        return await self.query_recent_posts(pos=pos, num=num, with_detail=with_detail, cursor=cursor)

    async def _query_recent_post_details(self, posts: list[QzonePost]) -> list[QzonePost]:
        detailed = []
        for post in posts:
            try:
                detail = await self.detail(post.key)
                detail.feed_key = detail.feed_key or post.feed_key
                detail.curkey = detail.curkey or post.curkey
                detail.unikey = detail.unikey or post.unikey
                detail.busi_param = detail.busi_param or post.busi_param
                detailed.append(detail)
            except Exception:
                detailed.append(post)
        return detailed

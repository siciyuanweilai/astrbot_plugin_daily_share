from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...concurrency import KeyedLocks
from ..models import QzonePost
from ..parse import parse_feed_item
from ..parse.photo import photo_thread_comments
from ..photobatch import refresh_batch_comments

if TYPE_CHECKING:
    from ..qzone import QzoneService


class QzoneFeedDetailService:
    """说说详情查询。"""

    def __init__(self, owner: QzoneService) -> None:
        self.owner = owner
        self._locks = KeyedLocks()
        self._slots = asyncio.Semaphore(3)

    async def detail(self, post_id: str) -> QzonePost:
        post = self.owner._require_post(post_id)
        scope = self.owner._cache_bot
        async with self._locks.hold((id(scope), post.key)):
            self._ensure_scope(scope)
            cached = self.owner._cached_detail_post(post.key)
            if cached is not None:
                return cached
            async with self._slots:
                self._ensure_scope(scope)
                post = self.owner._require_post(post.key)
                revision = self.owner._cache_revision
                result = await self._fetch_detail(post)
            self._ensure_scope(scope)
            # 评论或删除等写入期间取得的旧详情不能恢复已失效缓存。
            # 整组照片由补读方法按实际成功结果管理详情标记，失败仍返回原动态。
            if revision == self.owner._cache_revision and not (
                int(post.appid or 311) == 4 and post.photo_comment_scope == "batch"
            ):
                self.owner._remember_posts([result], detailed=True)
            return result

    def _ensure_scope(self, scope) -> None:
        self.owner._ensure_bot_cache_scope()
        if scope is not self.owner._cache_bot:
            raise RuntimeError("QQ 空间实例已变化，请重新读取动态")

    async def _fetch_detail(self, post: QzonePost) -> QzonePost:
        if int(post.appid or 311) != 311:
            if int(post.appid) == 4 and post.photo_comment_scope == "batch":
                return await refresh_batch_comments(self.owner, post)
            if (
                int(post.appid) == 4
                and post.photo_comment_scope != "batch"
                and not post.comment_target_error
            ):
                target = post.photo_targets[0]
                photo = await self.owner.query_photo(
                    owner_uin=post.uin,
                    album_id=target.album_id,
                    pic_key=target.pic_key,
                    comment_count=50,
                )
                photo.feed_topic_id = target.feed_topic_id
                photo.batch_id = photo.batch_id or target.batch_id
                post.photo_targets = [photo]
                comments = photo_thread_comments(photo)
                canonical = {
                    (
                        item.raw_tid,
                        item.uin,
                        item.raw_fields.get("photo_root_id", ""),
                    ): item
                    for item in comments
                }
                post.comments = [
                    canonical.get(
                        (
                            item.raw_tid,
                            item.uin,
                            item.raw_fields.get("photo_root_id", ""),
                        ),
                        item,
                    )
                    for item in self.owner._merge_comments(post.comments, comments)
                ]
            return post

        ctx = await self.owner.context()
        referer = f"{self.owner.BASE_URL}/{post.uin}/mood/{post.tid}"
        attempts = (
            (
                "POST",
                self.owner.DETAIL_URL,
                {"g_tk": ctx.gtk2},
                {
                    "uin": post.uin,
                    "tid": post.tid,
                    "format": "json",
                    "hostuin": ctx.uin,
                    "qzreferrer": referer,
                },
            ),
            (
                "GET",
                self.owner.DETAIL_URL,
                {
                    "g_tk": ctx.gtk2,
                    "uin": post.uin,
                    "tid": post.tid,
                    "format": "json",
                    "hostuin": ctx.uin,
                    "qzreferrer": referer,
                },
                None,
            ),
            (
                "GET",
                self.owner.DETAIL_H5_URL,
                {
                    "uin": post.uin,
                    "tid": post.tid,
                    "num": 100,
                    "pos": 0,
                    "not_trunc_con": 1,
                    "format": "json",
                    "g_tk": ctx.gtk2,
                },
                None,
            ),
        )
        last_message = ""
        parsed = None
        for method, url, params, data in attempts:
            payload = await self.owner._request(
                method,
                url,
                params=params,
                data=data,
                headers=self.owner._headers(ctx, Referer=referer),
                retry_parse_error=False,
            )
            if not self.owner._ok(payload):
                last_message = str(
                    payload.get("message")
                    or payload.get("msg")
                    or "获取 QQ 空间详情失败"
                )
                continue
            parsed = self.owner._parse_detail_post(payload)
            if parsed:
                break
        if not parsed:
            raise RuntimeError(last_message or "QQ 空间详情解析失败")
        parsed = self.owner._merge_post_detail(post, parsed)
        return parsed

    @staticmethod
    def _parse_detail_post(payload: dict[str, Any]) -> QzonePost | None:
        candidates: list[dict[str, Any]] = []

        def add(candidate: Any) -> None:
            if isinstance(candidate, dict):
                candidates.append(candidate)
            elif isinstance(candidate, list):
                for item in candidate:
                    if isinstance(item, dict):
                        candidates.append(item)
                        break

        data = payload.get("data") if isinstance(payload, dict) else None
        result = payload.get("result") if isinstance(payload, dict) else None
        add(payload)
        add(data)
        if isinstance(data, dict):
            add(data.get("data"))
            add(data.get("detail"))
            add(data.get("msglist"))
        add(result)
        if isinstance(result, dict):
            add(result.get("data"))
            add(result.get("detail"))
            add(result.get("post"))
            add(result.get("msglist"))
        add(payload.get("detail") if isinstance(payload, dict) else None)
        add(payload.get("msglist") if isinstance(payload, dict) else None)

        for candidate in candidates:
            parsed = parse_feed_item(candidate)
            if parsed:
                return parsed
        return None

    async def _safe_post_detail(self, post: QzonePost) -> QzonePost | None:
        try:
            return await self.owner.detail(post.key)
        except Exception:
            return None

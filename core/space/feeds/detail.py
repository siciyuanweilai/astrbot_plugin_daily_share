from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..models import QzonePost
from ..parse import parse_feed_item
from ..parse.photo import photo_thread_comments

if TYPE_CHECKING:
    from ..qzone import QzoneService


class QzoneFeedDetailService:
    """说说详情查询。"""

    def __init__(self, owner: QzoneService) -> None:
        self.owner = owner

    async def detail(self, post_id: str) -> QzonePost:
        post = self.owner._require_post(post_id)
        cached = self.owner._cached_detail_post(post.key)
        if cached is not None:
            return cached
        if int(post.appid or 311) != 311:
            if int(post.appid) == 4 and not post.comment_target_error:
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
            self.owner._remember_posts([post], detailed=True)
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
        self.owner._remember_posts([parsed], detailed=True)
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

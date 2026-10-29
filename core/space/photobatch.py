from __future__ import annotations

from astrbot.api import logger

from .models import QzoneComment, QzonePost
from .parse.photo import resolve_photo_comment_thread
from .parse.thread import _feed_html_comment_items, parse_comments


def batch_comments(post: QzonePost, comments: list[QzoneComment]) -> list[QzoneComment]:
    """整批和单张评论可能混在一个响应中，只保留原楼明确绑定的整批评论。"""
    topic = post.photo_batch_topic_id

    def bound(comment: QzoneComment) -> bool:
        fields = comment.raw_fields or {}
        return (
            fields.get("photo_topic_id") == topic
            and fields.get("photo_owner_uin") == post.uin
            and fields.get("photo_private") in (0, "0")
        )

    roots = [
        comment
        for comment in comments
        if not comment.parent_tid and not comment.reply_to_tid and bound(comment)
    ]
    replies: dict[str, list[QzoneComment]] = {}
    for comment in comments:
        if comment.parent_tid and bound(comment):
            replies.setdefault(comment.parent_tid, []).append(comment)
    return [
        comment
        for root in roots
        for comment in resolve_photo_comment_thread(root, replies.get(root.tid, []))
    ]


async def refresh_batch_comments(service, post: QzonePost) -> QzonePost:
    if post.photo_comment_scope != "batch" or post.comment_target_error:
        raise RuntimeError("相册整组评论缺少已核实的上传批次")
    cached = service._cached_detail_post(post.key)
    if cached is not None and cached.photo_batch_topic_id == post.photo_batch_topic_id:
        post.comments = batch_comments(post, cached.comments)
        return post
    scope, revision = service._cache_bot, service._cache_revision
    complete = False
    post.comments = batch_comments(post, post.comments)
    try:
        ctx = await service.context()
        # 与 QQ 空间 comment.js 的“更多评论”请求一致。feedsType=8 和
        # isfakereq=1 表示只读；此接口虽名为 add，查询时不能附带 content。
        payload = await service._request(
            "POST",
            service.PHOTO_COMMENT_URL,
            params={"g_tk": ctx.gtk},
            data={
                "topicId": post.photo_batch_topic_id,
                "feedsType": 8,
                "hostUin": post.uin,
                "uin": ctx.uin,
                "start": 0,
                "sort": 1,
                "num": 20,
                "format": "fs",
                "ref": "feeds",
                "isfakereq": 1,
                "paramstr": 1,
                "inCharset": "utf-8",
                "outCharset": "utf-8",
                "plat": "qzone",
                "source": "ic",
            },
            headers=service._headers(ctx, Referer=f"{service.BASE_URL}/{post.uin}"),
            retry_parse_error=False,
        )
        data = payload.get("data")
        if (
            not service._ok(payload)
            or not isinstance(data, dict)
            or not isinstance(data.get("feeds"), str)
        ):
            raise RuntimeError("整组照片评论详情不可用")
        post.comments = batch_comments(
            post, parse_comments(_feed_html_comment_items(data["feeds"]))
        )
        complete = True
    except RuntimeError as exc:
        logger.debug(f"[日常分享] 整组照片评论补读失败，保留动态自带评论: {exc}")
    service._ensure_bot_cache_scope()
    if scope is service._cache_bot and revision == service._cache_revision:
        service._remember_posts([post], detailed=complete)
    return post

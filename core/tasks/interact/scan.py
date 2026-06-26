from astrbot.api import logger

from ...space.merge import QzoneFeedMergeMixin
from .task import _qzone_service


async def _query_qzone_mention_posts(owner, *, fetch_count: int) -> list:
    service = _qzone_service(owner)
    method = getattr(service, "query_mention_posts", None)
    if not callable(method):
        return []
    try:
        return list(await method(offset=0, count=fetch_count, with_detail=True) or [])
    except Exception as exc:
        logger.debug(f"[每日分享] QQ 空间自动互动查询 @我动态失败: {exc}")
        return []


def _merge_qzone_posts_by_key(*post_groups: list) -> list:
    merged = []
    index_by_key: dict[str, int] = {}
    for posts in post_groups:
        for post in posts or []:
            key = str(getattr(post, "key", "") or "").strip()
            if key and key in index_by_key:
                merged[index_by_key[key]] = QzoneFeedMergeMixin._merge_post_detail(merged[index_by_key[key]], post)
                continue
            if key:
                index_by_key[key] = len(merged)
            merged.append(post)
    return merged


async def _query_qzone_friend_posts(
    owner,
    *,
    fetch_count: int,
    suppress_errors: bool = False,
    debug_label: str = "自动互动",
) -> list:
    service = _qzone_service(owner)
    method = getattr(service, "query_recent_posts", None)
    if not callable(method):
        method = getattr(service, "query_friend_feeds", None)
    if not callable(method):
        return []
    try:
        mention_posts = await _query_qzone_mention_posts(owner, fetch_count=fetch_count)
        friend_posts = list(await method(pos=0, num=fetch_count, with_detail=True) or [])
        return _merge_qzone_posts_by_key(mention_posts, friend_posts)
    except Exception as exc:
        if suppress_errors:
            logger.debug(f"[每日分享] QQ 空间{debug_label}查询好友动态失败: {exc}")
            return []
        raise

from astrbot.api import logger

from .task import _qzone_service


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
        return list(await method(pos=0, num=fetch_count, with_detail=True) or [])
    except Exception as exc:
        if suppress_errors:
            logger.debug(f"[每日分享] QQ 空间{debug_label}查询好友动态失败: {exc}")
            return []
        raise

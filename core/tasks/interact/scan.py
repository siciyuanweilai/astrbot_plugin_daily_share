from astrbot.api import logger

from ...space.merge import QzoneFeedMergeService
from .task import _qzone_service


async def _query_qzone_mention_posts(owner, *, fetch_count: int) -> list:
    service = _qzone_service(owner)
    try:
        return list(
            await service.query_mention_posts(
                offset=0, count=fetch_count, with_detail=True
            )
            or []
        )
    except Exception as exc:
        logger.debug(f"[日常分享] QQ 空间自动互动查询 @我动态失败: {exc}")
        return []


def _merge_qzone_posts_by_key(*post_groups: list) -> list:
    merged: list = []
    index_by_key: dict[str, int] = {}
    for posts in post_groups:
        for post in posts or []:
            key = str(getattr(post, "key", "") or "").strip()
            if key and key in index_by_key:
                merged[index_by_key[key]] = QzoneFeedMergeService._merge_post_detail(
                    merged[index_by_key[key]], post
                )
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
    try:
        mention_posts = await _query_qzone_mention_posts(owner, fetch_count=fetch_count)
        friend_posts = list(
            await service.query_recent_posts(pos=0, num=fetch_count, with_detail=True)
            or []
        )
        return _merge_qzone_posts_by_key(mention_posts, friend_posts)
    except Exception as exc:
        if suppress_errors:
            logger.debug(f"[日常分享] QQ 空间{debug_label}查询好友动态失败: {exc}")
            return []
        raise


async def _query_qzone_self_album_posts(owner, *, self_uin: int) -> list:
    service = _qzone_service(owner)
    if not callable(getattr(service, "query_recent_posts", None)):
        return []
    try:
        recent = await service.query_recent_posts(pos=0, num=20, with_detail=False)
    except Exception as exc:
        logger.debug(f"[日常分享] QQ 空间相册自动回评查询动态失败: {exc}")
        return []
    photos = []
    seen_targets: set[str] = set()
    for post in recent or []:
        if (
            int(getattr(post, "uin", 0) or 0) != self_uin
            or int(getattr(post, "appid", 311) or 311) != 4
        ):
            continue
        multiple = len(post.photo_targets) > 1
        needs_verification = bool(post.comment_target_error) and bool(
            post.photo_targets
        )
        if (
            post.comment_target_error
            and not multiple
            and not (
                needs_verification
                and callable(getattr(service, "query_photo_posts", None))
            )
        ):
            logger.debug(
                f"[日常分享] QQ 空间相册自动回评跳过: {post.comment_target_error}"
            )
            continue
        photo_keys = {photo.key for photo in post.photo_targets}
        if photo_keys <= seen_targets:
            continue
        try:
            targets = (
                await service.query_photo_posts(post.key)
                if multiple or needs_verification
                else [await service.detail(post.key)]
            )
            for target in targets:
                photo_key = target.photo_targets[0].key
                if photo_key not in seen_targets:
                    photos.append(target)
                    seen_targets.add(photo_key)
        except Exception as exc:
            logger.debug(f"[日常分享] QQ 空间相册自动回评读取照片评论失败: {exc}")
    return photos


async def _expand_qzone_photo_posts(owner, posts: list) -> list:
    service = _qzone_service(owner)
    expanded = []
    for post in posts or []:
        if (
            int(getattr(post, "appid", 311) or 311) != 4
            or (
                len(getattr(post, "photo_targets", []) or []) <= 1
                and not getattr(post, "comment_target_error", "")
            )
            or not callable(getattr(service, "query_photo_posts", None))
        ):
            expanded.append(post)
            continue
        try:
            expanded.extend(await service.query_photo_posts(post.key))
        except Exception as exc:
            logger.debug(f"[日常分享] QQ 空间批量相册目标读取失败，跳过自动选择: {exc}")
            expanded.append(post)
    return _merge_qzone_posts_by_key(expanded)

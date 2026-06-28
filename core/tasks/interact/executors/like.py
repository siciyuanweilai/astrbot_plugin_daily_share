import asyncio

from astrbot.api import logger

from ..scan import _query_qzone_friend_posts
from ..task import (
    _qzone_abort_query_failure,
    _qzone_auto_config,
    _qzone_auto_result,
    _qzone_finish_task,
    _qzone_is_retry_later_error,
    _qzone_mark_result_rate_limited,
    _qzone_prepare_task,
    _qzone_query_fetch_count,
)
from ..tracker import (
    QZONE_ACTION_LIKED,
    QZONE_AUTO_LIKE_DEFAULT_COOLDOWN_HOURS,
    QZONE_AUTO_LIKE_POLICY_VERSION,
    QZONE_AUTO_LIKE_STATE_KEY,
    _mark_qzone_post_processed,
    _post_alias_keys,
    _post_key,
)
from .pacing import QZONE_ACTION_DELAY_SECONDS


async def execute_qzone_auto_like_task(owner, *, emit_summary: bool = True) -> dict:
    """查询好友动态并自动点赞，返回本次执行统计。"""
    result = _qzone_auto_result(liked=0)
    cfg = _qzone_auto_config(owner)
    limit = cfg.like_limit
    ready, state, processed, now = await _qzone_prepare_task(
        owner,
        result=result,
        enabled=cfg.enable_like,
        state_key=QZONE_AUTO_LIKE_STATE_KEY,
        cooldown_hours=QZONE_AUTO_LIKE_DEFAULT_COOLDOWN_HOURS,
        disabled_log="[每日分享] QQ 空间自动点赞未开启，跳过。",
    )
    if not ready:
        return result

    try:
        ctx = await owner.plugin.qzone_service.context()
        fetch_count = _qzone_query_fetch_count(limit, 4)
        posts = await _query_qzone_friend_posts(owner, fetch_count=fetch_count)
    except Exception as exc:
        return await _qzone_abort_query_failure(
            owner,
            state_key=QZONE_AUTO_LIKE_STATE_KEY,
            state=state,
            processed=processed,
            result=result,
            run_at=now,
            message="[每日分享] QQ 空间自动点赞查询失败",
            error=exc,
        )

    seen_post_keys: set[str] = set()
    for post in posts:
        if result["liked"] >= limit:
            break
        result["scanned"] += 1
        post_key = _post_key(post)
        post_aliases = set(_post_alias_keys(post))
        if post_aliases and post_aliases & seen_post_keys:
            result["skipped"] += 1
            continue
        seen_post_keys.update(post_aliases)
        if not owner._qzone_auto_like_candidate(post, self_uin=ctx.uin, processed=processed):
            result["skipped"] += 1
            continue

        try:
            await owner.plugin.qzone_service.like(post_key)
            _mark_qzone_post_processed(
                processed,
                post,
                QZONE_ACTION_LIKED,
                author=str(getattr(post, "name", "") or getattr(post, "uin", "") or ""),
                policy_version=QZONE_AUTO_LIKE_POLICY_VERSION,
            )
            result["liked"] += 1
            owner.plugin._page_emit_dashboard_event(
                "qzone",
                {"action": "auto_like", "post_id": post_key},
            )
            logger.info(
                f"[每日分享] 已自动点赞 QQ 空间动态: "
                f"{getattr(post, 'name', '') or getattr(post, 'uin', '')}"
            )
            await asyncio.sleep(QZONE_ACTION_DELAY_SECONDS)
        except Exception as exc:
            if _qzone_is_retry_later_error(exc):
                result["skipped"] += 1
                _qzone_mark_result_rate_limited(result, exc)
                logger.debug(f"[每日分享] QQ 空间自动点赞稍后重试: {exc}")
                break
            result["failed"] += 1
            logger.warning(f"[每日分享] QQ 空间自动点赞失败: {exc}")

    await _qzone_finish_task(
        owner,
        state_key=QZONE_AUTO_LIKE_STATE_KEY,
        state=state,
        processed=processed,
        result=result,
        emit_summary=emit_summary,
        task_label="自动点赞",
        count_label="点赞",
        count_key="liked",
        success_keys=("liked",),
    )
    return result

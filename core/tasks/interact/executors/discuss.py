import asyncio

from astrbot.api import logger

from ..candidate import _qzone_friend_thread_comment_candidates
from ..comments import QzoneCommentIndex
from ..errors import QzoneAutoInteractionRateLimited
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
    QZONE_ACTION_COMMENTED,
    QZONE_ACTION_RETRY_LATER,
    QZONE_ACTION_SKIPPED,
    QZONE_ACTION_THREAD_COMMENTED,
    QZONE_AUTO_COMMENT_DEFAULT_COOLDOWN_HOURS,
    QZONE_AUTO_COMMENT_STATE_KEY,
    _mark_qzone_post_processed,
    _mark_qzone_processed,
    _post_alias_keys,
    _qzone_pending_reply,
)
from .pacing import QZONE_ACTION_DELAY_SECONDS


async def _execute_qzone_auto_comment_thread_reply(
    owner,
    posts: list,
    ctx,
    state: dict,
    processed: dict,
    result: dict,
    *,
    limit: int,
) -> set[str]:
    paused = False
    replied_post_keys: set[str] = set()
    for candidate in _qzone_friend_thread_comment_candidates(
        owner,
        posts,
        self_uin=ctx.uin,
        processed=processed,
    ):
        if result["commented"] >= limit or paused:
            break
        post = candidate.post
        comment = candidate.comment
        parent_comment = candidate.parent_comment
        item_key = candidate.item_key
        result["scanned"] += 1
        pending_reply = _qzone_pending_reply(processed, item_key)
        if pending_reply:
            reply = pending_reply
        else:
            try:
                reply = await owner._generate_qzone_auto_reply_thread(post, parent_comment, comment)
            except Exception as exc:
                result["failed"] += 1
                result["generation_failed"] += 1
                logger.warning(f"[每日分享] QQ 空间好友动态自动续评生成失败: {exc}")
                continue
        try:
            await owner._qzone_send_auto_reply_result(
                post,
                comment,
                processed,
                result,
                item_key=item_key,
                reply=reply,
                processed_action=QZONE_ACTION_THREAD_COMMENTED,
                dashboard_action="auto_comment",
                log_label="已自动续评 QQ 空间好友动态",
                parent_comment_id=str(getattr(parent_comment, "tid", "") or ""),
                parent_comment=parent_comment,
                result_count_key="commented",
            )
            post_key = str(getattr(post, "key", "") or "").strip()
            if post_key:
                replied_post_keys.add(post_key)
        except QzoneAutoInteractionRateLimited as exc:
            paused = True
            result["skipped"] += 1
            _qzone_mark_result_rate_limited(result, exc)
            logger.debug(f"[每日分享] QQ 空间好友动态自动续评稍后重试: {exc}")
        except Exception as exc:
            result["failed"] += 1
            logger.warning(f"[每日分享] QQ 空间好友动态自动续评失败: {exc}")
    return replied_post_keys


async def _execute_qzone_auto_comment_new_posts(
    owner,
    posts: list,
    ctx,
    state: dict,
    processed: dict,
    result: dict,
    *,
    limit: int,
    skip_post_keys: set[str] | None = None,
) -> None:
    skip_post_keys = skip_post_keys or set()
    for post in posts:
        if result["commented"] >= limit:
            break
        if str(getattr(post, "key", "") or "").strip() in skip_post_keys:
            continue
        result["scanned"] += 1
        post_key = str(getattr(post, "key", "") or "").strip()
        comment_index = QzoneCommentIndex.build(post, ctx.uin)
        if not owner._qzone_auto_comment_candidate(
            post,
            self_uin=ctx.uin,
            processed=processed,
            index=comment_index,
        ):
            result["skipped"] += 1
            continue

        pending_comment = next(
            (reply for reply in (_qzone_pending_reply(processed, key) for key in _post_alias_keys(post)) if reply),
            "",
        )
        if pending_comment:
            comment = pending_comment
        else:
            try:
                comment = await owner._generate_qzone_auto_comment(post, state=state)
            except Exception as exc:
                result["failed"] += 1
                result["generation_failed"] += 1
                logger.warning(f"[每日分享] QQ 空间自动评论生成失败: {exc}")
                continue
        try:
            if not comment:
                _mark_qzone_processed(processed, post_key, QZONE_ACTION_SKIPPED)
                result["skipped"] += 1
                continue
            await owner.plugin.qzone_service.comment(post_key, comment)
            _mark_qzone_post_processed(
                processed,
                post,
                QZONE_ACTION_COMMENTED,
                content=comment,
                post_key=post_key,
                post_uin=int(getattr(post, "uin", 0) or 0),
                post_tid=str(getattr(post, "tid", "") or ""),
                author=str(getattr(post, "name", "") or getattr(post, "uin", "") or ""),
            )
            result["commented"] += 1
            owner.plugin._page_emit_dashboard_event(
                "qzone",
                {"action": "auto_comment", "post_id": post_key},
            )
            logger.info(
                f"[每日分享] 已自动评论 QQ 空间动态: "
                f"{getattr(post, 'name', '') or getattr(post, 'uin', '')}"
            )
            await asyncio.sleep(QZONE_ACTION_DELAY_SECONDS)
        except Exception as exc:
            if _qzone_is_retry_later_error(exc):
                _mark_qzone_post_processed(
                    processed,
                    post,
                    QZONE_ACTION_RETRY_LATER,
                    content=comment,
                    post_key=post_key,
                    post_uin=int(getattr(post, "uin", 0) or 0),
                    post_tid=str(getattr(post, "tid", "") or ""),
                    author=str(getattr(post, "name", "") or getattr(post, "uin", "") or ""),
                    reason=str(exc),
                )
                result["skipped"] += 1
                _qzone_mark_result_rate_limited(result, exc)
                logger.debug(f"[每日分享] QQ 空间自动评论稍后重试: {exc}")
                break
            result["failed"] += 1
            logger.warning(f"[每日分享] QQ 空间自动评论失败: {exc}")


async def execute_qzone_auto_comment_task(owner, *, emit_summary: bool = True) -> dict:
    """查询好友动态并自动评论，返回本次执行统计。"""
    result = _qzone_auto_result(commented=0)
    cfg = _qzone_auto_config(owner)
    limit = cfg.comment_limit
    ready, state, processed, now = await _qzone_prepare_task(
        owner,
        result=result,
        enabled=cfg.enable_comment,
        state_key=QZONE_AUTO_COMMENT_STATE_KEY,
        cooldown_hours=QZONE_AUTO_COMMENT_DEFAULT_COOLDOWN_HOURS,
        disabled_log="[每日分享] QQ 空间自动评论未开启，跳过。",
    )
    if not ready:
        return result

    try:
        ctx = await owner.plugin.qzone_service.context()
        fetch_count = _qzone_query_fetch_count(limit, 3)
        posts = await _query_qzone_friend_posts(owner, fetch_count=fetch_count)
    except Exception as exc:
        return await _qzone_abort_query_failure(
            owner,
            state_key=QZONE_AUTO_COMMENT_STATE_KEY,
            state=state,
            processed=processed,
            result=result,
            run_at=now,
            message="[每日分享] QQ 空间自动评论查询失败",
            error=exc,
        )

    thread_replied_post_keys = await _execute_qzone_auto_comment_thread_reply(
        owner,
        posts,
        ctx,
        state,
        processed,
        result,
        limit=limit,
    )

    await _execute_qzone_auto_comment_new_posts(
        owner,
        posts,
        ctx,
        state,
        processed,
        result,
        limit=limit,
        skip_post_keys=thread_replied_post_keys,
    )

    await _qzone_finish_task(
        owner,
        state_key=QZONE_AUTO_COMMENT_STATE_KEY,
        state=state,
        processed=processed,
        result=result,
        emit_summary=emit_summary,
        task_label="自动评论",
        count_label="评论",
        count_key="commented",
        success_keys=("commented",),
    )
    return result

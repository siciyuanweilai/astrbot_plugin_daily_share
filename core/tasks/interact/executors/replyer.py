from astrbot.api import logger

from ..candidate import _qzone_self_reply_candidates
from ..errors import QzoneAutoInteractionRateLimited
from ..task import (
    _mark_current_qzone_rate_limited,
    _qzone_abort_query_failure,
    _qzone_auto_config,
    _qzone_auto_result,
    _qzone_finish_task,
    _qzone_prepare_task,
    _qzone_query_fetch_count,
)
from ..tracker import (
    QZONE_ACTION_REPLIED,
    QZONE_ACTION_THREAD_REPLIED,
    QZONE_AUTO_REPLY_DEFAULT_COOLDOWN_HOURS,
    QZONE_AUTO_REPLY_STATE_KEY,
    _qzone_pending_reply,
)


async def _execute_qzone_auto_reply_candidates(
    owner,
    candidates: list,
    state: dict,
    processed: dict,
    result: dict,
    *,
    limit: int,
) -> None:
    paused = False
    for candidate in candidates:
        if result["replied"] >= limit or paused:
            break
        post = candidate.post
        comment = candidate.comment
        parent_comment = candidate.parent_comment
        item_key = candidate.item_key
        is_thread_reply = candidate.is_thread_reply
        pending_reply = _qzone_pending_reply(processed, item_key)
        if pending_reply:
            reply = pending_reply
        else:
            try:
                reply = (
                    await owner._generate_qzone_auto_reply_thread(post, parent_comment, comment)
                    if is_thread_reply
                    else await owner._generate_qzone_auto_reply(post, comment)
                )
            except Exception as exc:
                result["failed"] += 1
                result["generation_failed"] += 1
                logger.warning(f"[每日分享] QQ 空间自动回评生成失败: {exc}")
                continue

        try:
            await owner._qzone_send_auto_reply_result(
                post,
                comment,
                processed,
                result,
                item_key=item_key,
                reply=reply,
                processed_action=QZONE_ACTION_THREAD_REPLIED if is_thread_reply else QZONE_ACTION_REPLIED,
                dashboard_action="auto_reply",
                log_label="已自动回评 QQ 空间评论",
                parent_comment_id=(
                    str(getattr(parent_comment, "tid", "") or "") if is_thread_reply else ""
                ),
                parent_comment=parent_comment if is_thread_reply else None,
            )
        except QzoneAutoInteractionRateLimited as exc:
            paused = True
            result["skipped"] += 1
            _mark_current_qzone_rate_limited(owner, state, exc)
            logger.debug(f"[每日分享] QQ 空间自动回评稍后重试: {exc}")
            break
        except Exception as exc:
            result["failed"] += 1
            logger.warning(f"[每日分享] QQ 空间自动回评失败: {exc}")


async def execute_qzone_auto_reply_task(owner, *, emit_summary: bool = True) -> dict:
    """查询自己的说说评论并自动回评，返回本次执行统计。"""
    result = _qzone_auto_result(replied=0)
    cfg = _qzone_auto_config(owner)
    limit = cfg.reply_limit
    ready, state, processed, now = await _qzone_prepare_task(
        owner,
        result=result,
        enabled=cfg.enable_reply,
        state_key=QZONE_AUTO_REPLY_STATE_KEY,
        cooldown_hours=QZONE_AUTO_REPLY_DEFAULT_COOLDOWN_HOURS,
        disabled_log="[每日分享] QQ 空间自动回评未开启，跳过。",
    )
    if not ready:
        return result
    try:
        ctx = await owner.plugin.qzone_service.context()
        fetch_count = _qzone_query_fetch_count(limit, 3)
        posts = await owner.plugin.qzone_service.query_posts(
            target_id=str(ctx.uin),
            pos=0,
            num=fetch_count,
            with_detail=True,
        )
    except Exception as exc:
        return await _qzone_abort_query_failure(
            owner,
            state_key=QZONE_AUTO_REPLY_STATE_KEY,
            state=state,
            processed=processed,
            result=result,
            run_at=now,
            message="[每日分享] QQ 空间自动回评查询失败",
            error=exc,
        )

    candidates = _qzone_self_reply_candidates(
        owner,
        posts,
        self_uin=ctx.uin,
        processed=processed,
        result=result,
    )
    await _execute_qzone_auto_reply_candidates(
        owner,
        candidates,
        state,
        processed,
        result,
        limit=limit,
    )

    await _qzone_finish_task(
        owner,
        state_key=QZONE_AUTO_REPLY_STATE_KEY,
        state=state,
        processed=processed,
        result=result,
        emit_summary=emit_summary,
        task_label="自动回评",
        count_label="回评",
        count_key="replied",
        success_keys=("replied",),
    )
    return result

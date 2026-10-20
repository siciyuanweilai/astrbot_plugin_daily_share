import asyncio
import random
from dataclasses import replace

from astrbot.api import logger

from ..candidate import _qzone_friend_thread_comment_candidates
from ..comments import QzoneCommentIndex
from ..errors import QzoneAutoInteractionRateLimited
from ..receipt import record_qzone_interaction
from ..scan import _expand_qzone_photo_posts, _query_qzone_friend_posts
from ..task import (
    QzoneStatePersistenceError,
    _qzone_abort_query_failure,
    _qzone_auto_config,
    _qzone_auto_result,
    _qzone_finish_task,
    _qzone_is_retry_later_error,
    _qzone_mark_result_rate_limited,
    _qzone_prepare_task,
    _qzone_query_fetch_count,
    _qzone_result_rate_limited,
    checkpoint_qzone_action,
)
from ..tracker import (
    QZONE_ACTION_COMMENT_REPLIED,
    QZONE_ACTION_COMMENTED,
    QZONE_ACTION_RETRY_LATER,
    QZONE_ACTION_SKIPPED,
    QZONE_ACTION_THREAD_COMMENTED,
    QZONE_AUTO_COMMENT_DEFAULT_COOLDOWN_HOURS,
    QZONE_AUTO_COMMENT_STATE_KEY,
    _comment_key,
    _mark_qzone_post_processed,
    _mark_qzone_processed,
    _photo_batch_key,
    _post_alias_keys,
    _qzone_pending_reply,
)
from .pacing import QZONE_ACTION_DELAY_SECONDS


def _qzone_auto_comment_batch_posts(post, posts: list) -> list:
    batch_key = _photo_batch_key(post)
    if not batch_key or post.comment_target_error:
        return [post]
    return sorted(
        (
            item
            for item in posts
            if _photo_batch_key(item) == batch_key
            and item.uin == post.uin
            and not item.comment_target_error
            and item.photo_batch_complete
        ),
        key=lambda item: item.photo_targets[0].key,
    )


def _qzone_auto_comment_generation_post(post, posts: list):
    batch_posts = _qzone_auto_comment_batch_posts(post, posts)
    images = list(dict.fromkeys(image for item in batch_posts for image in item.images))
    # 仅生成文案时使用整批图片，缓存中的评论提交与回评目标仍按照片隔离。
    return replace(post, images=images) if images != post.images else post


def _qzone_auto_comment_reply_target(
    owner,
    posts: list,
    ctx,
    processed: dict,
    *,
    probability: int,
    skip_post_keys: set[str],
):
    candidates = []
    for post in posts:
        if post.key in skip_post_keys:
            continue
        index = QzoneCommentIndex.build(post, ctx.uin)
        for comment_index, comment in enumerate(index.comments):
            if not owner._qzone_auto_comment_reply_candidate(
                post,
                comment,
                self_uin=ctx.uin,
                processed=processed,
                index=index,
            ):
                continue
            item_key = _comment_key(post, comment)
            candidates.append(
                (
                    bool(_qzone_pending_reply(processed, item_key)),
                    int(getattr(comment, "create_time", 0) or 0),
                    comment_index,
                    post,
                    comment,
                    item_key,
                )
            )
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[:3], reverse=True)
    pending = next((item for item in candidates if item[0]), None)
    if pending:
        return pending[3:]
    if not probability:
        return None
    if random.random() * 100 >= max(0, min(100, int(probability or 0))):
        return None
    selected = candidates[0]
    return selected[3:]


async def _execute_qzone_auto_comment_reply(
    owner,
    post,
    comment,
    item_key: str,
    state: dict,
    processed: dict,
    result: dict,
    *,
    self_uin: int,
    target_umo: str = "",
) -> bool:
    reply = _qzone_pending_reply(processed, item_key)
    if not reply:
        try:
            reply = await owner._generate_qzone_auto_reply(
                post,
                comment,
                state=state,
                target_umo=target_umo,
                as_post_owner=False,
                self_uin=self_uin,
            )
        except Exception as exc:
            result["failed"] += 1
            result["generation_failed"] += 1
            logger.warning(f"[日常分享] QQ 空间好友评论回评生成失败: {exc}")
            return False
    try:
        await owner._qzone_send_auto_reply_result(
            post,
            comment,
            processed,
            result,
            item_key=item_key,
            reply=reply,
            processed_action=QZONE_ACTION_COMMENT_REPLIED,
            dashboard_action="auto_comment",
            log_label="已自动回复好友动态评论",
            state=state,
            state_key=QZONE_AUTO_COMMENT_STATE_KEY,
            parent_comment_id="",
            parent_comment=None,
            result_count_key="commented",
            processed_post_action=QZONE_ACTION_COMMENT_REPLIED,
        )
    except QzoneStatePersistenceError:
        raise
    except QzoneAutoInteractionRateLimited as exc:
        result["skipped"] += 1
        _qzone_mark_result_rate_limited(result, exc)
        logger.debug(f"[日常分享] QQ 空间好友评论回评稍后重试: {exc}")
        return True
    except Exception as exc:
        result["failed"] += 1
        logger.warning(f"[日常分享] QQ 空间好友评论回评失败: {exc}")
        return False
    return False


async def _execute_qzone_auto_comment_thread_reply(
    owner,
    posts: list,
    ctx,
    state: dict,
    processed: dict,
    result: dict,
    *,
    limit: int,
    target_umo: str = "",
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
                reply = await owner._generate_qzone_auto_reply_thread(
                    post,
                    parent_comment,
                    comment,
                    state=state,
                    target_umo=target_umo,
                )
            except Exception as exc:
                result["failed"] += 1
                result["generation_failed"] += 1
                logger.warning(f"[日常分享] QQ 空间好友动态自动续评生成失败: {exc}")
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
                state=state,
                state_key=QZONE_AUTO_COMMENT_STATE_KEY,
                parent_comment_id=str(getattr(parent_comment, "tid", "") or ""),
                parent_comment=parent_comment,
                result_count_key="commented",
            )
            post_key = str(getattr(post, "key", "") or "").strip()
            if post_key:
                replied_post_keys.add(post_key)
        except QzoneStatePersistenceError:
            raise
        except QzoneAutoInteractionRateLimited as exc:
            paused = True
            result["skipped"] += 1
            _qzone_mark_result_rate_limited(result, exc)
            logger.debug(f"[日常分享] QQ 空间好友动态自动续评稍后重试: {exc}")
        except Exception as exc:
            result["failed"] += 1
            logger.warning(f"[日常分享] QQ 空间好友动态自动续评失败: {exc}")
    return replied_post_keys


async def _submit_qzone_auto_comment(
    owner,
    post,
    comment: str,
    photo_key: str,
    state: dict,
    processed: dict,
    result: dict,
) -> bool:
    """仅捕获提交异常；已确认的动作落库后才执行联动和回执。

    返回 True 表示触发限流，需要结束本轮提交。
    """
    post_key = post.key
    if not comment:
        _mark_qzone_processed(processed, post_key, QZONE_ACTION_SKIPPED)
        result["skipped"] += 1
        return False
    try:
        bridge = getattr(owner.plugin, "daily_life_bridge", None)
        clean = getattr(bridge, "clean_expression_punctuation", None)
        if callable(clean):
            comment = await clean(comment, scene="qzone_comment")
        await owner.plugin.qzone_service.comment(post_key, comment)
    except Exception as exc:
        if int(post.appid or 311) == 4 and getattr(exc, "submission_unknown", False):
            _mark_qzone_post_processed(
                processed,
                post,
                QZONE_ACTION_SKIPPED,
                content=comment,
                reason=str(exc),
                submission_unknown=True,
                photo_target_key=photo_key,
            )
            result["skipped"] += 1
            await checkpoint_qzone_action(
                owner, QZONE_AUTO_COMMENT_STATE_KEY, state, processed, result
            )
            logger.warning(
                f"[日常分享] QQ 空间相册评论提交状态未知，已停止整批自动重试: {exc}"
            )
            return False
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
                photo_target_key=photo_key,
            )
            result["skipped"] += 1
            _qzone_mark_result_rate_limited(result, exc)
            logger.debug(f"[日常分享] QQ 空间自动评论稍后重试: {exc}")
            return True
        result["failed"] += 1
        logger.warning(f"[日常分享] QQ 空间自动评论失败: {exc}")
        return False
    _mark_qzone_post_processed(
        processed,
        post,
        QZONE_ACTION_COMMENTED,
        content=comment,
        post_key=post_key,
        post_uin=int(getattr(post, "uin", 0) or 0),
        post_tid=str(getattr(post, "tid", "") or ""),
        author=str(getattr(post, "name", "") or getattr(post, "uin", "") or ""),
        photo_target_key=photo_key,
    )
    result["commented"] += 1
    await checkpoint_qzone_action(
        owner, QZONE_AUTO_COMMENT_STATE_KEY, state, processed, result
    )
    await record_qzone_interaction(
        owner,
        post,
        comment,
        scene="qzone_comment",
        actor_id=str(getattr(post, "uin", "") or ""),
    )
    owner.plugin.emit_dashboard_event(
        "qzone",
        {"action": "auto_comment", "post_id": post_key},
    )
    logger.info(
        f"[日常分享] 已自动评论 QQ 空间动态: "
        f"{getattr(post, 'name', '') or getattr(post, 'uin', '')}"
        + (f"，照片={photo_key}" if photo_key else "")
    )
    await asyncio.sleep(QZONE_ACTION_DELAY_SECONDS)
    return False


async def _generate_qzone_comment_target(
    owner,
    post,
    posts: list,
    ctx,
    state: dict,
    processed: dict,
    *,
    target_umo: str,
    skip_post_keys: set[str],
):
    """生成整批评论并验证实际提交目标，不在这里修改持久状态。"""
    photo_key = post.photo_targets[0].key if int(post.appid or 311) == 4 else ""
    batch_posts = _qzone_auto_comment_batch_posts(post, posts)
    if len(batch_posts) > 1:
        (
            selected_key,
            comment,
        ) = await owner.generate_qzone_auto_photo_comment(
            _qzone_auto_comment_generation_post(post, batch_posts),
            batch_posts,
            state=state,
            target_umo=target_umo,
        )
        selected_post = next(
            (item for item in batch_posts if item.photo_targets[0].key == selected_key),
            None,
        )
        if selected_post is None:
            raise RuntimeError("相册评论选择了本批以外的照片，停止提交")
        if (
            selected_post.key in skip_post_keys
            or not owner._qzone_auto_comment_candidate(
                selected_post, self_uin=ctx.uin, processed=processed
            )
        ):
            return None
        post = selected_post
        photo_key = selected_key
    else:
        comment = await owner.generate_qzone_auto_comment(
            post,
            state=state,
            target_umo=target_umo,
        )

    return post, comment, photo_key


async def _execute_qzone_auto_comment_new_posts(
    owner,
    posts: list,
    ctx,
    state: dict,
    processed: dict,
    result: dict,
    *,
    limit: int,
    target_umo: str = "",
    skip_post_keys: set[str] | None = None,
) -> None:
    skip_post_keys = skip_post_keys or set()
    engaged_batches = {
        _photo_batch_key(post)
        for post in posts
        if _photo_batch_key(post)
        and any(
            int(getattr(comment, "uin", 0) or 0) == ctx.uin
            for comment in getattr(post, "comments", []) or []
        )
    }
    attempted_batches: set[str] = set()
    for post in posts:
        if result["commented"] >= limit:
            break
        if str(getattr(post, "key", "") or "").strip() in skip_post_keys:
            continue
        result["scanned"] += 1
        batch_key = _photo_batch_key(post)
        if batch_key and (
            not getattr(post, "photo_batch_complete", True)
            or batch_key in attempted_batches
        ):
            result["skipped"] += 1
            continue
        target_error = getattr(post, "comment_target_error", "")
        if target_error:
            result["skipped"] += 1
            logger.debug(f"[日常分享] QQ 空间自动评论跳过: {target_error}")
            continue
        pending_comment = next(
            (
                reply
                for reply in (
                    _qzone_pending_reply(processed, key)
                    for key in _post_alias_keys(post)
                )
                if reply
            ),
            "",
        )
        pending_target = next(
            (
                item.get("photo_target_key", "")
                for key in _post_alias_keys(post)
                if isinstance(item := processed.get(key), dict)
                and item.get("action") == QZONE_ACTION_RETRY_LATER
                and item.get("photo_target_key")
            ),
            "",
        )
        photo_key = post.photo_targets[0].key if int(post.appid or 311) == 4 else ""
        if pending_target and pending_target != photo_key:
            result["skipped"] += 1
            continue
        if batch_key:
            attempted_batches.add(batch_key)
        if not pending_comment:
            target = _qzone_auto_comment_reply_target(
                owner,
                _qzone_auto_comment_batch_posts(post, posts),
                ctx,
                processed,
                probability=_qzone_auto_config(owner).comment_reply_probability,
                skip_post_keys=skip_post_keys,
            )
            if target:
                reply_post, reply_comment, item_key = target
                paused = await _execute_qzone_auto_comment_reply(
                    owner,
                    reply_post,
                    reply_comment,
                    item_key,
                    state,
                    processed,
                    result,
                    self_uin=ctx.uin,
                    target_umo=target_umo,
                )
                if paused:
                    break
                continue
        if batch_key and batch_key in engaged_batches:
            result["skipped"] += 1
            continue
        if not owner._qzone_auto_comment_candidate(
            post,
            self_uin=ctx.uin,
            processed=processed,
        ):
            result["skipped"] += 1
            continue
        if pending_comment:
            comment = pending_comment
        else:
            try:
                generated = await _generate_qzone_comment_target(
                    owner,
                    post,
                    posts,
                    ctx,
                    state,
                    processed,
                    target_umo=target_umo,
                    skip_post_keys=skip_post_keys,
                )
                if generated is None:
                    result["skipped"] += 1
                    continue
                post, comment, photo_key = generated
            except Exception as exc:
                result["failed"] += 1
                result["generation_failed"] += 1
                logger.warning(f"[日常分享] QQ 空间自动评论生成失败: {exc}")
                continue
        if await _submit_qzone_auto_comment(
            owner, post, comment, photo_key, state, processed, result
        ):
            break


async def execute_qzone_auto_comment_task(
    owner,
    *,
    emit_summary: bool = True,
    target_id: str = "",
    target_umo: str = "",
) -> dict:
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
        disabled_log="[日常分享] QQ 空间自动评论未开启，跳过。",
    )
    if not ready:
        return result

    try:
        ctx = await owner.plugin.qzone_service.context()
        fetch_count = _qzone_query_fetch_count(limit, 3)
        target = str(target_id or "").strip()
        if target:
            posts = await owner.plugin.qzone_service.query_posts(
                target_id=target,
                pos=0,
                num=fetch_count,
                with_detail=True,
            )
        else:
            posts = await _query_qzone_friend_posts(owner, fetch_count=fetch_count)
        posts = await _expand_qzone_photo_posts(owner, posts)
    except Exception as exc:
        return await _qzone_abort_query_failure(
            owner,
            state_key=QZONE_AUTO_COMMENT_STATE_KEY,
            state=state,
            processed=processed,
            result=result,
            run_at=now,
            message="[日常分享] QQ 空间自动评论查询失败",
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
        target_umo=target_umo,
    )

    if not _qzone_result_rate_limited(result):
        await _execute_qzone_auto_comment_new_posts(
            owner,
            posts,
            ctx,
            state,
            processed,
            result,
            limit=limit,
            target_umo=target_umo,
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

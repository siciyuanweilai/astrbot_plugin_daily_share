import asyncio
import random
from dataclasses import replace

from astrbot.api import logger

from ..candidate import _qzone_friend_thread_comment_candidates
from ..comments import QzoneCommentIndex, _post_has_self_comment
from ..errors import QzoneAutoInteractionRateLimited
from ..intent import interaction_ready, living_interaction, wants_interaction
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
    _photo_target_key,
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
    # 生成时共享本批图片预算；实际评论范围由选定目标保留。
    return replace(post, images=images) if images != post.images else post


def _qzone_auto_comment_reply_targets(
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
        return []
    candidates.sort(key=lambda item: item[:3], reverse=True)
    pending = [item for item in candidates if item[0]]
    if pending:
        candidates = pending
    elif not probability or (
        not living_interaction(owner) and random.random() * 100 >= probability
    ):
        return []
    selected = []
    users: set[int] = set()
    user_limit = _qzone_auto_config(owner).comment_reply_user_limit
    for item in candidates:
        uin = int(item[4].uin)
        if uin not in users:
            users.add(uin)
            selected.append(item[3:])
        if len(selected) >= user_limit:
            break
    return selected


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
        if not await wants_interaction(owner, "reply", post, comment):
            result["skipped"] += 1
            return False
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
            if not await wants_interaction(
                owner, "reply", post, comment, parent_comment
            ):
                result["skipped"] += 1
                continue
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


async def _execute_qzone_auto_comment_replies(
    owner,
    posts: list,
    ctx,
    state: dict,
    processed: dict,
    result: dict,
    *,
    limit: int,
    target_umo: str = "",
    skip_post_keys: set[str],
) -> None:
    """概率回评独立扫描，不占用主体评论额度或修改其防重状态。"""
    attempted: set[str] = set()
    probability = _qzone_auto_config(owner).comment_reply_probability
    for post in posts:
        if result["commented"] >= limit:
            break
        batch_key = _photo_batch_key(post)
        identity = batch_key or post.key
        if (
            identity in attempted
            or post.comment_target_error
            or (batch_key and not post.photo_batch_complete)
        ):
            continue
        attempted.add(identity)
        targets = _qzone_auto_comment_reply_targets(
            owner,
            _qzone_auto_comment_batch_posts(post, posts),
            ctx,
            processed,
            probability=probability,
            skip_post_keys=skip_post_keys,
        )
        for reply_post, reply_comment, item_key in targets:
            if result["commented"] >= limit:
                break
            # 上一条回评可能已用完人数名额，或提交结果不明而暂停整批。
            if not owner._qzone_auto_comment_reply_candidate(
                reply_post, reply_comment, self_uin=ctx.uin, processed=processed
            ):
                continue
            result["scanned"] += 1
            if await _execute_qzone_auto_comment_reply(
                owner,
                reply_post,
                reply_comment,
                item_key,
                state,
                processed,
                result,
                self_uin=ctx.uin,
                target_umo=target_umo,
            ):
                return


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
        if not await interaction_ready(owner):
            result["skipped"] += 1
            return False
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
        photo_key=photo_key,
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
    """每批只选择一次评论范围，生成后校验实际落点。"""
    batch_posts = _qzone_auto_comment_batch_posts(post, posts)
    batch_post = next(
        (item for item in batch_posts if item.photo_comment_scope == "batch"), None
    )
    photo_posts = [item for item in batch_posts if item.photo_comment_scope != "batch"]
    probability = _qzone_auto_config(owner).comment_photo_batch_probability
    use_batch = batch_post is not None and (
        probability >= 100 or (probability > 0 and random.random() * 100 < probability)
    )
    if use_batch:
        post = batch_post
        comment = await owner.generate_qzone_auto_comment(
            post, state=state, target_umo=target_umo
        )
    elif len(photo_posts) > 1:
        selected_key, comment = await owner.generate_qzone_auto_photo_comment(
            _qzone_auto_comment_generation_post(photo_posts[0], photo_posts),
            photo_posts,
            state=state,
            target_umo=target_umo,
        )
        post = next(
            (item for item in photo_posts if item.photo_targets[0].key == selected_key),
            None,
        )
        if post is None:
            raise RuntimeError("相册评论选择了本批以外的照片，停止提交")
    else:
        post = photo_posts[0] if photo_posts else post
        comment = await owner.generate_qzone_auto_comment(
            post, state=state, target_umo=target_umo
        )
    if post.key in skip_post_keys or not owner._qzone_auto_comment_candidate(
        post, self_uin=ctx.uin, processed=processed
    ):
        return None
    return post, comment, _photo_target_key(post)


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
        if _photo_batch_key(post) and _post_has_self_comment(post, ctx.uin)
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
        photo_key = _photo_target_key(post)
        if pending_target and pending_target != photo_key:
            result["skipped"] += 1
            continue
        if batch_key:
            attempted_batches.add(batch_key)
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
            if not await wants_interaction(owner, "comment", post):
                result["skipped"] += 1
                continue
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
    state["processed"] = processed

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

    thread_reply_count = result["commented"]
    if not _qzone_result_rate_limited(result):
        await _execute_qzone_auto_comment_new_posts(
            owner,
            posts,
            ctx,
            state,
            processed,
            result,
            limit=thread_reply_count + limit,
            target_umo=target_umo,
            skip_post_keys=thread_replied_post_keys,
        )

    if not _qzone_result_rate_limited(result):
        # 主体评论先发送；概率回评可读取本轮已确认发送的正文。
        main_comment_count = result["commented"] - thread_reply_count
        await _execute_qzone_auto_comment_replies(
            owner,
            posts,
            ctx,
            state,
            processed,
            result,
            limit=main_comment_count + limit,
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

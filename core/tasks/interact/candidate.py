from dataclasses import dataclass
from typing import Any

from astrbot.api import logger

from ...space.photos import photo_reply_target_error
from .comments import QzoneCommentIndex, _comment_created_at, _comment_replies_to_self
from .placement import _has_thread_reply_submit_plan, _unsafe_thread_target_reason
from .tracker import _comment_key

_QZONE_SKIP_REASON_LABELS = {
    "already_processed": "已处理该评论",
    "outside_active_window": "不在有效互动时间范围内",
    "not_self_post": "不是机器人自己的动态",
    "not_friend_post": "不是好友动态",
    "self_comment": "评论来自机器人自己",
    "official_qzone": "QQ 空间官方动态",
    "already_replied": "已回复该评论",
    "empty_comment": "评论内容为空",
    "parent_is_self": "原一级评论来自机器人自己",
    "parent_not_self": "原一级评论不是机器人发布的",
    "missing_parent": "缺少原一级评论",
    "already_replied_to_target": "已回复当前对象",
    "has_later_nonself_reply": "已有更新的非机器人回复",
    "self_reply_after_comment": "机器人回复晚于当前评论，缺少此前参与记录",
    "missing_self_thread_reply": "缺少机器人在原楼层中的回复记录",
    "photo_reply_not_to_bot": "相册回复未明确指向机器人",
    "already_replied_to_photo_author": "已回复该相册评论人",
    "synthetic_thread_tid_without_real_submit_id": "楼层仅有合成 tid，缺少真实提交 ID",
}


@dataclass(frozen=True)
class QzoneReplyCandidate:
    priority: tuple
    post: Any
    comment: Any
    item_key: str
    parent_comment: Any = None
    is_thread_reply: bool = True


def _log_qzone_candidate_skip(label: str, reason: str, post, comment) -> None:
    author = getattr(post, "name", "") or getattr(post, "uin", "") or ""
    target = getattr(comment, "nickname", "") or getattr(comment, "uin", "") or ""
    reason_label = _QZONE_SKIP_REASON_LABELS.get(reason, reason)
    reason_text = f"{reason_label}（{reason}）" if reason_label != reason else reason
    logger.debug(
        f"[日常分享] QQ 空间{label}候选跳过: 原因={reason_text}，动态={author}，评论={target}"
    )


def _photo_candidate_skip_reason(post, comment, parent, *, self_uin, index) -> str:
    if getattr(post, "comment_target_error", ""):
        return post.comment_target_error
    topic = post.photo_targets[0].feed_comment_topic_id
    reason = photo_reply_target_error(
        comment,
        topic=topic,
        parent_comment=parent,
    )
    if reason or parent is None:
        return reason
    if comment.reply_to_uin != self_uin:
        return "photo_reply_not_to_bot"
    # QQ 只标识被回复的账号，不提供对应的前序回复 ID。
    # 机器人随后已回复该账号时，就不再处理较早的候选。
    if any(
        item.uin == self_uin
        and item.reply_to_uin in (0, comment.uin)
        and item.create_time >= comment.create_time > 0
        for item in index.by_parent_tid.get(parent.tid, [])
    ):
        return "already_replied_to_photo_author"
    # 不同评论人或指向其他对象的回复属于独立轮次。
    if any(
        item.uin == comment.uin
        and item.reply_to_uin == self_uin
        and item.create_time > comment.create_time > 0
        and not photo_reply_target_error(item, topic=topic, parent_comment=parent)
        for item in index.by_parent_tid.get(parent.tid, [])
    ):
        return "has_later_nonself_reply"
    return ""


def _qzone_friend_thread_comment_candidates(
    owner, posts: list, *, self_uin: int, processed: dict
) -> list[QzoneReplyCandidate]:
    candidates: list[QzoneReplyCandidate] = []
    seen_photo_targets: set[str] = set()
    for post_index, post in enumerate(posts or []):
        appid = int(getattr(post, "appid", 311) or 311)
        if appid not in {311, 4}:
            continue
        if int(getattr(post, "uin", 0) or 0) == int(self_uin or 0):
            continue
        comment_index = QzoneCommentIndex.build(post, self_uin)
        for comment_index_in_post, comment in enumerate(comment_index.comments):
            parent_comment = owner._qzone_find_parent_comment(
                post, comment, index=comment_index
            )
            if parent_comment is None:
                continue
            item_key = _comment_key(post, comment)
            if appid == 4:
                reason = _photo_candidate_skip_reason(
                    post,
                    comment,
                    parent_comment,
                    self_uin=self_uin,
                    index=comment_index,
                )
                if reason:
                    _log_qzone_candidate_skip("好友相册续评", reason, post, comment)
                    continue
            skip_reason = owner._qzone_friend_comment_thread_skip_reason(
                post,
                parent_comment,
                comment,
                self_uin=self_uin,
                processed=processed,
                index=comment_index,
            )
            if skip_reason:
                _log_qzone_candidate_skip("好友动态续评", skip_reason, post, comment)
                continue
            unsafe_reason = _unsafe_thread_target_reason(
                owner, comment, parent_comment=parent_comment
            )
            if (
                appid == 311
                and unsafe_reason
                and not _has_thread_reply_submit_plan(
                    owner,
                    post,
                    comment,
                    parent_comment=parent_comment,
                )
            ):
                _log_qzone_candidate_skip("好友动态续评", unsafe_reason, post, comment)
                continue
            if appid == 4:
                if item_key in seen_photo_targets:
                    continue
                seen_photo_targets.add(item_key)
            targets_self = _comment_replies_to_self(
                comment, self_uin, index=comment_index
            )
            priority = (
                1 if targets_self else 0,
                _comment_created_at(comment),
                -post_index,
                comment_index_in_post,
            )
            candidates.append(
                QzoneReplyCandidate(
                    priority=priority,
                    post=post,
                    comment=comment,
                    parent_comment=parent_comment,
                    item_key=item_key,
                    is_thread_reply=True,
                )
            )
    return sorted(candidates, key=lambda item: item.priority, reverse=True)


def _qzone_self_reply_candidates(
    owner, posts: list, *, self_uin: int, processed: dict, result: dict
) -> list[QzoneReplyCandidate]:
    candidates: list[QzoneReplyCandidate] = []
    seen_targets: set[str] = set()
    for post_index, post in enumerate(posts or []):
        appid = int(getattr(post, "appid", 311) or 311)
        if appid not in {311, 4}:
            continue
        if appid == 4 and getattr(post, "comment_target_error", ""):
            logger.debug(
                f"[日常分享] QQ 空间相册自动回评跳过: {post.comment_target_error}"
            )
            continue
        comment_index = QzoneCommentIndex.build(post, self_uin)
        is_self_post = int(getattr(post, "uin", 0) or 0) == int(self_uin or 0)
        if not is_self_post:
            continue
        for comment_index_in_post, comment in enumerate(comment_index.comments):
            parent_comment = owner._qzone_find_parent_comment(
                post, comment, index=comment_index
            )
            result["scanned"] += 1
            item_key = _comment_key(post, comment)
            is_thread_reply = parent_comment is not None
            if appid == 4:
                reason = _photo_candidate_skip_reason(
                    post,
                    comment,
                    parent_comment,
                    self_uin=self_uin,
                    index=comment_index,
                )
                if reason:
                    result["skipped"] += 1
                    _log_qzone_candidate_skip(
                        "相册自动回评",
                        reason,
                        post,
                        comment,
                    )
                    continue
            if is_thread_reply:
                skip_reason = owner._qzone_auto_reply_thread_skip_reason(
                    post,
                    parent_comment,
                    comment,
                    self_uin=self_uin,
                    processed=processed,
                    index=comment_index,
                )
                if skip_reason:
                    result["skipped"] += 1
                    _log_qzone_candidate_skip("自动回评", skip_reason, post, comment)
                    continue
                unsafe_reason = _unsafe_thread_target_reason(
                    owner, comment, parent_comment=parent_comment
                )
                if (
                    appid == 311
                    and unsafe_reason
                    and not _has_thread_reply_submit_plan(
                        owner,
                        post,
                        comment,
                        parent_comment=parent_comment,
                    )
                ):
                    result["skipped"] += 1
                    _log_qzone_candidate_skip("自动回评", unsafe_reason, post, comment)
                    continue
            else:
                skip_reason = owner._qzone_auto_reply_skip_reason(
                    post,
                    comment,
                    self_uin=self_uin,
                    processed=processed,
                    index=comment_index,
                )
                if skip_reason:
                    result["skipped"] += 1
                    _log_qzone_candidate_skip("自动回评", skip_reason, post, comment)
                    continue

            if appid == 4:
                if item_key in seen_targets:
                    result["skipped"] += 1
                    continue
                seen_targets.add(item_key)
            targets_self = bool(
                is_thread_reply
                and _comment_replies_to_self(comment, self_uin, index=comment_index)
            )
            priority = (
                1 if targets_self else 0,
                1 if is_thread_reply else 0,
                _comment_created_at(comment),
                -post_index,
                comment_index_in_post,
            )
            candidates.append(
                QzoneReplyCandidate(
                    priority=priority,
                    post=post,
                    comment=comment,
                    parent_comment=parent_comment if is_thread_reply else None,
                    item_key=item_key,
                    is_thread_reply=is_thread_reply,
                )
            )
    return sorted(candidates, key=lambda item: item.priority, reverse=True)

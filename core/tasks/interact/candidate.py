from dataclasses import dataclass
from typing import Any

from .comments import QzoneCommentIndex, _comment_created_at, _comment_replies_to_self
from .placement import _has_thread_reply_submit_plan, _unsafe_thread_target_reason
from .tracker import _comment_key


@dataclass(frozen=True)
class QzoneReplyCandidate:
    priority: tuple
    post: Any
    comment: Any
    item_key: str
    parent_comment: Any = None
    is_thread_reply: bool = True


def _qzone_friend_thread_comment_candidates(owner, posts: list, *, self_uin: int, processed: dict) -> list[QzoneReplyCandidate]:
    candidates: list[QzoneReplyCandidate] = []
    for post_index, post in enumerate(posts or []):
        if int(getattr(post, "uin", 0) or 0) == int(self_uin or 0):
            continue
        comment_index = QzoneCommentIndex.build(post, self_uin)
        for comment_index_in_post, comment in enumerate(comment_index.comments):
            parent_comment = owner._qzone_find_parent_comment(post, comment, index=comment_index)
            if parent_comment is None:
                continue
            item_key = _comment_key(post, comment)
            skip_reason = owner._qzone_friend_comment_thread_skip_reason(
                post,
                parent_comment,
                comment,
                self_uin=self_uin,
                processed=processed,
                index=comment_index,
            )
            if skip_reason:
                continue
            unsafe_reason = _unsafe_thread_target_reason(owner, comment, parent_comment=parent_comment)
            if unsafe_reason and not _has_thread_reply_submit_plan(
                owner,
                post,
                comment,
                parent_comment=parent_comment,
            ):
                continue
            targets_self = _comment_replies_to_self(comment, self_uin, index=comment_index)
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


def _qzone_self_reply_candidates(owner, posts: list, *, self_uin: int, processed: dict, result: dict) -> list[QzoneReplyCandidate]:
    candidates: list[QzoneReplyCandidate] = []
    for post_index, post in enumerate(posts or []):
        comment_index = QzoneCommentIndex.build(post, self_uin)
        is_self_post = int(getattr(post, "uin", 0) or 0) == int(self_uin or 0)
        if not is_self_post:
            continue
        for comment_index_in_post, comment in enumerate(comment_index.comments):
            parent_comment = owner._qzone_find_parent_comment(post, comment, index=comment_index)
            result["scanned"] += 1
            item_key = _comment_key(post, comment)
            is_thread_reply = parent_comment is not None
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
                    continue
                unsafe_reason = _unsafe_thread_target_reason(owner, comment, parent_comment=parent_comment)
                if unsafe_reason and not _has_thread_reply_submit_plan(
                    owner,
                    post,
                    comment,
                    parent_comment=parent_comment,
                ):
                    result["skipped"] += 1
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
                    continue

            targets_self = bool(
                is_thread_reply and _comment_replies_to_self(comment, self_uin, index=comment_index)
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

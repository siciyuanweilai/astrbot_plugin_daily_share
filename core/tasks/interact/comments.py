from dataclasses import dataclass
import re
from typing import Any


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except Exception:
        return default


def _comment_tid(comment) -> str:
    return str(getattr(comment, "tid", "") or "").strip()


def _comment_parent_tid(comment) -> str:
    return str(getattr(comment, "parent_tid", "") or "").strip()


def _comment_submit_tid(comment) -> str:
    return str(getattr(comment, "submit_tid", "") or "").strip()


def _comment_reply_to_tid(comment) -> str:
    return str(getattr(comment, "reply_to_tid", "") or "").strip()


def _comment_reply_to_uin(comment) -> int:
    return _safe_int(getattr(comment, "reply_to_uin", 0))


def _comment_mention_uins(comment) -> set[int]:
    text = str(getattr(comment, "content", "") or "")
    return {
        uin
        for uin in (_safe_int(match) for match in re.findall(r"@\{[^}]*\buin:(\d+)", text, re.I))
        if uin
    }


def _comment_uin(comment) -> int:
    return _safe_int(getattr(comment, "uin", 0))


def _comment_created_at(comment) -> int:
    return _safe_int(getattr(comment, "create_time", 0))


def _post_comments(post) -> list:
    return list(getattr(post, "comments", []) or [])


@dataclass
class QzoneCommentIndex:
    comments: list
    by_tid: dict[str, Any]
    by_parent_tid: dict[str, list]
    by_reply_to_tid: dict[str, list]
    self_comments: list
    self_replies_by_parent: dict[str, list]
    self_replies_by_target: dict[str, list]
    by_parent_tid_nonself: dict[str, list]

    @classmethod
    def build(cls, post, self_uin: int) -> "QzoneCommentIndex":
        self_uin = _safe_int(self_uin)
        comments = _post_comments(post)
        by_tid: dict[str, Any] = {}
        by_parent_tid: dict[str, list] = {}
        by_reply_to_tid: dict[str, list] = {}
        self_comments = []
        self_replies_by_parent: dict[str, list] = {}
        self_replies_by_target: dict[str, list] = {}
        by_parent_tid_nonself: dict[str, list] = {}

        for comment in comments:
            tid = _comment_tid(comment)
            parent_tid = _comment_parent_tid(comment)
            reply_to_tid = _comment_reply_to_tid(comment)
            uin = _comment_uin(comment)
            if tid:
                by_tid[tid] = comment
            if parent_tid:
                by_parent_tid.setdefault(parent_tid, []).append(comment)
                if self_uin and uin == self_uin:
                    self_replies_by_parent.setdefault(parent_tid, []).append(comment)
                else:
                    by_parent_tid_nonself.setdefault(parent_tid, []).append(comment)
            if reply_to_tid:
                by_reply_to_tid.setdefault(reply_to_tid, []).append(comment)
                if self_uin and uin == self_uin:
                    self_replies_by_target.setdefault(reply_to_tid, []).append(comment)
            elif self_uin and uin == self_uin:
                self_comments.append(comment)

        return cls(
            comments=comments,
            by_tid=by_tid,
            by_parent_tid=by_parent_tid,
            by_reply_to_tid=by_reply_to_tid,
            self_comments=self_comments,
            self_replies_by_parent=self_replies_by_parent,
            self_replies_by_target=self_replies_by_target,
            by_parent_tid_nonself=by_parent_tid_nonself,
        )

    def parent_of(self, comment):
        parent_tid = _comment_parent_tid(comment)
        if parent_tid:
            return self.by_tid.get(parent_tid)
        target = self.reply_target_of(comment)
        if not target:
            return None
        target_parent_tid = _comment_parent_tid(target)
        return self.by_tid.get(target_parent_tid) if target_parent_tid else target

    def reply_target_of(self, comment):
        reply_to_tid = _comment_reply_to_tid(comment)
        if not reply_to_tid:
            return None
        target = self.by_tid.get(reply_to_tid)
        if target:
            return target
        reply_to_uin = _comment_reply_to_uin(comment)
        if not reply_to_uin:
            return None
        for item in reversed(self.comments):
            if _comment_uin(item) != reply_to_uin:
                continue
            if reply_to_tid in {_comment_tid(item), _comment_submit_tid(item)}:
                return item
        return None

    def has_self_comment(self) -> bool:
        return bool(self.self_comments)

    def has_self_reply(self, parent_tid: str) -> bool:
        return bool(self.self_replies_by_parent.get(str(parent_tid or "").strip()))

    def has_self_reply_to(self, target_tid: str) -> bool:
        return bool(self.self_replies_by_target.get(str(target_tid or "").strip()))

    def has_timed_self_reply(self, parent_tid: str) -> bool:
        return any(
            _comment_created_at(item) > 0
            for item in self.self_replies_by_parent.get(str(parent_tid or "").strip(), [])
        )

    def self_reply_bounds(self, parent_tid: str, comment) -> tuple[bool, bool]:
        parent_tid = str(parent_tid or "").strip()
        if not parent_tid:
            return False, False
        comment_tid = _comment_tid(comment)
        comment_time = _comment_created_at(comment)
        comment_index = -1
        for index, item in enumerate(self.comments):
            if item is comment or (comment_tid and _comment_tid(item) == comment_tid):
                comment_index = index
                break

        has_before = False
        has_after = False
        for item in self.self_replies_by_parent.get(parent_tid, []):
            item_time = _comment_created_at(item)
            if comment_time and item_time:
                if item_time < comment_time:
                    has_before = True
                elif item_time > comment_time:
                    has_after = True
                continue
            if comment_index >= 0:
                try:
                    item_index = self.comments.index(item)
                except ValueError:
                    continue
                if item_index < comment_index:
                    has_before = True
                elif item_index > comment_index:
                    has_after = True
            else:
                has_after = True
        return has_before, has_after

    def has_later_nonself_reply(self, parent_tid: str, comment, self_uin: int) -> bool:
        parent_tid = str(parent_tid or "").strip()
        if not parent_tid:
            return False
        self_uin = _safe_int(self_uin)
        comment_tid = _comment_tid(comment)
        comment_time = _comment_created_at(comment)
        comment_index = -1
        for index, item in enumerate(self.comments):
            if item is comment or (comment_tid and _comment_tid(item) == comment_tid):
                comment_index = index
                break

        for item in self.by_parent_tid_nonself.get(parent_tid, []):
            if self_uin and _comment_uin(item) == self_uin:
                continue
            item_tid = _comment_tid(item)
            if comment_tid and item_tid == comment_tid:
                continue
            item_time = _comment_created_at(item)
            if comment_time and item_time:
                if item_time > comment_time:
                    return True
                continue
            if comment_index >= 0:
                try:
                    item_index = self.comments.index(item)
                except ValueError:
                    continue
                if item_index > comment_index:
                    return True
        return False


def _post_has_self_comment(post, self_uin: int, index: QzoneCommentIndex = None) -> bool:
    self_uin = _safe_int(self_uin)
    if not self_uin:
        return False
    return (index or QzoneCommentIndex.build(post, self_uin)).has_self_comment()


def _comment_has_self_reply(post, comment, self_uin: int, index: QzoneCommentIndex = None) -> bool:
    self_uin = _safe_int(self_uin)
    parent_tid = _comment_tid(comment)
    if not self_uin or not parent_tid:
        return False
    return (index or QzoneCommentIndex.build(post, self_uin)).has_self_reply(parent_tid)


def _comment_thread_has_self_reply_to(
    post,
    comment,
    self_uin: int,
    index: QzoneCommentIndex = None,
) -> bool:
    self_uin = _safe_int(self_uin)
    target_tid = _comment_tid(comment)
    if not self_uin or not target_tid:
        return False
    return (index or QzoneCommentIndex.build(post, self_uin)).has_self_reply_to(target_tid)


def _comment_replies_to_self(comment, self_uin: int, index: QzoneCommentIndex = None) -> bool:
    self_uin = _safe_int(self_uin)
    if not self_uin:
        return False
    if _comment_reply_to_uin(comment) == self_uin:
        return True
    if self_uin in _comment_mention_uins(comment):
        return True
    reply_to_tid = _comment_reply_to_tid(comment)
    if not reply_to_tid or index is None:
        return False
    target = index.by_tid.get(reply_to_tid)
    return bool(target and _comment_uin(target) == self_uin)


def _comment_thread_has_timed_self_reply(
    post,
    parent_comment,
    self_uin: int,
    index: QzoneCommentIndex = None,
) -> bool:
    self_uin = _safe_int(self_uin)
    parent_tid = _comment_tid(parent_comment)
    if not self_uin or not parent_tid:
        return False
    return (index or QzoneCommentIndex.build(post, self_uin)).has_timed_self_reply(parent_tid)


def _comment_thread_self_reply_bounds(
    post,
    parent_comment,
    comment,
    self_uin: int,
    index: QzoneCommentIndex = None,
) -> tuple[bool, bool]:
    self_uin = _safe_int(self_uin)
    parent_tid = _comment_tid(parent_comment)
    if not self_uin or not parent_tid:
        return False, False
    return (index or QzoneCommentIndex.build(post, self_uin)).self_reply_bounds(parent_tid, comment)


def _comment_thread_has_later_nonself_reply(
    post,
    parent_comment,
    comment,
    self_uin: int,
    index: QzoneCommentIndex = None,
) -> bool:
    parent_tid = _comment_tid(parent_comment)
    if not parent_tid:
        return False
    return (index or QzoneCommentIndex.build(post, self_uin)).has_later_nonself_reply(parent_tid, comment, self_uin)

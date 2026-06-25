from .comments import (
    QzoneCommentIndex,
    _comment_has_self_reply,
    _comment_thread_has_later_nonself_reply,
    _comment_thread_has_self_reply_to,
    _comment_thread_has_timed_self_reply,
    _comment_thread_self_reply_bounds,
    _post_has_self_comment,
)
from .formatting import _qzone_post_plain_text
from .tracker import (
    QZONE_ACTION_RETRY_LATER,
    _comment_key,
    _post_key,
    _qzone_like_processed_action,
    _qzone_processed_thread_has_self_reply,
)


class QzoneAutoPolicyMixin:
    @staticmethod
    def _qzone_is_official_qzone_post(post) -> bool:
        author = str(getattr(post, "name", "") or "").strip()
        return author.replace(" ", "").casefold() == "官方qzone"

    def _qzone_auto_comment_candidate(
        self,
        post,
        *,
        self_uin: int,
        processed: dict,
        index: QzoneCommentIndex = None,
    ) -> bool:
        post_key = str(getattr(post, "key", "") or "").strip()
        if not post_key or post_key in processed:
            return False
        if self._qzone_is_official_qzone_post(post):
            return False
        try:
            if int(getattr(post, "uin", 0) or 0) == int(self_uin or 0):
                return False
        except Exception:
            return False
        if _post_has_self_comment(post, self_uin, index=index):
            return False
        content = _qzone_post_plain_text(post)
        return bool(content or getattr(post, "images", None) or getattr(post, "videos", None))

    def _qzone_auto_like_candidate(
        self,
        post,
        *,
        self_uin: int,
        processed: dict,
    ) -> bool:
        post_key = _post_key(post)
        if not post_key or _qzone_like_processed_action(processed, post_key):
            return False
        if self._qzone_is_official_qzone_post(post):
            return False
        try:
            if int(getattr(post, "uin", 0) or 0) == int(self_uin or 0):
                return False
        except Exception:
            return False
        if bool(getattr(post, "liked", False)):
            return False
        content = _qzone_post_plain_text(post)
        return bool(content or getattr(post, "images", None) or getattr(post, "videos", None))

    def _qzone_auto_reply_skip_reason(
        self,
        post,
        comment,
        *,
        self_uin: int,
        processed: dict,
        index: QzoneCommentIndex = None,
    ) -> str:
        item_key = _comment_key(post, comment)
        processed_item = processed.get(item_key) if isinstance(processed, dict) else None
        processed_action = str(processed_item.get("action") or "") if isinstance(processed_item, dict) else ""
        if processed_action and processed_action != QZONE_ACTION_RETRY_LATER:
            return "already_processed"
        if int(getattr(post, "uin", 0) or 0) != int(self_uin or 0):
            return "not_self_post"
        if int(getattr(comment, "uin", 0) or 0) == int(self_uin or 0):
            return "self_comment"
        if self._qzone_is_official_qzone_post(post):
            return "official_qzone"
        if _comment_has_self_reply(post, comment, self_uin, index=index):
            return "already_replied"
        content = str(getattr(comment, "content", "") or "").strip()
        return "" if content else "empty_comment"

    def _qzone_auto_reply_candidate(
        self,
        post,
        comment,
        *,
        self_uin: int,
        processed: dict,
        index: QzoneCommentIndex = None,
    ) -> bool:
        return not self._qzone_auto_reply_skip_reason(
            post,
            comment,
            self_uin=self_uin,
            processed=processed,
            index=index,
        )

    def _qzone_auto_reply_thread_skip_reason(
        self,
        post,
        parent_comment,
        comment,
        *,
        self_uin: int,
        processed: dict,
        index: QzoneCommentIndex = None,
    ) -> str:
        item_key = _comment_key(post, comment)
        processed_item = processed.get(item_key) if isinstance(processed, dict) else None
        processed_action = str(processed_item.get("action") or "") if isinstance(processed_item, dict) else ""
        if processed_action and processed_action != QZONE_ACTION_RETRY_LATER:
            return "already_processed"
        if int(getattr(post, "uin", 0) or 0) != int(self_uin or 0):
            return "not_self_post"
        if int(getattr(comment, "uin", 0) or 0) == int(self_uin or 0):
            return "self_comment"
        if parent_comment is None:
            return "missing_parent"
        parent_uin = int(getattr(parent_comment, "uin", 0) or 0)
        if parent_uin == int(self_uin or 0):
            return "parent_is_self"
        if _comment_thread_has_self_reply_to(post, comment, self_uin, index=index):
            return "already_replied_to_target"
        if _comment_thread_has_later_nonself_reply(post, parent_comment, comment, self_uin, index=index):
            return "has_later_nonself_reply"
        content = str(getattr(comment, "content", "") or "").strip()
        if not content:
            return "empty_comment"
        if not _comment_has_self_reply(post, parent_comment, self_uin, index=index):
            if _qzone_processed_thread_has_self_reply(post, parent_comment, processed):
                return ""
            return "missing_self_thread_reply"

        if _comment_thread_has_timed_self_reply(post, parent_comment, self_uin, index=index):
            has_before, has_after = _comment_thread_self_reply_bounds(
                post,
                parent_comment,
                comment,
                self_uin,
                index=index,
            )
            if has_after and not has_before:
                return "self_reply_after_comment"
            if not has_before:
                return "missing_self_thread_reply"
        return ""

    def _qzone_auto_reply_thread_candidate(
        self,
        post,
        parent_comment,
        comment,
        *,
        self_uin: int,
        processed: dict,
        index: QzoneCommentIndex = None,
    ) -> bool:
        return not self._qzone_auto_reply_thread_skip_reason(
            post,
            parent_comment,
            comment,
            self_uin=self_uin,
            processed=processed,
            index=index,
        )

    def _qzone_friend_comment_thread_skip_reason(
        self,
        post,
        parent_comment,
        comment,
        *,
        self_uin: int,
        processed: dict,
        index: QzoneCommentIndex = None,
    ) -> str:
        item_key = _comment_key(post, comment)
        processed_item = processed.get(item_key) if isinstance(processed, dict) else None
        processed_action = str(processed_item.get("action") or "") if isinstance(processed_item, dict) else ""
        if processed_action and processed_action != QZONE_ACTION_RETRY_LATER:
            return "already_processed"
        if int(getattr(post, "uin", 0) or 0) == int(self_uin or 0):
            return "not_friend_post"
        if parent_comment is None:
            return "missing_parent"
        if int(getattr(parent_comment, "uin", 0) or 0) != int(self_uin or 0):
            return "parent_not_self"
        if int(getattr(comment, "uin", 0) or 0) == int(self_uin or 0):
            return "self_comment"
        if _comment_thread_has_self_reply_to(post, comment, self_uin, index=index):
            return "already_replied_to_target"
        if _comment_thread_has_later_nonself_reply(post, parent_comment, comment, self_uin, index=index):
            return "has_later_nonself_reply"
        content = str(getattr(comment, "content", "") or "").strip()
        return "" if content else "empty_comment"

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from ...space.photos import photo_reply_target_error
from .comments import (
    QzoneCommentIndex,
    _comment_has_self_reply,
    _comment_replies_to_self,
    _comment_thread_has_later_nonself_reply,
    _comment_thread_has_self_reply_to,
    _comment_thread_has_timed_self_reply,
    _comment_thread_self_reply_bounds,
    _post_has_self_comment,
)
from .formatting import _qzone_post_plain_text
from .tracker import (
    QZONE_ACTION_COMMENT_REPLIED,
    QZONE_ACTION_RETRY_LATER,
    _comment_key,
    _post_key,
    _qzone_comment_reply_post_action,
    _qzone_like_post_processed_action,
    _qzone_post_processed_action,
    _qzone_processed_thread_has_self_reply,
)

if TYPE_CHECKING:
    from ..qinteract import TaskQzoneAutoCommentService

QZONE_ACTIVE_WINDOW_MIN_TIMESTAMP = 946684800


class QzoneAutoPolicyService:
    def __init__(self, owner: TaskQzoneAutoCommentService) -> None:
        self.owner = owner

    @staticmethod
    def _qzone_is_official_qzone_post(post) -> bool:
        author = str(getattr(post, "name", "") or "").strip()
        return author.replace(" ", "").casefold() == "官方qzone"

    def _qzone_auto_active_window_hours(self) -> int:
        try:
            cfg = self.owner._qzone_auto_config()
        except Exception:
            cfg = None
        try:
            hours = int(
                getattr(cfg, "active_window_hours", 24) if cfg is not None else 24
            )
        except Exception:
            hours = 24
        return max(0, min(168, hours))

    def _qzone_auto_timestamp_in_active_window(self, timestamp: int) -> bool:
        hours = self.owner._qzone_auto_active_window_hours()
        if hours <= 0:
            return True
        try:
            created_at = int(timestamp or 0)
        except Exception:
            created_at = 0
        if created_at < QZONE_ACTIVE_WINDOW_MIN_TIMESTAMP:
            return True
        return created_at >= int(time.time()) - hours * 3600

    def _qzone_auto_post_in_active_window(self, post) -> bool:
        return self.owner._qzone_auto_timestamp_in_active_window(
            getattr(post, "create_time", 0)
        )

    def _qzone_auto_comment_in_active_window(self, post, comment) -> bool:
        timestamp = getattr(comment, "create_time", 0) or getattr(
            post, "create_time", 0
        )
        return self.owner._qzone_auto_timestamp_in_active_window(timestamp)

    def _qzone_auto_comment_candidate(
        self,
        post,
        *,
        self_uin: int,
        processed: dict,
        index: QzoneCommentIndex | None = None,
    ) -> bool:
        post_key = str(getattr(post, "key", "") or "").strip()
        processed_action = _qzone_post_processed_action(processed, post)
        if not post_key or (
            processed_action
            and processed_action
            not in {QZONE_ACTION_RETRY_LATER, QZONE_ACTION_COMMENT_REPLIED}
        ):
            return False
        if not self.owner._qzone_auto_post_in_active_window(post):
            return False
        if self.owner._qzone_is_official_qzone_post(post):
            return False
        try:
            if int(getattr(post, "uin", 0) or 0) == int(self_uin or 0):
                return False
        except Exception:
            return False
        if _post_has_self_comment(post, self_uin, index=index):
            return False
        content = _qzone_post_plain_text(post)
        return bool(
            content
            or getattr(post, "images", None)
            or getattr(post, "rt_images", None)
            or getattr(post, "videos", None)
        )

    def _qzone_auto_comment_reply_candidate(
        self,
        post,
        comment,
        *,
        self_uin: int,
        processed: dict,
        index: QzoneCommentIndex | None = None,
    ) -> bool:
        appid = int(getattr(post, "appid", 311) or 311)
        if appid not in {311, 4}:
            return False
        post_key = str(getattr(post, "key", "") or "").strip()
        if not post_key or not self.owner._qzone_auto_post_in_active_window(post):
            return False
        if self.owner._qzone_is_official_qzone_post(post):
            return False
        if int(getattr(post, "uin", 0) or 0) in {0, int(self_uin or 0)}:
            return False
        if _qzone_comment_reply_post_action(processed, post):
            return False
        if (
            str(getattr(comment, "parent_tid", "") or "").strip()
            or str(getattr(comment, "reply_to_tid", "") or "").strip()
        ):
            return False
        comment_id = str(
            getattr(comment, "tid", "") or getattr(comment, "submit_tid", "") or ""
        ).strip()
        if not comment_id:
            return False
        if int(getattr(comment, "uin", 0) or 0) in {0, int(self_uin or 0)}:
            return False
        if not str(getattr(comment, "content", "") or "").strip():
            return False
        if not self.owner._qzone_auto_comment_in_active_window(post, comment):
            return False

        item_key = _comment_key(post, comment)
        processed_item = (
            processed.get(item_key) if isinstance(processed, dict) else None
        )
        processed_action = (
            str(processed_item.get("action") or "")
            if isinstance(processed_item, dict)
            else ""
        )
        if processed_action and processed_action != QZONE_ACTION_RETRY_LATER:
            return False

        comment_index = index or QzoneCommentIndex.build(post, self_uin)
        target_ids = {
            str(getattr(comment, name, "") or "").strip()
            for name in ("tid", "submit_tid", "raw_tid")
        }
        target_ids.discard("")
        if any(
            comment_index.has_self_reply(target_id)
            or comment_index.has_self_reply_to(target_id)
            for target_id in target_ids
        ):
            return False

        if appid == 4:
            photos = getattr(post, "photo_targets", []) or []
            if len(photos) != 1:
                return False
            return not photo_reply_target_error(
                comment,
                topic=photos[0].feed_comment_topic_id,
                parent_comment=None,
            )
        return True

    def _qzone_auto_like_candidate(
        self,
        post,
        *,
        self_uin: int,
        processed: dict,
    ) -> bool:
        post_key = _post_key(post)
        if not post_key or _qzone_like_post_processed_action(processed, post):
            return False
        if not self.owner._qzone_auto_post_in_active_window(post):
            return False
        if self.owner._qzone_is_official_qzone_post(post):
            return False
        try:
            if int(getattr(post, "uin", 0) or 0) == int(self_uin or 0):
                return False
        except Exception:
            return False
        if bool(getattr(post, "liked", False)):
            return False
        content = _qzone_post_plain_text(post)
        return bool(
            content
            or getattr(post, "images", None)
            or getattr(post, "rt_images", None)
            or getattr(post, "videos", None)
        )

    def _qzone_auto_reply_skip_reason(
        self,
        post,
        comment,
        *,
        self_uin: int,
        processed: dict,
        index: QzoneCommentIndex | None = None,
    ) -> str:
        item_key = _comment_key(post, comment)
        processed_item = (
            processed.get(item_key) if isinstance(processed, dict) else None
        )
        processed_action = (
            str(processed_item.get("action") or "")
            if isinstance(processed_item, dict)
            else ""
        )
        if processed_action and processed_action != QZONE_ACTION_RETRY_LATER:
            return "already_processed"
        if not self.owner._qzone_auto_comment_in_active_window(post, comment):
            return "outside_active_window"
        if int(getattr(post, "uin", 0) or 0) != int(self_uin or 0):
            return "not_self_post"
        if int(getattr(comment, "uin", 0) or 0) == int(self_uin or 0):
            return "self_comment"
        if self.owner._qzone_is_official_qzone_post(post):
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
        index: QzoneCommentIndex | None = None,
    ) -> bool:
        return not self.owner._qzone_auto_reply_skip_reason(
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
        index: QzoneCommentIndex | None = None,
    ) -> str:
        reason = self.owner._qzone_reply_thread_base_skip_reason(
            post,
            parent_comment,
            comment,
            self_uin=self_uin,
            processed=processed,
        )
        if reason:
            return reason
        parent_uin = int(getattr(parent_comment, "uin", 0) or 0)
        if parent_uin == int(self_uin or 0):
            return "parent_is_self"
        if _comment_thread_has_self_reply_to(post, comment, self_uin, index=index):
            return "already_replied_to_target"
        # 相册候选按评论人和被回复者合并已核验的回复。
        is_photo = int(getattr(post, "appid", 311) or 311) == 4
        if not is_photo and _comment_thread_has_later_nonself_reply(
            post, parent_comment, comment, self_uin, index=index
        ):
            return "has_later_nonself_reply"
        if not str(getattr(comment, "content", "") or "").strip():
            return "empty_comment"
        if not _comment_has_self_reply(post, parent_comment, self_uin, index=index):
            return (
                ""
                if _qzone_processed_thread_has_self_reply(
                    post, parent_comment, processed
                )
                else "missing_self_thread_reply"
            )

        if _comment_thread_has_timed_self_reply(
            post, parent_comment, self_uin, index=index
        ):
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

    def _qzone_reply_thread_base_skip_reason(
        self,
        post,
        parent_comment,
        comment,
        *,
        self_uin: int,
        processed: dict,
    ) -> str:
        item_key = _comment_key(post, comment)
        processed_item = (
            processed.get(item_key) if isinstance(processed, dict) else None
        )
        processed_action = (
            str(processed_item.get("action") or "")
            if isinstance(processed_item, dict)
            else ""
        )
        if processed_action and processed_action != QZONE_ACTION_RETRY_LATER:
            return "already_processed"
        if not self.owner._qzone_auto_comment_in_active_window(post, comment):
            return "outside_active_window"
        if int(getattr(post, "uin", 0) or 0) != int(self_uin or 0):
            return "not_self_post"
        if int(getattr(comment, "uin", 0) or 0) == int(self_uin or 0):
            return "self_comment"
        return "" if parent_comment is not None else "missing_parent"

    def _qzone_auto_reply_thread_candidate(
        self,
        post,
        parent_comment,
        comment,
        *,
        self_uin: int,
        processed: dict,
        index: QzoneCommentIndex | None = None,
    ) -> bool:
        return not self.owner._qzone_auto_reply_thread_skip_reason(
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
        index: QzoneCommentIndex | None = None,
    ) -> str:
        item_key = _comment_key(post, comment)
        processed_item = (
            processed.get(item_key) if isinstance(processed, dict) else None
        )
        processed_action = (
            str(processed_item.get("action") or "")
            if isinstance(processed_item, dict)
            else ""
        )
        if processed_action and processed_action != QZONE_ACTION_RETRY_LATER:
            return "already_processed"
        if not self.owner._qzone_auto_comment_in_active_window(post, comment):
            return "outside_active_window"
        if int(getattr(post, "uin", 0) or 0) == int(self_uin or 0):
            return "not_friend_post"
        if parent_comment is None:
            return "missing_parent"
        if int(getattr(parent_comment, "uin", 0) or 0) != int(self_uin or 0):
            if not _comment_replies_to_self(comment, self_uin, index=index):
                return "reply_not_to_bot"
            if not (
                _comment_has_self_reply(post, parent_comment, self_uin, index=index)
                or _qzone_processed_thread_has_self_reply(
                    post, parent_comment, processed
                )
            ):
                return "missing_self_thread_reply"
            if _comment_thread_has_timed_self_reply(
                post, parent_comment, self_uin, index=index
            ):
                has_before, _has_after = _comment_thread_self_reply_bounds(
                    post, parent_comment, comment, self_uin, index=index
                )
                if not has_before:
                    return "missing_self_thread_reply"
        if int(getattr(comment, "uin", 0) or 0) == int(self_uin or 0):
            return "self_comment"
        if _comment_thread_has_self_reply_to(post, comment, self_uin, index=index):
            return "already_replied_to_target"
        is_photo = int(getattr(post, "appid", 311) or 311) == 4
        if not is_photo and _comment_thread_has_later_nonself_reply(
            post, parent_comment, comment, self_uin, index=index
        ):
            return "has_later_nonself_reply"
        content = str(getattr(comment, "content", "") or "").strip()
        return "" if content else "empty_comment"

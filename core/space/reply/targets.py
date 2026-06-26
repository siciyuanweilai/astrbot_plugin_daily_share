from __future__ import annotations

from typing import Any

from ..models import QzoneComment, QzonePost
from .identity import QzoneReplyIdentityMixin


class QzoneReplyTargetMixin(QzoneReplyIdentityMixin):
    """Build and validate Qzone reply targets before submitting."""

    @staticmethod
    def _prefer_h5_reply(comment: QzoneComment, *, parent_comment: QzoneComment | None = None) -> bool:
        return bool(
            str(getattr(comment, "submit_tid", "") or "").strip()
            or (
                parent_comment is not None
                and str(getattr(comment, "parent_tid", "") or "").strip()
            )
        )

    @classmethod
    def _can_try_addreply_ugc_thread_variant(
        cls,
        post: QzonePost,
        comment: QzoneComment,
        *,
        parent_comment: QzoneComment,
        child_seq: str,
    ) -> bool:
        child_seq = str(child_seq or "").strip()
        if not cls._is_short_numeric_comment_id(child_seq):
            return False
        try:
            if int(child_seq) <= 0:
                return False
        except ValueError:
            return False
        parent_ids = cls._comment_id_aliases(parent_comment)
        post_uin = int(getattr(post, "uin", 0) or 0)
        parent_uin = int(getattr(parent_comment, "uin", 0) or 0)
        reply_to_uin = int(getattr(comment, "reply_to_uin", 0) or getattr(comment, "raw_reply_to_uin", 0) or 0)
        known_self_uins = {uin for uin in (post_uin, parent_uin) if uin}
        if reply_to_uin and reply_to_uin not in known_self_uins:
            return False
        self_uin = reply_to_uin or post_uin
        if not self_uin:
            return False
        reply_to_tid = str(getattr(comment, "reply_to_tid", "") or "").strip()
        parent_tid = str(getattr(comment, "parent_tid", "") or "").strip()
        if not parent_tid:
            parent_tid = str(getattr(parent_comment, "submit_tid", "") or getattr(parent_comment, "tid", "") or "").strip()
        if parent_uin == self_uin and (not reply_to_tid or reply_to_tid in parent_ids):
            return True
        saw_self_reply_under_parent = False
        for item in getattr(post, "comments", []) or []:
            if int(getattr(item, "uin", 0) or 0) != self_uin:
                continue
            if parent_tid and str(getattr(item, "parent_tid", "") or "").strip() != parent_tid:
                continue
            saw_self_reply_under_parent = True
            if reply_to_tid in cls._comment_id_aliases(item):
                return True
        if reply_to_tid and reply_to_tid not in parent_ids:
            return False
        return saw_self_reply_under_parent and reply_to_uin == self_uin

    @staticmethod
    def _reply_submit_targets(
        post: QzonePost,
        comment: QzoneComment,
        *,
        parent_comment: QzoneComment | None = None,
    ) -> list[dict[str, Any]]:
        post_tid = str(getattr(post, "tid", "") or "").strip()
        comment_tid = str(getattr(comment, "tid", "") or "").strip()
        comment_submit_tid = str(getattr(comment, "submit_tid", "") or "").strip()
        comment_uin = int(getattr(comment, "uin", 0) or 0)
        parent_tid = str(
            getattr(parent_comment, "submit_tid", "")
            or getattr(parent_comment, "tid", "")
            or getattr(comment, "parent_tid", "")
            or ""
        ).strip()
        parent_uin = int(getattr(parent_comment, "uin", 0) or 0)
        if parent_tid == post_tid:
            parent_tid = ""

        targets: list[dict[str, Any]] = []

        def add(comment_id: str, comment_uin_value: int) -> None:
            comment_id = str(comment_id or "").strip()
            if not comment_id:
                return
            key = (comment_id, int(comment_uin_value or 0))
            if any((item["comment_id"], item["comment_uin"]) == key for item in targets):
                return
            targets.append({"comment_id": comment_id, "comment_uin": int(comment_uin_value or 0)})

        add(comment_tid, comment_uin)
        if comment_submit_tid and comment_tid and comment_tid != comment_submit_tid:
            add(comment_submit_tid, comment_uin)
        elif comment_submit_tid and not comment_tid:
            add(comment_submit_tid, comment_uin)
        if parent_comment is None and parent_tid:
            add(parent_tid, parent_uin or comment_uin)
        return targets

    @classmethod
    def _filter_thread_reply_targets(
        cls,
        post: QzonePost,
        comment: QzoneComment,
        *,
        parent_comment: QzoneComment | None,
        targets: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        comment_ids = {
            str(getattr(comment, "tid", "") or "").strip(),
            str(getattr(comment, "submit_tid", "") or "").strip(),
        }
        comment_ids.discard("")
        blocked_ids = {
            str(getattr(post, "tid", "") or "").strip(),
            str(getattr(parent_comment, "tid", "") or "").strip(),
            str(getattr(parent_comment, "submit_tid", "") or "").strip(),
            str(getattr(comment, "parent_tid", "") or "").strip(),
        }
        blocked_ids.discard("")

        filtered: list[dict[str, Any]] = []
        for target in targets or []:
            comment_id = str((target or {}).get("comment_id") or "").strip()
            if not comment_id or comment_id in blocked_ids:
                continue
            if parent_comment is not None and cls._is_short_numeric_comment_id(comment_id):
                continue
            if comment_ids and comment_id not in comment_ids:
                continue
            comment_uin = int((target or {}).get("comment_uin") or 0)
            key = (comment_id, comment_uin)
            if any((item["comment_id"], item["comment_uin"]) == key for item in filtered):
                continue
            filtered.append({"comment_id": comment_id, "comment_uin": comment_uin})
        return filtered

    @classmethod
    def unsafe_thread_reply_target_reason(
        cls,
        comment: QzoneComment,
        *,
        parent_comment: QzoneComment | None,
    ) -> str:
        return cls._unsafe_thread_reply_target_reason(comment, parent_comment=parent_comment)

    def has_thread_reply_submit_plan(
        self,
        post: QzonePost,
        comment: QzoneComment,
        *,
        parent_comment: QzoneComment | None,
    ) -> bool:
        if parent_comment is None:
            return False
        try:
            targets = self._reply_submit_targets(post, comment, parent_comment=parent_comment)
            targets = self._filter_thread_reply_targets(
                post,
                comment,
                parent_comment=parent_comment,
                targets=targets,
            )
            return bool(self._thread_reply_payload_variants(post, comment, parent_comment, targets))
        except Exception:
            return False

    @classmethod
    def _unsafe_thread_reply_target_reason(
        cls,
        comment: QzoneComment,
        *,
        parent_comment: QzoneComment | None,
    ) -> str:
        if parent_comment is None:
            return ""
        comment_tid = str(getattr(comment, "tid", "") or "").strip()
        parent_tid = str(getattr(comment, "parent_tid", "") or "").strip()
        submit_tid = str(getattr(comment, "submit_tid", "") or "").strip()
        raw_tid = str(getattr(comment, "raw_tid", "") or "").strip()
        parent_ids = cls._comment_id_aliases(parent_comment)
        parent_ids.update(text for text in (parent_tid,) if text)
        if not comment_tid or "_r_" not in comment_tid or not parent_ids:
            return ""
        if parent_tid and not any(comment_tid.startswith(f"{parent_id}_r_") for parent_id in parent_ids):
            return ""
        if not cls._is_short_numeric_comment_id(submit_tid or raw_tid):
            return ""
        if submit_tid and submit_tid != raw_tid and raw_tid and not cls._is_short_numeric_comment_id(raw_tid):
            return ""
        return "synthetic_thread_tid_without_real_submit_id"

    @staticmethod
    def _is_short_numeric_comment_id(value: str) -> bool:
        text = str(value or "").strip()
        return bool(text and text.isdigit() and len(text) <= 6)

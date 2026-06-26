from __future__ import annotations

from ..models import QzoneComment


class QzoneReplyIdentityMixin:
    """Shared comment identity helpers for reply submit and verification."""

    @staticmethod
    def _comment_id_aliases(comment: QzoneComment | None) -> set[str]:
        if comment is None:
            return set()
        return {
            text
            for text in (
                str(getattr(comment, "tid", "") or "").strip(),
                str(getattr(comment, "submit_tid", "") or "").strip(),
            )
            if text
        }

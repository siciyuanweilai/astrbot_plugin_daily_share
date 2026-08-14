from __future__ import annotations

from ..methodset import QzoneMethodSet
from ..models import QzoneComment


class QzoneReplyIdentityService(QzoneMethodSet):
    """评论提交与校验共用的评论标识工具。"""

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

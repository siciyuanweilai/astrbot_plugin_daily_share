from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import QzoneComment

if TYPE_CHECKING:
    from ..qzone import QzoneService


class QzoneReplyIdentityService:
    """评论提交与校验共用的评论标识工具。"""

    def __init__(self, owner: QzoneService) -> None:
        self.owner = owner

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

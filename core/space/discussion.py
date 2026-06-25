from __future__ import annotations

from .remark import (
    QzoneCommentDeleteMixin,
    QzoneCommentPostMixin,
    QzoneCommentReplyMixin,
    QzoneCommentUtilMixin,
)
from .reply import QzoneReplySubmitMixin, QzoneReplyVerifyMixin


class QzoneCommentServiceMixin(
    QzoneCommentReplyMixin,
    QzoneCommentPostMixin,
    QzoneCommentDeleteMixin,
    QzoneCommentUtilMixin,
    QzoneReplySubmitMixin,
    QzoneReplyVerifyMixin,
):
    """QQ 空间评论、回评与删除能力。"""


__all__ = ["QzoneCommentServiceMixin"]

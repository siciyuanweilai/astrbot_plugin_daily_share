from __future__ import annotations

from .thumb import QzoneVideoCoverInitMixin, QzoneVideoCoverPayloadMixin, QzoneVideoCoverUploadMixin


class QzoneVideoCoverMixin(
    QzoneVideoCoverUploadMixin,
    QzoneVideoCoverInitMixin,
    QzoneVideoCoverPayloadMixin,
):
    """QQ 空间视频封面上传能力。"""


__all__ = ["QzoneVideoCoverMixin"]

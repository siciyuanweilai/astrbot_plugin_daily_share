from __future__ import annotations

from .album import QzoneAlbumMixin
from .attachments import QzoneVideoCoverMixin
from .videos import (
    QzoneVideoBizMixin,
    QzoneVideoChunkMixin,
    QzoneVideoConfirmMixin,
    QzoneVideoCoverUploadMixin,
    QzoneVideoUploadMixin,
)


class QzoneVideoMixin(
    QzoneVideoCoverMixin,
    QzoneAlbumMixin,
    QzoneVideoBizMixin,
    QzoneVideoChunkMixin,
    QzoneVideoCoverUploadMixin,
    QzoneVideoConfirmMixin,
    QzoneVideoUploadMixin,
):
    """QQ 空间视频上传能力。"""


__all__ = ["QzoneVideoMixin"]

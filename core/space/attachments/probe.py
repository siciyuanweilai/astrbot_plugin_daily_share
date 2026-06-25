from __future__ import annotations

from .detect import (
    QzoneAlbumProbeBaseMixin,
    QzoneAlbumProbeConfirmMixin,
    QzoneAlbumProbeEvidenceMixin,
    QzoneAlbumProbeQueryMixin,
)


class QzoneAlbumProbeMixin(
    QzoneAlbumProbeConfirmMixin,
    QzoneAlbumProbeQueryMixin,
    QzoneAlbumProbeEvidenceMixin,
    QzoneAlbumProbeBaseMixin,
):
    """QQ 空间相册视频公开性探测能力。"""


__all__ = ["QzoneAlbumProbeMixin"]

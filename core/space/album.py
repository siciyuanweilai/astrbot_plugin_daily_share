from __future__ import annotations

from .albums import QzoneAlbumBaseMixin, QzoneAlbumListMixin, QzoneAlbumVideoMixin
from .h5 import QzoneH5TransportMixin
from .attachments import QzoneAlbumPublicMixin, QzoneAlbumSelectMixin


class QzoneAlbumMixin(
    QzoneAlbumSelectMixin,
    QzoneAlbumPublicMixin,
    QzoneH5TransportMixin,
    QzoneAlbumBaseMixin,
    QzoneAlbumListMixin,
    QzoneAlbumVideoMixin,
):
    """QQ 空间相册与视频库能力。"""


__all__ = ["QzoneAlbumMixin"]

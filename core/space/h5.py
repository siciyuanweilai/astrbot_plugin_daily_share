from __future__ import annotations

from .hfive import QzoneH5BaseMixin, QzoneH5ErrorMixin, QzoneH5RequestMixin
from .transport import QzoneH5CookieMixin, QzoneH5NativeMixin


class QzoneH5TransportMixin(
    QzoneH5NativeMixin,
    QzoneH5CookieMixin,
    QzoneH5BaseMixin,
    QzoneH5ErrorMixin,
    QzoneH5RequestMixin,
):
    """QQ 空间 H5 传输能力。"""


__all__ = ["QzoneH5TransportMixin"]

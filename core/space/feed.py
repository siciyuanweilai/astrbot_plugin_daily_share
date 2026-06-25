from __future__ import annotations

from .feeds import (
    QzoneFeedDetailMixin,
    QzoneFeedExtraMixin,
    QzoneFeedHomeMixin,
    QzoneFeedPostsMixin,
    QzoneFeedRecentMixin,
)
from .merge import QzoneFeedMergeMixin
from .query import QzoneFeedQueryMixin


class QzoneFeedServiceMixin(
    QzoneFeedQueryMixin,
    QzoneFeedMergeMixin,
    QzoneFeedDetailMixin,
    QzoneFeedPostsMixin,
    QzoneFeedRecentMixin,
    QzoneFeedHomeMixin,
    QzoneFeedExtraMixin,
):
    """QQ 空间动态查询能力。"""


__all__ = ["QzoneFeedServiceMixin"]

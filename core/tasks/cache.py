from __future__ import annotations

from .snapshot import (
    TaskNewsCacheFocusMixin,
    TaskNewsCacheFormatMixin,
    TaskNewsCacheLookupMixin,
    TaskNewsCacheNormalizeMixin,
    TaskNewsCacheStoreMixin,
)


class TaskNewsCacheMixin(
    TaskNewsCacheLookupMixin,
    TaskNewsCacheFormatMixin,
    TaskNewsCacheFocusMixin,
    TaskNewsCacheStoreMixin,
    TaskNewsCacheNormalizeMixin,
):
    """新闻快照缓存和缓存链接查询辅助方法。"""


__all__ = ["TaskNewsCacheMixin"]

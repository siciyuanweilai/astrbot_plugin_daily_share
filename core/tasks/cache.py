from __future__ import annotations

from .snapshot import TaskNewsCacheLookupService


class TaskNewsCacheService(TaskNewsCacheLookupService):
    """新闻快照缓存和缓存链接查询辅助方法。"""


__all__ = ["TaskNewsCacheService"]

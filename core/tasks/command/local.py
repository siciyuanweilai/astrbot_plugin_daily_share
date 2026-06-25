from __future__ import annotations

from .manual import (
    TaskCommandLocalMediaMixin,
    TaskCommandLocalNewsMixin,
    TaskCommandLocalRecordMixin,
    TaskCommandLocalResolveMixin,
    TaskCommandLocalRunMixin,
)


class TaskCommandLocalMixin(
    TaskCommandLocalRunMixin,
    TaskCommandLocalRecordMixin,
    TaskCommandLocalMediaMixin,
    TaskCommandLocalNewsMixin,
    TaskCommandLocalResolveMixin,
):
    """自然语言本地分享执行能力。"""


__all__ = ["TaskCommandLocalMixin"]

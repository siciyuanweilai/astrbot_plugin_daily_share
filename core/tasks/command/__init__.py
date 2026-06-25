from __future__ import annotations

from .picture import TaskCommandImageMixin
from .local import TaskCommandLocalMixin
from .runner import TaskCommandRunnerMixin


class TaskCommandShareMixin(
    TaskCommandRunnerMixin,
    TaskCommandLocalMixin,
    TaskCommandImageMixin,
):
    """自然语言触发的分享后台任务。"""


__all__ = ["TaskCommandShareMixin"]

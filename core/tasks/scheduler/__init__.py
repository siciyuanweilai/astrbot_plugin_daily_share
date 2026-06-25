from __future__ import annotations

from .auto import TaskSchedulerAutoMixin
from .cron import TaskSchedulerCronMixin
from .delay import TaskSchedulerDelayMixin
from .random import TaskSchedulerRandomMixin
from .recovery import TaskSchedulerRecoveryMixin
from .setup import TaskSchedulerSetupMixin
from .smart import TaskSchedulerSmartMixin
from .triggers import TaskSchedulerTriggerMixin


class TaskSchedulerMixin(
    TaskSchedulerSetupMixin,
    TaskSchedulerAutoMixin,
    TaskSchedulerDelayMixin,
    TaskSchedulerCronMixin,
    TaskSchedulerRecoveryMixin,
    TaskSchedulerRandomMixin,
    TaskSchedulerSmartMixin,
    TaskSchedulerTriggerMixin,
):
    """定时任务注册、随机延迟排程和未完成任务恢复。"""


__all__ = ["TaskSchedulerMixin"]

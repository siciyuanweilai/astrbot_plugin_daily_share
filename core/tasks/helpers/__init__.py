from __future__ import annotations

from typing import TYPE_CHECKING

from ..taskbase import TaskServiceBase
from .arguments import TaskHelperArgsService
from .imagery import TaskHelperMediaService
from .ledger import TaskHelperRecordService
from .lock import TaskHelperLockService
from .material import TaskHelperContextService
from .period import TaskHelperPeriodService
from .sync import TaskHelperSyncService

if TYPE_CHECKING:
    from ..components import TaskServices
    from ..runtime import TaskRuntime
    from ..taskbase import TaskConfigState, TaskSharedState


class TaskExecutorHelperService(TaskServiceBase):
    """持有具名辅助组件，调用方直接访问对应能力。"""

    def __init__(
        self,
        runtime: TaskRuntime,
        config: TaskConfigState,
        state: TaskSharedState,
    ) -> None:
        super().__init__(runtime, config, state)
        args = (runtime, config, state)
        self.arguments = TaskHelperArgsService(*args)
        self.context = TaskHelperContextService(*args)
        self.media = TaskHelperMediaService(*args)
        self.locks = TaskHelperLockService(*args)
        self.records = TaskHelperRecordService(*args)
        self.period = TaskHelperPeriodService(*args)
        self.sync = TaskHelperSyncService(*args)

    def connect(self, services: TaskServices) -> None:
        super().connect(services)
        for component in (
            self.arguments,
            self.context,
            self.media,
            self.locks,
            self.records,
            self.period,
            self.sync,
        ):
            component.connect(services)


__all__ = ["TaskExecutorHelperService"]

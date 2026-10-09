from __future__ import annotations

from dataclasses import dataclass, fields

from .briefing import TaskBriefingService
from .cache import TaskNewsCacheService
from .cachemedia import TaskDeliveryAssetsService
from .command import TaskCommandShareService
from .executor import TaskExecutorService
from .helpers import TaskExecutorHelperService
from .moments import TaskQzoneService
from .progress import TaskProgressService
from .qinteract import TaskQzoneAutoCommentService
from .runtime import TaskRuntime
from .scheduler import TaskSchedulerService
from .selector import TaskTypeSelectorService
from .targets import TaskTargetService
from .taskbase import TaskConfigState, TaskServiceBase, TaskSharedState
from .taskdelivery import TaskDeliveryService
from .weixin import TaskDeliveryWeixinService


class QzoneInteractionService(TaskServiceBase, TaskQzoneAutoCommentService):
    """将 QQ 空间互动策略绑定到共享任务运行时。"""


@dataclass(frozen=True, slots=True)
class TaskServices:
    """任务编排使用的具名服务容器。"""

    snapshots: TaskNewsCacheService
    targets: TaskTargetService
    schedule: TaskSchedulerService
    progress: TaskProgressService
    qzone_interaction: QzoneInteractionService
    executor_helpers: TaskExecutorHelperService
    type_selector: TaskTypeSelectorService
    briefing: TaskBriefingService
    qzone_share: TaskQzoneService
    command_share: TaskCommandShareService
    share: TaskExecutorService
    delivery_assets: TaskDeliveryAssetsService
    weixin_delivery: TaskDeliveryWeixinService
    delivery: TaskDeliveryService

    @classmethod
    def build(
        cls,
        runtime: TaskRuntime,
        config: TaskConfigState,
        state: TaskSharedState,
    ) -> TaskServices:
        args = (runtime, config, state)
        services = cls(
            snapshots=TaskNewsCacheService(*args),
            targets=TaskTargetService(*args),
            schedule=TaskSchedulerService(*args),
            progress=TaskProgressService(*args),
            qzone_interaction=QzoneInteractionService(*args),
            executor_helpers=TaskExecutorHelperService(*args),
            type_selector=TaskTypeSelectorService(*args),
            briefing=TaskBriefingService(*args),
            qzone_share=TaskQzoneService(*args),
            command_share=TaskCommandShareService(*args),
            share=TaskExecutorService(*args),
            delivery_assets=TaskDeliveryAssetsService(*args),
            weixin_delivery=TaskDeliveryWeixinService(*args),
            delivery=TaskDeliveryService(*args),
        )
        for service in services:
            service.connect(services)
        return services

    def __iter__(self):
        for field in fields(self):
            yield getattr(self, field.name)

    def __len__(self) -> int:
        return len(fields(self))


__all__ = [
    "TaskConfigState",
    "TaskServiceBase",
    "TaskServices",
    "TaskSharedState",
]

from .artwork import TaskExecutorMediaMixin
from .flow import TaskExecutorFlowMixin
from .newsitem import TaskExecutorNewsMixin
from .send import TaskExecutorSendMixin
from .targetplan import TaskExecutorTargetMixin


class TaskExecutorMixin(
    TaskExecutorTargetMixin,
    TaskExecutorNewsMixin,
    TaskExecutorMediaMixin,
    TaskExecutorSendMixin,
    TaskExecutorFlowMixin,
):
    """分享主流程。"""


__all__ = ["TaskExecutorMixin"]

from .arguments import TaskHelperArgsMixin
from .context import TaskHelperContextMixin
from .imagery import TaskHelperMediaMixin
from .ledger import TaskHelperRecordMixin
from .lock import TaskHelperLockMixin
from .period import TaskHelperPeriodMixin
from .sync import TaskHelperSyncMixin


class TaskExecutorHelperMixin(
    TaskHelperPeriodMixin,
    TaskHelperRecordMixin,
    TaskHelperLockMixin,
    TaskHelperArgsMixin,
    TaskHelperContextMixin,
    TaskHelperMediaMixin,
    TaskHelperSyncMixin,
):
    """分享执行器的通用辅助方法。"""


__all__ = ["TaskExecutorHelperMixin"]

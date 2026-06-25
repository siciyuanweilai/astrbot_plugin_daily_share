from .localnews import TaskCommandLocalNewsMixin
from .logbook import TaskCommandLocalRecordMixin
from .mediafile import TaskCommandLocalMediaMixin
from .resolve import TaskCommandLocalResolveMixin
from .run import TaskCommandLocalRunMixin


__all__ = [
    "TaskCommandLocalMediaMixin",
    "TaskCommandLocalNewsMixin",
    "TaskCommandLocalRecordMixin",
    "TaskCommandLocalResolveMixin",
    "TaskCommandLocalRunMixin",
]

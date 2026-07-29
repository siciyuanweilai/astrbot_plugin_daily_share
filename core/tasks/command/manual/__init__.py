from .localnews import TaskCommandLocalNewsService
from .logbook import TaskCommandLocalRecordService
from .mediafile import TaskCommandLocalMediaService
from .resolve import TaskCommandLocalResolveService
from .run import TaskCommandLocalRunService


__all__ = [
    "TaskCommandLocalMediaService",
    "TaskCommandLocalNewsService",
    "TaskCommandLocalRecordService",
    "TaskCommandLocalResolveService",
    "TaskCommandLocalRunService",
]

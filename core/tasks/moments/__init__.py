from .content import TaskQzoneContentMixin
from .digest import TaskQzoneNewsMixin
from .illustration import TaskQzoneMediaMixin
from .pipeline import TaskQzoneFlowMixin
from .release import TaskQzonePublishMixin


class TaskQzoneMixin(
    TaskQzoneNewsMixin,
    TaskQzoneContentMixin,
    TaskQzoneMediaMixin,
    TaskQzonePublishMixin,
    TaskQzoneFlowMixin,
):
    """QQ 空间独立分享流程。"""


__all__ = ["TaskQzoneMixin"]

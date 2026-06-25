from __future__ import annotations

from .file import DashboardMediaFileMixin
from .kind import DashboardMediaKindMixin
from .page import DashboardMediaPageMixin
from .preview import DashboardMediaPreviewMixin


class DashboardMediaMixin(
    DashboardMediaPageMixin,
    DashboardMediaPreviewMixin,
    DashboardMediaFileMixin,
    DashboardMediaKindMixin,
):
    """仪表盘媒体能力。"""


__all__ = ["DashboardMediaMixin"]

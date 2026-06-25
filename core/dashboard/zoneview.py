from __future__ import annotations

from pathlib import Path
import sys

_package = sys.modules.get(__package__)
if _package is not None and hasattr(_package, "__path__") and not list(_package.__path__):
    _package.__path__.append(str(Path(__file__).resolve().parent))

from .qpanel import (
    DashboardQzoneActionMixin,
    DashboardQzoneEntryMixin,
    DashboardQzoneFeedMixin,
    DashboardQzonePublishMixin,
    DashboardQzoneRelationMixin,
    DashboardQzoneUploadMixin,
    DashboardQzoneUtilMixin,
)


class DashboardQzoneMixin(
    DashboardQzoneActionMixin,
    DashboardQzoneEntryMixin,
    DashboardQzoneFeedMixin,
    DashboardQzonePublishMixin,
    DashboardQzoneRelationMixin,
    DashboardQzoneUploadMixin,
    DashboardQzoneUtilMixin,
):
    """仪表盘 QQ 空间接口能力。"""


__all__ = ["DashboardQzoneMixin"]

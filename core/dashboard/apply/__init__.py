from __future__ import annotations

from .field import DashboardApplyFieldMixin
from .general import DashboardApplyBasicMixin
from .payloads import DashboardApplyPayloadMixin
from .schedule import DashboardApplyScheduleMixin
from .section import DashboardApplySectionMixin
from .zonectl import DashboardApplyQzoneMixin


class DashboardConfigApplyMixin(
    DashboardApplyPayloadMixin,
    DashboardApplySectionMixin,
    DashboardApplyQzoneMixin,
    DashboardApplyBasicMixin,
    DashboardApplyScheduleMixin,
    DashboardApplyFieldMixin,
):
    """设置页配置提交处理。"""

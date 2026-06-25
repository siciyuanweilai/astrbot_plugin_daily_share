from __future__ import annotations

from .audiencectl import DashboardRouteTargetMixin
from .operation import DashboardRouteActionMixin
from .retry import DashboardRouteRetryMixin
from .search import DashboardRouteQueryMixin
from .settings import DashboardRouteConfigMixin
from .statusview import DashboardRouteStatusMixin


class DashboardRoutesMixin(
    DashboardRouteActionMixin,
    DashboardRouteConfigMixin,
    DashboardRouteQueryMixin,
    DashboardRouteRetryMixin,
    DashboardRouteStatusMixin,
    DashboardRouteTargetMixin,
):
    """仪表盘路由能力。"""

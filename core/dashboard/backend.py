from .api import DashboardConfigMixin
from .events import DashboardEventsMixin
from .gallery import DashboardMediaMixin
from .meta import DashboardConfigMetaMixin
from .routes import DashboardRoutesMixin
from .rosterhub import DashboardTargetsMixin
from .server import DashboardBaseMixin
from .common import PAGE_PREFERENCES_FILE
from .validation import DashboardConfigValidationMixin
from .zoneview import DashboardQzoneMixin


class DashboardBackendMixin(
    DashboardQzoneMixin,
    DashboardRoutesMixin,
    DashboardEventsMixin,
    DashboardMediaMixin,
    DashboardConfigValidationMixin,
    DashboardConfigMetaMixin,
    DashboardConfigMixin,
    DashboardTargetsMixin,
    DashboardBaseMixin,
):
    """聚合仪表盘页面 API、配置、媒体和目标管理能力。"""


__all__ = ["DashboardBackendMixin", "PAGE_PREFERENCES_FILE"]

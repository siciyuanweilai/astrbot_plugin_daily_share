from __future__ import annotations

import asyncio

from .events import DashboardEventsService
from .qpanel.network import DashboardQzoneRelationService
from .qpanel.operate import DashboardQzoneActionService
from .qpanel.paneltool import DashboardQzoneUtilService
from .qpanel.posting import DashboardQzonePublishService
from .qpanel.qzoneportal import DashboardQzoneEntryService
from .qpanel.stream import DashboardQzoneFeedService
from .qpanel.uploader import DashboardQzoneUploadService
from .server import DashboardBaseService


class DashboardQzoneService:
    """可独立测试的仪表盘 QQ 空间组件容器。"""

    def __init__(self) -> None:
        self._page_event_clients: set[asyncio.Queue] = set()
        self._page_event_seq = 0
        self.server = DashboardBaseService(self)
        self.events = DashboardEventsService(self)
        self.qzone_tools = DashboardQzoneUtilService(self)
        self.qzone_upload = DashboardQzoneUploadService(self)
        self.qzone_relations = DashboardQzoneRelationService(self)
        self.qzone_publish = DashboardQzonePublishService(self)
        self.qzone_feed = DashboardQzoneFeedService(self)
        self.qzone_entry = DashboardQzoneEntryService(self)
        self.qzone_actions = DashboardQzoneActionService(self)


__all__ = ["DashboardQzoneService"]

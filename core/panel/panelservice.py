from __future__ import annotations

import asyncio

from .activity import DashboardActivityService as _PanelComponent5
from .apply.field import DashboardApplyFieldService as _PanelComponent12
from .apply.general import DashboardApplyBasicService as _PanelComponent10
from .apply.scheduleapply import DashboardApplyScheduleService as _PanelComponent11
from .apply.section import DashboardApplySectionService as _PanelComponent8
from .apply.submission import DashboardApplyPayloadService as _PanelComponent7
from .apply.zonectl import DashboardApplyQzoneService as _PanelComponent9
from .events import DashboardEventsService as _PanelComponent24
from .gallery.file import DashboardMediaFileService as _PanelComponent21
from .gallery.kind import DashboardMediaKindService as _PanelComponent22
from .gallery.page import DashboardMediaPageService as _PanelComponent19
from .gallery.preview import DashboardMediaPreviewService as _PanelComponent20
from .jobs import DashboardJobsService as _PanelComponent4
from .labels import DashboardLabelsService as _PanelComponent2
from .meta import DashboardConfigMetaService as _PanelComponent17
from .payload import DashboardConfigPayloadService as _PanelComponent14
from .qpanel.network import DashboardQzoneRelationService as _PanelComponent34
from .qpanel.operate import DashboardQzoneActionService as _PanelComponent38
from .qpanel.paneltool import DashboardQzoneUtilService as _PanelComponent32
from .qpanel.posting import DashboardQzonePublishService as _PanelComponent35
from .qpanel.qzoneportal import DashboardQzoneEntryService as _PanelComponent37
from .qpanel.stream import DashboardQzoneFeedService as _PanelComponent36
from .qpanel.uploader import DashboardQzoneUploadService as _PanelComponent33
from .refresh import DashboardConfigRefreshService as _PanelComponent15
from .roster import DashboardTargetConfigService as _PanelComponent3
from .routes.audiencectl import DashboardRouteTargetService as _PanelComponent25
from .routes.configroute import DashboardRouteConfigService as _PanelComponent29
from .routes.operation import DashboardRouteActionService as _PanelComponent30
from .routes.retry import DashboardRouteRetryService as _PanelComponent27
from .routes.search import DashboardRouteQueryService as _PanelComponent28
from .routes.statusview import DashboardRouteStatusService as _PanelComponent26
from .server import DashboardBaseService as _PanelComponent1
from .validation import DashboardConfigValidationService as _PanelComponent18


class PanelRuntime:
    """聚合仪表盘路由、配置、媒体和 QQ 空间组件。"""

    def __init__(self, plugin) -> None:
        self.plugin = plugin
        self._page_action_seq = 0
        self._page_action_runs: dict[str, dict] = {}
        self._page_config_schema_raw_cache: dict | None = None
        self._page_config_schema_meta_cache: dict | None = None
        self._page_target_label_cache_data: dict[str, object] = {}
        self._page_event_clients: set[asyncio.Queue] = set()
        self._page_event_seq = 0
        self._registered_web_api_routes: set[tuple[str, tuple[str, ...]]] = set()

        self.server = _PanelComponent1(self)
        self.labels = _PanelComponent2(self)
        self.targets = _PanelComponent3(self)
        self.jobs = _PanelComponent4(self)
        self.activity = _PanelComponent5(self)
        self.apply = _PanelComponent7(self)
        self.sections = _PanelComponent8(self)
        self.qzone_apply = _PanelComponent9(self)
        self.general_apply = _PanelComponent10(self)
        self.schedule_apply = _PanelComponent11(self)
        self.fields = _PanelComponent12(self)
        self.payload = _PanelComponent14(self)
        self.refresh = _PanelComponent15(self)
        self.meta = _PanelComponent17(self)
        self.validation = _PanelComponent18(self)
        self.media_page = _PanelComponent19(self)
        self.media_preview = _PanelComponent20(self)
        self.media_files = _PanelComponent21(self)
        self.media_kind = _PanelComponent22(self)
        self.events = _PanelComponent24(self)
        self.target_routes = _PanelComponent25(self)
        self.status_routes = _PanelComponent26(self)
        self.retry_routes = _PanelComponent27(self)
        self.query_routes = _PanelComponent28(self)
        self.config_routes = _PanelComponent29(self)
        self.action_routes = _PanelComponent30(self)
        self.qzone_tools = _PanelComponent32(self)
        self.qzone_upload = _PanelComponent33(self)
        self.qzone_relations = _PanelComponent34(self)
        self.qzone_publish = _PanelComponent35(self)
        self.qzone_feed = _PanelComponent36(self)
        self.qzone_entry = _PanelComponent37(self)
        self.qzone_actions = _PanelComponent38(self)

    @property
    def context(self):
        return self.plugin.context

    @property
    def config(self):
        return self.plugin.config

    @property
    def scheduler(self):
        return self.plugin.scheduler

    @property
    def db(self):
        return self.plugin.db

    @db.setter
    def db(self, value) -> None:
        self.plugin.db = value

    @property
    def task_manager(self):
        return self.plugin.task_manager

    @property
    def command_handler(self):
        return self.plugin.command_handler

    @property
    def ctx_service(self):
        return self.plugin.ctx_service

    @ctx_service.setter
    def ctx_service(self, value) -> None:
        self.plugin.ctx_service = value

    @property
    def news_service(self):
        return self.plugin.news_service

    @property
    def image_service(self):
        return self.plugin.image_service

    @property
    def llm_service(self):
        return self.plugin.llm_service

    @property
    def content_service(self):
        return self.plugin.content_service

    @property
    def qzone_service(self):
        return self.plugin.qzone_service

    @qzone_service.setter
    def qzone_service(self, value) -> None:
        self.plugin.qzone_service = value

    @property
    def data_dir(self):
        return self.plugin.data_dir

    @data_dir.setter
    def data_dir(self, value) -> None:
        self.plugin.data_dir = value

    @property
    def page_preferences_file(self):
        return self.plugin.page_preferences_file

    @property
    def _lock(self):
        return self.plugin._lock

    @property
    def _is_terminated(self):
        return self.plugin._is_terminated

    @property
    def basic_conf(self):
        return self.plugin.basic_conf

    @basic_conf.setter
    def basic_conf(self, value) -> None:
        self.plugin.basic_conf = value

    @property
    def image_conf(self):
        return self.plugin.image_conf

    @image_conf.setter
    def image_conf(self, value) -> None:
        self.plugin.image_conf = value

    @property
    def tts_conf(self):
        return self.plugin.tts_conf

    @tts_conf.setter
    def tts_conf(self, value) -> None:
        self.plugin.tts_conf = value

    @property
    def qzone_conf(self):
        return self.plugin.qzone_conf

    @qzone_conf.setter
    def qzone_conf(self, value) -> None:
        self.plugin.qzone_conf = value

    @property
    def receiver_conf(self):
        return self.plugin.receiver_conf

    @receiver_conf.setter
    def receiver_conf(self, value) -> None:
        self.plugin.receiver_conf = value

    @property
    def extra_shares_conf(self):
        return self.plugin.extra_shares_conf

    @extra_shares_conf.setter
    def extra_shares_conf(self, value) -> None:
        self.plugin.extra_shares_conf = value

    @property
    def context_conf(self):
        return self.plugin.context_conf

    @context_conf.setter
    def context_conf(self, value) -> None:
        self.plugin.context_conf = value

    @property
    def news_conf(self):
        return self.plugin.news_conf

    @news_conf.setter
    def news_conf(self, value) -> None:
        self.plugin.news_conf = value

    @property
    def xiaohongshu_conf(self):
        return self.plugin.xiaohongshu_conf

    @xiaohongshu_conf.setter
    def xiaohongshu_conf(self, value) -> None:
        self.plugin.xiaohongshu_conf = value

    @property
    def contact_aliases(self):
        return self.plugin.contact_aliases

    @contact_aliases.setter
    def contact_aliases(self, value) -> None:
        self.plugin.contact_aliases = value

    def get_contact_alias(self, target_id: str) -> str:
        return self.plugin.support_service.get_contact_alias(target_id)

    def track_task(self, coro):
        return self.plugin.runtime_service.track_task(coro)

    def is_share_busy(
        self, target_uid: str | None = None, *, global_scope: bool = False
    ) -> bool:
        return self.plugin.runtime_service.is_share_busy(
            target_uid, global_scope=global_scope
        )

    async def save_config_file(self) -> None:
        await self.plugin.runtime_service.save_config_file()


class DashboardService:
    """仪表盘的组合式公共服务边界。"""

    def __init__(self, plugin) -> None:
        self.operations = PanelRuntime(plugin)

    def register_web_apis(self) -> None:
        self.operations.server.register_web_apis()

    def shutdown(self) -> None:
        """结束面板事件流并移除本插件注册的网页接口。"""
        self.operations.events.shutdown_event_streams()
        self.operations.server.unregister_web_apis()

    async def load_config_schema(self) -> dict:
        return await self.operations.meta.load_config_schema()

    def emit_dashboard_event(
        self,
        event_type: str = "status",
        data: dict | None = None,
    ) -> None:
        self.operations.events.emit_dashboard_event(event_type, data)

    async def save_config_and_refresh_runtime(self, **kwargs):
        return await self.operations.refresh.save_config_and_refresh_runtime(**kwargs)


__all__ = ["DashboardService"]

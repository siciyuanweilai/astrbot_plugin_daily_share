from .eventdelivery import send_event_message
from .host.alias import PluginAliasService
from .host.helper import PluginToolContextService
from .host.job import PluginShareJobService
from .host.manual import PluginManualShareService
from .host.outbox.broadcast import ImageDeliveryShareService
from .host.outbox.news import ImageNewsShareService
from .host.outbox.static import ImageStaticShareService
from .host.permission import PluginPermissionService
from .host.routing.bulletin import PluginShareBriefingRouteService
from .host.routing.share import PluginShareMainRouteService
from .host.routing.start import PluginShareStartRouteService
from .host.routing.typed import PluginShareTypedRouteService
from .host.space import PluginQzoneService
from .host.tools import PluginToolService


class SupportRuntime:
    """聚合命令、工具、权限、别名和 QQ 空间操作组件。"""

    def __init__(self, plugin) -> None:
        self.plugin = plugin
        self.tools = PluginToolService(self)
        self.tool_context = PluginToolContextService(self)
        self.permissions = PluginPermissionService(self)
        self.manual = PluginManualShareService(self)
        self.jobs = PluginShareJobService(self)
        self.news_outbox = ImageNewsShareService(self)
        self.delivery_outbox = ImageDeliveryShareService(self)
        self.static_outbox = ImageStaticShareService(self)
        self.briefing_route = PluginShareBriefingRouteService(self)
        self.start_route = PluginShareStartRouteService(self)
        self.typed_route = PluginShareTypedRouteService(self)
        self.main_route = PluginShareMainRouteService(self)
        self.qzone = PluginQzoneService(self)
        self.aliases = PluginAliasService(self)

    async def send_event(self, event, chain) -> None:
        await send_event_message(event, chain)

    @property
    def context(self):
        return self.plugin.context

    @property
    def config(self):
        return self.plugin.config

    @property
    def db(self):
        return self.plugin.db

    @property
    def ctx_service(self):
        return self.plugin.ctx_service

    @property
    def news_service(self):
        return self.plugin.news_service

    @property
    def qzone_service(self):
        return self.plugin.qzone_service

    @qzone_service.setter
    def qzone_service(self, value) -> None:
        self.plugin.qzone_service = value

    @property
    def task_manager(self):
        return self.plugin.task_manager

    @property
    def command_handler(self):
        return self.plugin.command_handler

    @property
    def receiver_conf(self):
        return self.plugin.receiver_conf

    @receiver_conf.setter
    def receiver_conf(self, value) -> None:
        self.plugin.receiver_conf = value

    @property
    def basic_conf(self):
        return self.plugin.basic_conf

    @basic_conf.setter
    def basic_conf(self, value) -> None:
        self.plugin.basic_conf = value

    @property
    def extra_shares_conf(self):
        return self.plugin.extra_shares_conf

    @extra_shares_conf.setter
    def extra_shares_conf(self, value) -> None:
        self.plugin.extra_shares_conf = value

    @property
    def qzone_conf(self):
        return self.plugin.qzone_conf

    @qzone_conf.setter
    def qzone_conf(self, value) -> None:
        self.plugin.qzone_conf = value

    @property
    def contact_aliases(self):
        return self.plugin.contact_aliases

    @contact_aliases.setter
    def contact_aliases(self, value) -> None:
        self.plugin.contact_aliases = value

    @property
    def _is_terminated(self):
        return self.plugin._is_terminated

    @property
    def _cached_adapter_id(self):
        return self.plugin._cached_adapter_id

    @_cached_adapter_id.setter
    def _cached_adapter_id(self, value) -> None:
        self.plugin._cached_adapter_id = value

    @property
    def _cached_qq_adapter_id(self):
        return self.plugin._cached_qq_adapter_id

    @_cached_qq_adapter_id.setter
    def _cached_qq_adapter_id(self, value) -> None:
        self.plugin._cached_qq_adapter_id = value

    @property
    def _cached_weixin_adapter_id(self):
        return self.plugin._cached_weixin_adapter_id

    @_cached_weixin_adapter_id.setter
    def _cached_weixin_adapter_id(self, value) -> None:
        self.plugin._cached_weixin_adapter_id = value

    def track_task(self, coro):
        return self.plugin.runtime_service.track_task(coro)

    def get_share_lock(
        self, target_uid: str | None = None, *, global_scope: bool = False
    ):
        return self.plugin.runtime_service.get_share_lock(
            target_uid, global_scope=global_scope
        )

    def is_share_busy(
        self, target_uid: str | None = None, *, global_scope: bool = False
    ) -> bool:
        return self.plugin.runtime_service.is_share_busy(
            target_uid, global_scope=global_scope
        )

    def release_idle_share_lock(self, target_uid: str | None = None) -> None:
        self.plugin.runtime_service.release_idle_share_lock(target_uid)

    async def save_config_file(self) -> None:
        await self.plugin.runtime_service.save_config_file()

    async def save_config_and_refresh_runtime(self, **kwargs):
        return await self.plugin.dashboard_service.save_config_and_refresh_runtime(
            **kwargs
        )

    def emit_dashboard_event(
        self, event_type: str = "status", data: dict | None = None
    ) -> None:
        self.plugin.dashboard_service.emit_dashboard_event(event_type, data)


class SupportService:
    """工具、权限、指令路由和主动分享的组合式服务边界。"""

    def __init__(self, plugin) -> None:
        self.operations = SupportRuntime(plugin)

    @property
    def config(self):
        return self.operations.config

    @property
    def db(self):
        return self.operations.db

    @property
    def ctx_service(self):
        return self.operations.ctx_service

    @property
    def task_manager(self):
        return self.operations.task_manager

    @property
    def basic_conf(self):
        return self.operations.basic_conf

    @property
    def extra_shares_conf(self):
        return self.operations.extra_shares_conf

    @extra_shares_conf.setter
    def extra_shares_conf(self, value) -> None:
        self.operations.extra_shares_conf = value

    @property
    def qzone_conf(self):
        return self.operations.qzone_conf

    @property
    def receiver_conf(self):
        return self.operations.receiver_conf

    @receiver_conf.setter
    def receiver_conf(self, value) -> None:
        self.operations.receiver_conf = value

    async def run_daily_share_tool(self, *args, **kwargs):
        return await self.operations.tools.run_daily_share_tool(*args, **kwargs)

    async def inject_tool_context(self, *args, **kwargs) -> None:
        await self.operations.tools.inject_tool_context(*args, **kwargs)

    async def query_news_link(self, *args, **kwargs):
        return await self.operations.tools.query_news_link(*args, **kwargs)

    async def run_qzone_tool(self, *args, **kwargs):
        return await self.operations.tools.run_qzone_tool(*args, **kwargs)

    async def run_qzone_auto_interaction_tool(self, *args, **kwargs):
        return await self.operations.tools.run_qzone_auto_interaction_tool(
            *args, **kwargs
        )

    async def clean_news_link_llm_references(self, *args, **kwargs) -> None:
        await self.operations.tools.clean_news_link_llm_references(*args, **kwargs)

    async def clean_news_link_decorating_references(self, *args, **kwargs) -> None:
        await self.operations.tools.clean_news_link_decorating_references(
            *args, **kwargs
        )

    async def handle_share_command(self, *args, **kwargs):
        async for result in self.operations.main_route.handle_share_command(
            *args, **kwargs
        ):
            yield result

    async def publish_qzone(self, *args, **kwargs):
        return await self.operations.qzone.publish_qzone(*args, **kwargs)

    def target_entry_matches(self, *args, **kwargs) -> bool:
        return self.operations.permissions.target_entry_matches(*args, **kwargs)

    def get_contact_alias(self, *args, **kwargs) -> str:
        return self.operations.aliases.get_contact_alias(*args, **kwargs)

    def set_contact_alias(self, *args, **kwargs) -> str:
        return self.operations.aliases.set_contact_alias(*args, **kwargs)

    def remove_contact_alias(self, *args, **kwargs) -> list:
        return self.operations.aliases.remove_contact_alias(*args, **kwargs)

    async def save_config_file(self) -> None:
        await self.operations.save_config_file()

    async def save_config_and_refresh_runtime(self, *args, **kwargs):
        return await self.operations.save_config_and_refresh_runtime(*args, **kwargs)

    def extract_news_link_urls(self, text: str) -> list[str]:
        return self.operations.tool_context._extract_news_link_urls(text)

    def ensure_news_link_urls_in_reply(self, reply: str, urls: list[str]) -> str:
        return self.operations.tool_context._ensure_news_link_urls_in_reply(reply, urls)


__all__ = ["SupportService"]

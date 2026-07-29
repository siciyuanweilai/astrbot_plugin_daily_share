from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..container import PluginServices

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from ...main import DailySharePlugin
    from ..content import ContentService
    from ..context import ContextService
    from ..db import DatabaseManager
    from ..image import ImageService
    from ..news import NewsService


@dataclass(frozen=True, slots=True)
class TaskRuntime:
    """供各项任务能力共享的显式依赖边界。"""

    plugin: DailySharePlugin
    scheduler: AsyncIOScheduler
    db: DatabaseManager
    ctx_service: ContextService
    news_service: NewsService
    image_service: ImageService
    content_service: ContentService
    lock: asyncio.Lock
    basic_conf: dict
    extra_shares_conf: dict
    qzone_conf: dict
    image_conf: dict
    tts_conf: dict
    context_conf: dict
    receiver_conf: dict

    @classmethod
    def from_services(
        cls, plugin: DailySharePlugin, services: PluginServices
    ) -> "TaskRuntime":
        return cls(
            plugin=plugin,
            scheduler=services.scheduler,
            db=services.db,
            ctx_service=services.ctx_service,
            news_service=services.news_service,
            image_service=services.image_service,
            content_service=services.content_service,
            lock=services.lock,
            basic_conf=services.basic_conf,
            extra_shares_conf=services.extra_shares_conf,
            qzone_conf=services.qzone_conf,
            image_conf=services.image_conf,
            tts_conf=services.tts_conf,
            context_conf=services.context_conf,
            receiver_conf=services.receiver_conf,
        )

    @classmethod
    def from_plugin(cls, plugin: DailySharePlugin) -> "TaskRuntime":
        services = plugin.services
        if not isinstance(services, PluginServices):
            raise TypeError("每日分享插件必须提供 PluginServices 服务容器")
        return cls.from_services(plugin, services)

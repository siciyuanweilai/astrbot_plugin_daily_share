from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from .content import ContentService
    from .context import ContextService
    from .db import DatabaseManager
    from .image import ImageService
    from .news import NewsService
    from .space import QzoneService


@dataclass(frozen=True, slots=True)
class PluginServices:
    """插件运行期共享的显式服务容器。"""

    scheduler: AsyncIOScheduler
    db: DatabaseManager
    ctx_service: ContextService
    news_service: NewsService
    image_service: ImageService
    content_service: ContentService
    qzone_service: QzoneService
    lock: asyncio.Lock
    target_locks: dict[str, asyncio.Lock]
    basic_conf: dict
    extra_shares_conf: dict
    qzone_conf: dict
    image_conf: dict
    tts_conf: dict
    context_conf: dict
    receiver_conf: dict
    daily_life_bridge: Any = None


__all__ = ["PluginServices"]

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from .runtime import TaskRuntime

if TYPE_CHECKING:
    from .components import TaskServices


@dataclass(slots=True)
class TaskConfigState:
    """所有任务服务共享的可替换配置引用。"""

    basic: dict
    extra_shares: dict
    qzone: dict
    image: dict
    tts: dict
    context: dict
    receiver: dict

    @classmethod
    def from_runtime(cls, runtime: TaskRuntime) -> TaskConfigState:
        return cls(
            basic=runtime.basic_conf,
            extra_shares=runtime.extra_shares_conf,
            qzone=runtime.qzone_conf,
            image=runtime.image_conf,
            tts=runtime.tts_conf,
            context=runtime.context_conf,
            receiver=runtime.receiver_conf,
        )


@dataclass(slots=True)
class TaskSharedState:
    """跨服务共享且有明确所有权的运行状态。"""

    qzone_auto_interaction_lock: asyncio.Lock
    briefing_share_lock: asyncio.Lock
    last_share_time: datetime | None = None
    share_progress_seq: int = 0
    share_progress: dict | None = None
    news_image_cleanup_after_download_task: asyncio.Task | None = None


class TaskServiceBase:
    """任务服务的显式依赖基类，不代理属性和方法。"""

    def __init__(
        self,
        runtime: TaskRuntime,
        config: TaskConfigState,
        state: TaskSharedState,
    ) -> None:
        self.runtime = runtime
        self.config = config
        self.state = state
        self.services: TaskServices

    def connect(self, services: TaskServices) -> None:
        self.services = services

    async def send_event(self, event, chain) -> None:
        from ..eventdelivery import send_event_message

        await send_event_message(event, chain)

    @property
    def plugin(self):
        return self.runtime.plugin

    @property
    def scheduler(self):
        return self.runtime.scheduler

    @property
    def db(self):
        return self.runtime.db

    @property
    def ctx_service(self):
        return self.runtime.ctx_service

    @property
    def news_service(self):
        return self.runtime.news_service

    @property
    def image_service(self):
        return self.runtime.image_service

    @property
    def content_service(self):
        return self.runtime.content_service

    @property
    def _lock(self):
        return self.runtime.lock

    @property
    def _qzone_auto_interaction_lock(self):
        return self.state.qzone_auto_interaction_lock

    @property
    def _briefing_share_lock(self):
        return self.state.briefing_share_lock

    @property
    def basic_conf(self) -> dict:
        return self.config.basic

    @property
    def extra_shares_conf(self) -> dict:
        return self.config.extra_shares

    @property
    def qzone_conf(self) -> dict:
        return self.config.qzone

    @property
    def image_conf(self) -> dict:
        return self.config.image

    @property
    def tts_conf(self) -> dict:
        return self.config.tts

    @property
    def context_conf(self) -> dict:
        return self.config.context

    @property
    def receiver_conf(self) -> dict:
        return self.config.receiver


__all__ = ["TaskConfigState", "TaskServiceBase", "TaskSharedState"]

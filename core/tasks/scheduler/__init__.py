from __future__ import annotations

import asyncio

from ..taskbase import TaskServiceBase
from .auto import TaskSchedulerAutoService
from .cron import TaskSchedulerCronService
from .delay import TaskSchedulerDelayService
from .random import TaskSchedulerRandomService
from .recovery import TaskSchedulerRecoveryService
from .setup import TaskSchedulerSetupService
from .smart import TaskSchedulerSmartService
from .triggers import TaskSchedulerTriggerService


class TaskSchedulerService(TaskServiceBase):
    """定时注册、随机延迟、恢复与智能调度的组合服务。"""

    def __init__(self, runtime, config, state) -> None:
        super().__init__(runtime, config, state)
        self._build_generation = 0
        self._build_tasks: set[asyncio.Task] = set()
        self.triggers = TaskSchedulerTriggerService(self)
        self.smart = TaskSchedulerSmartService(self)
        self.random = TaskSchedulerRandomService(self)
        self.recovery = TaskSchedulerRecoveryService(self)
        self.cron = TaskSchedulerCronService(self)
        self.delay = TaskSchedulerDelayService(self)
        self.auto = TaskSchedulerAutoService(self)
        self.setup = TaskSchedulerSetupService(self)

    def invalidate_builds(self) -> int:
        """作废并取消仍在运行的旧调度构建任务。"""
        self._build_generation += 1
        for task in tuple(self._build_tasks):
            if task and not task.done():
                task.cancel()
        self._build_tasks.clear()
        return self._build_generation

    def is_current_build(self, generation: int | None) -> bool:
        return bool(
            generation == self._build_generation and not self.plugin._is_terminated
        )

    def track_build(self, coro, generation: int):
        if not self.is_current_build(generation):
            coro.close()
            return None
        task = self.plugin.track_task(coro)
        if task is None:
            return None
        self._build_tasks.add(task)
        task.add_done_callback(self._build_tasks.discard)
        return task

    def setup_tasks(self) -> None:
        generation = self.invalidate_builds()
        self.setup.setup_tasks(generation=generation)

    async def clear_pending_delay_jobs(self) -> None:
        await self.recovery.clear_pending_delay_jobs()

    def parse_cron_to_kwargs(self, cron_expr: str):
        return self.cron.parse_cron_to_kwargs(cron_expr)

    def clock_time_to_cron(self, value: str):
        return self.cron.clock_time_to_cron(value)

    def setup_cron_job_custom(self, *args, **kwargs):
        return self.cron.setup_cron_job_custom(*args, **kwargs)

    def setup_cleanup_tasks(self):
        return self.setup.setup_cleanup_tasks()

    def setup_custom_target_crons(self):
        return self.setup.setup_custom_target_crons()

    def setup_qzone_auto_interaction_cron(self):
        return self.auto.setup_qzone_auto_interaction_cron()


__all__ = ["TaskSchedulerService"]

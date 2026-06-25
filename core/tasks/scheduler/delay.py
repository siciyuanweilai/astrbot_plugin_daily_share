from __future__ import annotations

import asyncio
import random as random_module
from datetime import datetime, timedelta

from astrbot.api import logger


class TaskSchedulerDelayMixin:
    def _read_delay_minutes(self, conf: dict, key: str) -> int:
        try:
            return max(0, int(conf.get(key, 0)))
        except Exception:
            return 0

    async def _schedule_or_execute_delayed(
        self,
        *,
        state_key: str,
        delay_minutes: int,
        delayed_func,
        delayed_job_id: str,
        log_label: str,
    ):
        if delay_minutes > 0:
            delay_seconds = random_module.randint(0, delay_minutes * 60)
            if delay_seconds > 0:
                target_time = datetime.now() + timedelta(seconds=delay_seconds)
                time_str = target_time.strftime("%H:%M:%S")
                await self.db.update_state_dict(
                    state_key,
                    {"pending_delay_job": {"target_time": target_time.timestamp()}},
                )
                self.scheduler.add_job(
                    delayed_func,
                    "date",
                    run_date=target_time,
                    id=delayed_job_id,
                    replace_existing=True,
                )
                logger.debug(
                    f"[每日分享] {log_label}已触发，将随机延迟 "
                    f"{delay_seconds / 60:.1f} 分钟，预计于 {time_str} 分享..."
                )
                return

        await delayed_func()

    async def _run_tracked_pending_job(
        self,
        state_key: str,
        action,
        *,
        lock=None,
        locked_warning: str = "",
        before_action=None,
        background: bool = False,
    ):
        if self.plugin._is_terminated:
            return

        async def run_job(track_current_task: bool = True):
            task = asyncio.current_task()
            if track_current_task and task is not None:
                self.plugin._bg_tasks.add(task)
            try:
                await self.db.update_state_dict(state_key, {"pending_delay_job": None})

                if lock:
                    if lock.locked() and locked_warning:
                        logger.warning(locked_warning)
                    async with lock:
                        if before_action and not await before_action():
                            return
                        await action()
                    return

                if before_action and not await before_action():
                    return
                await action()
            finally:
                if track_current_task and task is not None:
                    self.plugin._bg_tasks.discard(task)

        if background:
            track_task = getattr(self.plugin, "_track_task", None)
            if callable(track_task):
                return track_task(run_job(track_current_task=False))
            return asyncio.create_task(run_job())

        await run_job()

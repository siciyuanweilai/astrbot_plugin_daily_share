from __future__ import annotations

import asyncio
import random as random_module
from datetime import datetime, timedelta

from astrbot.api import logger

from .schedulerbase import SchedulerComponent


class TaskSchedulerDelayService(SchedulerComponent):
    def _read_delay_minutes(self, conf: dict, key: str) -> int:
        try:
            return max(0, int(conf.get(key, 0)))
        except Exception:
            return 0

    def _scheduled_delay_job(self, job_id: str):
        return self.scheduler.get_job(job_id)

    @staticmethod
    def _delay_job_run_time(job):
        return job.next_run_time

    def _has_pending_delay_job(self, job_id: str, *, now: datetime) -> bool:
        job = self._scheduled_delay_job(job_id)
        if job is None:
            return False
        run_time = self._delay_job_run_time(job)
        if run_time is None:
            return True
        try:
            compare_now = datetime.now(run_time.tzinfo) if run_time.tzinfo else now
            return run_time > compare_now
        except Exception:
            return True

    async def _schedule_or_execute_delayed(
        self,
        *,
        state_key: str,
        delay_minutes: int,
        delayed_func,
        delayed_job_id: str,
        log_label: str,
        state_updater=None,
    ):
        update_state = state_updater or self.db.update_share_state
        if delay_minutes > 0:
            now = datetime.now()
            if self._has_pending_delay_job(delayed_job_id, now=now):
                logger.debug(f"[日常分享] {log_label}已有延迟任务，跳过本次触发。")
                return
            delay_seconds = random_module.randint(0, delay_minutes * 60)
            if delay_seconds > 0:
                target_time = now + timedelta(seconds=delay_seconds)
                time_str = target_time.strftime("%H:%M:%S")
                await update_state(
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
                    f"[日常分享] {log_label}已触发，将随机延迟 "
                    f"{delay_seconds / 60:.1f} 分钟，预计于 {time_str} 执行..."
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
        state_updater=None,
    ):
        if self.plugin._is_terminated:
            return
        update_state = state_updater or self.db.update_share_state

        if lock and lock.locked():
            await update_state(state_key, {"pending_delay_job": None})
            if locked_warning:
                logger.warning(locked_warning)
            return None

        async def run_job(track_current_task: bool = True):
            task = asyncio.current_task()
            if track_current_task and task is not None:
                self.plugin._bg_tasks.add(task)
            try:
                await update_state(state_key, {"pending_delay_job": None})

                if lock:
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

        return self.plugin.track_task(run_job(track_current_task=False))

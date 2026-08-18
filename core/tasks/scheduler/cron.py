from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from apscheduler.triggers.cron import CronTrigger

from astrbot.api import logger

from ...config import CRON_TEMPLATES
from ...schedule import ScheduleDefinition, normalize_schedule_mode
from .schedulerbase import SchedulerComponent


@dataclass(frozen=True)
class ScheduleJobDefinition:
    config: dict
    schedule: ScheduleDefinition
    base_job_id: str
    label: str
    execute: Callable[..., Any]
    random_scheduler_job_id: str
    random_scheduler: Callable[..., Any]
    schedule_random: Callable[..., Any]
    smart_scheduler_job_id: str = ""
    smart_scheduler: Callable[..., Any] | None = None
    schedule_smart: Callable[..., Any] | None = None


class TaskSchedulerCronService(SchedulerComponent):
    def parse_cron_to_kwargs(self, cron_str: str) -> dict | None:
        """解析标准 5 位定时表达式：分、时、日、月、周。"""
        text = str(cron_str or "").strip()
        parts = text.split()
        if len(parts) != 5:
            return None
        try:
            CronTrigger.from_crontab(text)
        except (TypeError, ValueError):
            return None
        return {
            "minute": parts[0],
            "hour": parts[1],
            "day": parts[2],
            "month": parts[3],
            "day_of_week": parts[4],
        }

    @staticmethod
    def clock_time_to_cron(time_value: str) -> str | None:
        raw = str(time_value or "").strip()
        if ":" not in raw:
            return None
        hour_text, minute_text = raw.split(":", 1)
        try:
            hour = int(hour_text)
            minute = int(minute_text)
        except Exception:
            return None
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        return f"{minute} {hour} * * *"

    def _setup_fixed_time_jobs(
        self, base_job_id: str, fixed_times: list, func, label: str
    ) -> None:
        valid_count = 0
        for index, time_value in enumerate(fixed_times):
            cron = self.clock_time_to_cron(time_value)
            if not cron:
                logger.error(f"[日常分享] {label}固定时间无效: {time_value}")
                continue
            job_id = (
                base_job_id if len(fixed_times) == 1 else f"{base_job_id}_fixed_{index}"
            )
            self.setup_cron_job_custom(job_id, cron, func)
            valid_count += 1
        if valid_count:
            logger.debug(
                f"[日常分享] {label}固定时间任务已启动: {', '.join(map(str, fixed_times))}"
            )

    def _setup_schedule_job(
        self, job: ScheduleJobDefinition, *, generation: int | None = None
    ) -> None:
        conf = job.config
        definition = job.schedule
        mode = normalize_schedule_mode(
            conf.get(definition.mode_key, definition.mode_default),
            definition.mode_default,
        )
        if mode == "fixed_time":
            fixed_times = list(
                conf.get(definition.fixed_key) or definition.fixed_default
            )
            self._setup_fixed_time_jobs(
                job.base_job_id, fixed_times, job.execute, job.label
            )
            return
        if mode == "random_period":
            self.setup_cron_job_custom(
                job.random_scheduler_job_id,
                "0 0 * * *",
                job.random_scheduler,
            )
            active_generation = (
                self.schedule._build_generation if generation is None else generation
            )
            self.schedule.track_build(
                job.schedule_random(generation=active_generation),
                active_generation,
            )
            logger.debug(f"[日常分享] {job.label}已启用随机时段模式")
            return
        if mode == "llm_smart":
            if not (
                job.smart_scheduler_job_id
                and job.smart_scheduler
                and job.schedule_smart
            ):
                logger.error(f"[日常分享] {job.label}缺少智能定时入口，已跳过")
                return
            self.setup_cron_job_custom(
                job.smart_scheduler_job_id,
                "5 0 * * *",
                job.smart_scheduler,
            )
            active_generation = (
                self.schedule._build_generation if generation is None else generation
            )
            self.schedule.track_build(
                job.schedule_smart(generation=active_generation),
                active_generation,
            )
            logger.debug(f"[日常分享] {job.label}已启用智能定时模式")
            return
        if mode == "cron":
            cron = conf.get(definition.cron_key, definition.cron_default)
            self.setup_cron_job_custom(job.base_job_id, cron, job.execute)
            logger.debug(
                f"[日常分享] {job.label}高级定时表达式任务已启动 ({CRON_TEMPLATES.get(cron, cron)})"
            )
            return
        logger.error(f"[日常分享] {job.label}触发模式无效: {mode}")

    def setup_cron_job_custom(self, job_id: str, cron_str: str, func):
        """通用定时表达式设置方法。"""
        if self.plugin._is_terminated:
            return
        actual_cron = CRON_TEMPLATES.get(cron_str, cron_str)
        cron_kwargs = self.parse_cron_to_kwargs(actual_cron)
        if not cron_kwargs:
            raise ValueError(
                f"任务[{job_id}]的定时表达式无效，需使用标准 5 位格式: {cron_str}"
            )

        try:
            self.scheduler.add_job(
                func,
                "cron",
                **cron_kwargs,
                id=job_id,
                replace_existing=True,
                max_instances=1,
            )
        except Exception as e:
            logger.error(f"[日常分享] 任务[{job_id}]设置失败: {e}")
            raise
        logger.debug(f"[日常分享] 任务[{job_id}]已设定: {actual_cron}")

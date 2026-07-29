from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from typing import Optional

from astrbot.api import logger

from ...config import CRON_TEMPLATES
from ...schedule import ScheduleDefinition
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
    def parse_cron_to_kwargs(self, cron_str: str) -> Optional[dict]:
        """解析标准 5 位定时表达式：分、时、日、月、周。"""
        parts = cron_str.strip().split()
        if len(parts) != 5:
            return None
        return {
            "minute": parts[0],
            "hour": parts[1],
            "day": parts[2],
            "month": parts[3],
            "day_of_week": parts[4],
        }

    @staticmethod
    def clock_time_to_cron(time_value: str) -> Optional[str]:
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
        mode = str(
            conf.get(definition.mode_key, definition.mode_default)
            or definition.mode_default
        ).strip()
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
        try:
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)

            actual_cron = CRON_TEMPLATES.get(cron_str, cron_str)
            cron_kwargs = self.parse_cron_to_kwargs(actual_cron)

            if cron_kwargs:
                self.scheduler.add_job(
                    func,
                    "cron",
                    **cron_kwargs,
                    id=job_id,
                    replace_existing=True,
                    max_instances=1,
                )
                logger.debug(f"[日常分享] 任务[{job_id}]已设定: {actual_cron}")
            else:
                logger.error(
                    f"[日常分享] 任务[{job_id}]无效的定时表达式（仅支持标准 5 位）: {cron_str}"
                )
        except Exception as e:
            logger.error(f"[日常分享] 任务[{job_id}]设置失败: {e}")

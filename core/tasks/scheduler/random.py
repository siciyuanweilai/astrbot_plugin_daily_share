import random
from datetime import datetime, timedelta

from astrbot.api import logger

from ...database.keys import BRIEFING_STATE_KEY, GLOBAL_STATE_KEY, QZONE_STATE_KEY
from .schedulerbase import SchedulerComponent


class TaskSchedulerRandomService(SchedulerComponent):
    """随机时段定时辅助方法。"""

    def _parse_random_period(
        self, base_dt: datetime, period_str: str
    ) -> tuple[datetime, datetime]:
        start_str, end_str = period_str.split("-", 1)
        start_h, start_m = map(int, start_str.split(":"))
        end_h, end_m = map(int, end_str.split(":"))

        start_dt = base_dt.replace(
            hour=start_h, minute=start_m, second=0, microsecond=0
        )
        end_dt = base_dt.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
        return start_dt, end_dt

    def _get_random_run_time(self, base_dt: datetime, period_str: str) -> datetime:
        start_dt, end_dt = self._parse_random_period(base_dt, period_str)
        total_seconds = int((end_dt - start_dt).total_seconds())
        if total_seconds <= 0:
            raise ValueError("结束时间必须晚于开始时间，随机时段不支持跨天")

        return start_dt + timedelta(seconds=random.randrange(total_seconds))

    async def _schedule_daily_random_schedule_jobs(
        self,
        *,
        state_key: str,
        periods: list,
        job_prefix: str,
        func,
        label: str,
        generation: int | None = None,
    ):
        generation = (
            self.schedule._build_generation if generation is None else generation
        )
        if not self.schedule.is_current_build(generation):
            return

        for job in list(self.scheduler.get_jobs()):
            if str(job.id).startswith(job_prefix):
                self.scheduler.remove_job(job.id)

        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        state = await self.db.get_share_state(state_key, {})
        random_schedule = state.get("random_schedule", {})
        normalized_periods = [
            str(period).strip() for period in periods if str(period).strip()
        ]
        random_schedule, is_modified = self._updated_random_schedule(
            random_schedule, date_str, normalized_periods, now
        )
        jobs = random_schedule["jobs"]

        if is_modified and self.schedule.is_current_build(generation):
            random_schedule["jobs"] = jobs
            await self.db.update_share_state(
                state_key, {"random_schedule": random_schedule}
            )

        if self.schedule.is_current_build(generation):
            self._register_random_jobs(jobs, now, job_prefix, func, label)

    def _updated_random_schedule(
        self, schedule: dict, date_str: str, periods: list[str], now: datetime
    ) -> tuple[dict, bool]:
        modified = schedule.get("date") != date_str
        schedule = {"date": date_str, "jobs": {}} if modified else schedule
        jobs = schedule.get("jobs", {})
        stale_periods = [period for period in jobs if period not in periods]
        for period in stale_periods:
            del jobs[period]
        modified = modified or bool(stale_periods)
        for period in periods:
            if period in jobs:
                continue
            try:
                run_time = self._get_random_run_time(now, period)
            except Exception as exc:
                logger.error(f"[日常分享] 解析随机时段失败 {period}: {exc}")
                continue
            if run_time is not None:
                jobs[period] = run_time.timestamp()
                modified = True
        schedule["jobs"] = jobs
        return schedule, modified

    def _register_random_jobs(
        self, jobs: dict, now: datetime, job_prefix: str, func, label: str
    ) -> None:
        for index, (period_str, timestamp) in enumerate(jobs.items()):
            run_time = datetime.fromtimestamp(timestamp)
            if run_time <= now:
                continue
            job_id = f"{job_prefix}{index}"
            self.scheduler.add_job(
                func,
                "date",
                run_date=run_time,
                id=job_id,
                replace_existing=True,
            )
            logger.debug(
                f"[日常分享] {label}随机任务 [{period_str}] 已设定: "
                f"{run_time.strftime('%H:%M:%S')}"
            )

    async def _schedule_daily_random_jobs(self, *, generation: int | None = None):
        await self._schedule_daily_random_schedule_jobs(
            state_key=GLOBAL_STATE_KEY,
            periods=self.basic_conf.get(
                "random_periods", ["08:00-10:00", "19:00-21:00"]
            ),
            job_prefix="random_share_",
            func=self.schedule.triggers._task_wrapper,
            label="全局分享",
            generation=generation,
        )

    async def _schedule_daily_briefing_random_jobs(
        self, *, generation: int | None = None
    ):
        await self._schedule_daily_random_schedule_jobs(
            state_key=BRIEFING_STATE_KEY,
            periods=self.extra_shares_conf.get(
                "briefing_random_periods", ["08:00-09:00"]
            ),
            job_prefix="briefing_random_share_",
            func=self.schedule.triggers._task_wrapper_briefing,
            label="早报",
            generation=generation,
        )

    async def _schedule_daily_qzone_random_jobs(self, *, generation: int | None = None):
        await self._schedule_daily_random_schedule_jobs(
            state_key=QZONE_STATE_KEY,
            periods=self.qzone_conf.get("qzone_random_periods", ["19:00-21:00"]),
            job_prefix="qzone_random_share_",
            func=self.schedule.triggers._task_wrapper_qzone,
            label="QQ 空间",
            generation=generation,
        )

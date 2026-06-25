import random
from datetime import datetime, timedelta
from typing import Optional

from astrbot.api import logger

from ...database.keys import BRIEFING_STATE_KEY, GLOBAL_STATE_KEY, QZONE_STATE_KEY


class TaskSchedulerRandomMixin:
    """随机时段定时辅助方法。"""

    def _parse_random_period(self, base_dt: datetime, period_str: str) -> tuple[datetime, datetime]:
        start_str, end_str = period_str.split("-", 1)
        start_h, start_m = map(int, start_str.split(":"))
        end_h, end_m = map(int, end_str.split(":"))

        start_dt = base_dt.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        end_dt = base_dt.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
        return start_dt, end_dt

    def _get_random_run_time(self, base_dt: datetime, period_str: str) -> Optional[datetime]:
        start_dt, end_dt = self._parse_random_period(base_dt, period_str)
        total_seconds = int((end_dt - start_dt).total_seconds())
        if total_seconds <= 0:
            return None

        return start_dt + timedelta(seconds=random.randrange(total_seconds))

    async def _schedule_daily_random_schedule_jobs(
        self,
        *,
        state_key: str,
        periods: list,
        job_prefix: str,
        func,
        label: str,
    ):
        if self.plugin._is_terminated:
            return

        for job in list(self.scheduler.get_jobs()):
            if str(job.id).startswith(job_prefix):
                self.scheduler.remove_job(job.id)

        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        state = await self.db.get_state(state_key, {})
        random_schedule = state.get("random_schedule", {})

        is_modified = False
        if random_schedule.get("date") != date_str:
            random_schedule = {"date": date_str, "jobs": {}}
            is_modified = True

        jobs = random_schedule.get("jobs", {})
        normalized_periods = [str(period).strip() for period in periods if str(period).strip()]

        for period in [period for period in list(jobs.keys()) if period not in normalized_periods]:
            del jobs[period]
            is_modified = True

        for period_str in normalized_periods:
            if period_str in jobs:
                continue
            try:
                run_time = self._get_random_run_time(now, period_str)
                if run_time is None:
                    continue
                jobs[period_str] = run_time.timestamp()
                is_modified = True
            except Exception as exc:
                logger.error(f"[每日分享] 解析随机时段失败 {period_str}: {exc}")

        if is_modified:
            random_schedule["jobs"] = jobs
            await self.db.update_state_dict(state_key, {"random_schedule": random_schedule})

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
                f"[每日分享] {label}随机任务 [{period_str}] 已设定: "
                f"{run_time.strftime('%H:%M:%S')}"
            )

    async def _schedule_daily_random_jobs(self):
        await self._schedule_daily_random_schedule_jobs(
            state_key=GLOBAL_STATE_KEY,
            periods=self.basic_conf.get("random_periods", ["08:00-10:00", "19:00-21:00"]),
            job_prefix="random_share_",
            func=self._task_wrapper,
            label="全局分享",
        )

    async def _schedule_daily_briefing_random_jobs(self):
        await self._schedule_daily_random_schedule_jobs(
            state_key=BRIEFING_STATE_KEY,
            periods=self.extra_shares_conf.get("briefing_random_periods", ["08:00-09:00"]),
            job_prefix="briefing_random_share_",
            func=self._task_wrapper_briefing,
            label="早报",
        )

    async def _schedule_daily_qzone_random_jobs(self):
        await self._schedule_daily_random_schedule_jobs(
            state_key=QZONE_STATE_KEY,
            periods=self.qzone_conf.get("qzone_random_periods", ["19:00-21:00"]),
            job_prefix="qzone_random_share_",
            func=self._task_wrapper_qzone,
            label="QQ 空间",
        )

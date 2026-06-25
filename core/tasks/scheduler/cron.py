from __future__ import annotations

from typing import Optional

from astrbot.api import logger

from ...config import CRON_TEMPLATES


class TaskSchedulerCronMixin:
    def _parse_cron_to_kwargs(self, cron_str: str) -> Optional[dict]:
        """
        兼容解析 5/6/7 位的定时表达式。
        5位: 分 时 日 月 周
        6位: 秒 分 时 日 月 周
        7位: 秒 分 时 日 月 周 年
        """
        parts = cron_str.strip().split()
        if len(parts) == 5:
            return {
                "minute": parts[0],
                "hour": parts[1],
                "day": parts[2],
                "month": parts[3],
                "day_of_week": parts[4],
            }
        if len(parts) == 6:
            return {
                "second": parts[0],
                "minute": parts[1],
                "hour": parts[2],
                "day": parts[3],
                "month": parts[4],
                "day_of_week": parts[5],
            }
        if len(parts) == 7:
            return {
                "second": parts[0],
                "minute": parts[1],
                "hour": parts[2],
                "day": parts[3],
                "month": parts[4],
                "day_of_week": parts[5],
                "year": parts[6],
            }
        return None

    @staticmethod
    def _clock_time_to_cron(time_value: str) -> Optional[str]:
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

    def _setup_fixed_time_jobs(self, base_job_id: str, fixed_times: list, func, label: str) -> None:
        valid_count = 0
        for index, time_value in enumerate(fixed_times):
            cron = self._clock_time_to_cron(time_value)
            if not cron:
                logger.error(f"[每日分享] {label}固定时间无效: {time_value}")
                continue
            job_id = base_job_id if len(fixed_times) == 1 else f"{base_job_id}_fixed_{index}"
            self._setup_cron_job_custom(job_id, cron, func)
            valid_count += 1
        if valid_count:
            logger.debug(f"[每日分享] {label}固定时间任务已启动: {', '.join(map(str, fixed_times))}")

    def _setup_schedule_job(
        self,
        conf: dict,
        *,
        mode_key: str,
        mode_default: str,
        fixed_key: str,
        fixed_default: list,
        cron_key: str,
        cron_default: str,
        base_job_id: str,
        label: str,
        func,
        random_scheduler_job_id: str,
        random_scheduler_func,
        schedule_random_func,
        smart_scheduler_job_id: str = "",
        smart_scheduler_func=None,
        schedule_smart_func=None,
    ) -> None:
        mode = str(conf.get(mode_key, mode_default) or mode_default).strip()
        if mode == "fixed_time":
            fixed_times = list(conf.get(fixed_key) or fixed_default)
            self._setup_fixed_time_jobs(base_job_id, fixed_times, func, label)
            return
        if mode == "random_period":
            self._setup_cron_job_custom(random_scheduler_job_id, "0 0 * * *", random_scheduler_func)
            self.plugin._track_task(schedule_random_func())
            logger.debug(f"[每日分享] {label}已启用随机时段模式")
            return
        if mode == "llm_smart":
            if not (smart_scheduler_job_id and smart_scheduler_func and schedule_smart_func):
                logger.error(f"[每日分享] {label}缺少智能定时入口，已跳过")
                return
            self._setup_cron_job_custom(smart_scheduler_job_id, "5 0 * * *", smart_scheduler_func)
            self.plugin._track_task(schedule_smart_func())
            logger.debug(f"[每日分享] {label}已启用智能定时模式")
            return
        if mode == "cron":
            cron = conf.get(cron_key, cron_default)
            self._setup_cron_job_custom(base_job_id, cron, func)
            logger.debug(f"[每日分享] {label}高级定时表达式任务已启动 ({CRON_TEMPLATES.get(cron, cron)})")
            return
        logger.error(f"[每日分享] {label}触发模式无效: {mode}")

    def _setup_cron_job_custom(self, job_id: str, cron_str: str, func):
        """通用定时表达式设置方法。"""
        if self.plugin._is_terminated:
            return
        try:
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)

            actual_cron = CRON_TEMPLATES.get(cron_str, cron_str)
            cron_kwargs = self._parse_cron_to_kwargs(actual_cron)

            if cron_kwargs:
                self.scheduler.add_job(
                    func,
                    "cron",
                    **cron_kwargs,
                    id=job_id,
                    replace_existing=True,
                    max_instances=1,
                )
                logger.debug(f"[每日分享] 任务[{job_id}]已设定: {actual_cron}")
            else:
                logger.error(f"[每日分享] 任务[{job_id}]无效的定时表达式（支持 5/6/7 位）: {cron_str}")
        except Exception as e:
            logger.error(f"[每日分享] 任务[{job_id}]设置失败: {e}")

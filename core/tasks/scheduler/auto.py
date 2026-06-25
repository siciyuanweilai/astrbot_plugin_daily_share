from __future__ import annotations

from astrbot.api import logger

from ...config import CRON_TEMPLATES
from ..qinteract import (
    QZONE_AUTO_INTERACTION_DEFAULT_CRON,
    QZONE_AUTO_INTERACTION_DEFAULT_INTERVAL_MINUTES,
)


class TaskSchedulerAutoMixin:
    def setup_qzone_auto_interaction_cron(self):
        """设置 QQ 空间自动互动触发器。"""
        self._setup_qzone_auto_schedule_job(
            enabled_key=None,
            interval_key="qzone_auto_interaction_interval_minutes",
            interval_default=self._qzone_auto_interaction_interval_default(),
            cron_key="qzone_auto_interaction_cron",
            cron_default=self._qzone_auto_interaction_cron_default(),
            job_id="qzone_auto_interaction",
            func=self._task_wrapper_qzone_auto_interaction,
            label="QQ 空间自动互动",
        )

    def _qzone_auto_interaction_interval_default(self) -> int:
        return QZONE_AUTO_INTERACTION_DEFAULT_INTERVAL_MINUTES

    def _qzone_auto_interaction_cron_default(self) -> str:
        return QZONE_AUTO_INTERACTION_DEFAULT_CRON

    @staticmethod
    def _coerce_qzone_auto_interval(value, default: int) -> int:
        try:
            return max(0, min(1440, int(value)))
        except Exception:
            return default

    def _setup_qzone_auto_schedule_job(
        self,
        *,
        enabled_key: str | None,
        interval_key: str,
        interval_default: int,
        cron_key: str,
        cron_default: str,
        job_id: str,
        func,
        label: str,
    ):
        if enabled_key and not self.qzone_conf.get(enabled_key, False):
            return
        if not enabled_key and not self._qzone_auto_interaction_enabled():
            return

        interval_minutes = self._coerce_qzone_auto_interval(
            self.qzone_conf.get(interval_key, interval_default),
            interval_default,
        )
        if interval_minutes > 0:
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            self.scheduler.add_job(
                func,
                "interval",
                minutes=interval_minutes,
                id=job_id,
                replace_existing=True,
                max_instances=1,
            )
            logger.debug(f"[每日分享] {label}任务已启动，每 {interval_minutes} 分钟查询一次")
            return

        cron = self.qzone_conf.get(cron_key, cron_default)
        actual_cron = CRON_TEMPLATES.get(cron, cron)
        self._setup_cron_job_custom(job_id, actual_cron, func)
        logger.debug(f"[每日分享] {label}任务已启动 ({actual_cron})")

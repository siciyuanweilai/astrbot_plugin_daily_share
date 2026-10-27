from __future__ import annotations

from ..qinteract import QZONE_AUTO_INTERACTION_DEFAULT_CRON
from ..interact.intent import living_interaction
from .schedulerbase import SchedulerComponent


class TaskSchedulerAutoService(SchedulerComponent):
    def setup_qzone_auto_interaction_cron(self):
        """生活模式只观察新内容；其他模式使用显式配置的定时。"""
        if not self.services.qzone_interaction.qzone_auto_interaction_enabled():
            return
        if living_interaction(self):
            self.scheduler.add_job(
                self.schedule.triggers._task_wrapper_qzone_auto_interaction,
                "interval",
                seconds=120,
                id="life_qzone_observer",
                replace_existing=True,
                max_instances=1,
            )
            return
        self.schedule.cron.setup_cron_job_custom(
            "qzone_auto_interaction",
            self.qzone_conf.get(
                "qzone_auto_interaction_cron", QZONE_AUTO_INTERACTION_DEFAULT_CRON
            ),
            self.schedule.triggers._task_wrapper_qzone_auto_interaction,
        )

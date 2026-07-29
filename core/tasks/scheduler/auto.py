from __future__ import annotations

from ..qinteract import QZONE_AUTO_INTERACTION_DEFAULT_CRON
from .schedulerbase import SchedulerComponent


class TaskSchedulerAutoService(SchedulerComponent):
    def setup_qzone_auto_interaction_cron(self):
        """设置 QQ 空间自动互动定时触发器。"""
        if not self.services.qzone_interaction.qzone_auto_interaction_enabled():
            return
        self.schedule.cron.setup_cron_job_custom(
            "qzone_auto_interaction",
            self.qzone_conf.get(
                "qzone_auto_interaction_cron", QZONE_AUTO_INTERACTION_DEFAULT_CRON
            ),
            self.schedule.triggers._task_wrapper_qzone_auto_interaction,
        )

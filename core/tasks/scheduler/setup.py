from __future__ import annotations

from astrbot.api import logger

from ...config import CRON_TEMPLATES
from ...database.keys import target_state_key
from ...schedule import BRIEFING_SCHEDULE, GLOBAL_SCHEDULE, QZONE_SCHEDULE
from .schedulerbase import SchedulerComponent
from .cron import ScheduleJobDefinition


class TaskSchedulerSetupService(SchedulerComponent):
    def setup_cleanup_tasks(self):
        self.services.delivery_assets.setup_weixin_temp_cleanup()
        self.services.delivery_assets.setup_news_image_cleanup()

    def setup_tasks(self, *, generation: int):
        if not self.plugin.config.get("enable_auto_share", False):
            logger.debug("[日常分享] 分享内容已禁用")
            return

        self.setup_cleanup_tasks()
        self.setup_cron(generation=generation)
        self.setup_custom_target_crons()

        enable_60s = self.extra_shares_conf.get("enable_60s_news", False)
        enable_ai = self.extra_shares_conf.get("enable_ai_news", False)

        if enable_60s or enable_ai:
            self.setup_briefing_schedule(generation=generation)

        if self.qzone_conf.get("enable_qzone", False):
            self.setup_qzone_cron(generation=generation)
            self.schedule.auto.setup_qzone_auto_interaction_cron()

        self.schedule.track_build(
            self.schedule.recovery._recover_pending_jobs(generation=generation),
            generation,
        )

    def setup_custom_target_crons(self):
        """解析并为写了独立时间的群聊、私聊挂载独立定时。"""
        r_groups = self.services.targets.parse_targets_config(
            self.receiver_conf.get("groups", []), expected_group=True
        )
        r_users = self.services.targets.parse_targets_config(
            self.receiver_conf.get("users", []), expected_group=False
        )

        job_ids = [
            job.id
            for job in self.scheduler.get_jobs()
            if job.id.startswith("custom_share_")
        ]
        for jid in job_ids:
            self.scheduler.remove_job(jid)

        for gid, conf in r_groups.items():
            if isinstance(conf, dict) and conf.get("cron"):
                self._add_custom_target_cron(gid, True, conf["cron"])

        for uid, conf in r_users.items():
            if isinstance(conf, dict) and conf.get("cron"):
                self._add_custom_target_cron(uid, False, conf["cron"])

    def _add_custom_target_cron(
        self, target_id: str, is_group: bool, cron_str: str
    ) -> None:
        if self.services.targets.is_unsupported_weixin_group_target(
            target_id, is_group
        ):
            logger.warning(
                f"[日常分享] 个人微信平台不支持群聊，已跳过独立定时目标: {target_id}"
            )
            return

        async def delayed_execute():
            async def run_share():
                logger.debug(f"[日常分享] 独立时间到达，开始独立分享任务: {target_id}")
                await self.services.share.execute_share(specific_target=target_id)

            await self.schedule.delay._run_tracked_pending_job(
                target_state_key(target_id),
                run_share,
                lock=self._lock,
                locked_warning=f"[日常分享] 独立任务 {target_id} 触发时系统仍在分享，已跳过本次触发",
                background=True,
            )

        async def wrapper():
            if not self.plugin._is_terminated:
                await self.schedule.delay._schedule_or_execute_delayed(
                    state_key=target_state_key(target_id),
                    delay_minutes=self.schedule.delay._read_delay_minutes(
                        self.basic_conf, "cron_random_delay"
                    ),
                    delayed_func=delayed_execute,
                    delayed_job_id=f"delayed_custom_share_{target_id}",
                    log_label=f"独立任务 {target_id}",
                )

        actual_cron = CRON_TEMPLATES.get(cron_str, cron_str)
        cron_kwargs = self.schedule.cron.parse_cron_to_kwargs(actual_cron)
        if not cron_kwargs:
            logger.error(
                f"[日常分享] 独立群聊、私聊任务 [{target_id}] 无效的定时表达式（仅支持标准 5 位）: {cron_str}"
            )
            return
        self.scheduler.add_job(
            wrapper,
            "cron",
            **cron_kwargs,
            id=f"custom_share_{target_id}",
            replace_existing=True,
            max_instances=1,
        )
        logger.debug(
            f"[日常分享] 独立群聊、私聊任务 [{target_id}] 已挂载独立定时: {actual_cron}"
        )

    def setup_cron(self, cron_str: str = "", *, generation: int | None = None):
        """设置自动分享触发器。"""
        if cron_str:
            self.basic_conf["share_cron"] = cron_str
        self.schedule.cron._setup_schedule_job(
            ScheduleJobDefinition(
                config=self.basic_conf,
                schedule=GLOBAL_SCHEDULE,
                base_job_id="auto_share",
                label="全局分享",
                execute=self.schedule.triggers._task_wrapper,
                random_scheduler_job_id="daily_random_scheduler",
                random_scheduler=self.schedule.random._schedule_daily_random_jobs,
                schedule_random=self.schedule.random._schedule_daily_random_jobs,
                smart_scheduler_job_id="daily_smart_scheduler",
                smart_scheduler=self.schedule.smart._schedule_daily_smart_jobs,
                schedule_smart=self.schedule.smart._schedule_daily_smart_jobs,
            ),
            generation=generation,
        )

    def setup_briefing_schedule(self, *, generation: int | None = None):
        """设置早报分享触发器。"""
        self.schedule.cron._setup_schedule_job(
            ScheduleJobDefinition(
                config=self.extra_shares_conf,
                schedule=BRIEFING_SCHEDULE,
                base_job_id="share_briefing",
                label="早报",
                execute=self.schedule.triggers._task_wrapper_briefing,
                random_scheduler_job_id="daily_briefing_random_scheduler",
                random_scheduler=self.schedule.random._schedule_daily_briefing_random_jobs,
                schedule_random=self.schedule.random._schedule_daily_briefing_random_jobs,
                smart_scheduler_job_id="daily_briefing_smart_scheduler",
                smart_scheduler=self.schedule.smart._schedule_daily_briefing_smart_jobs,
                schedule_smart=self.schedule.smart._schedule_daily_briefing_smart_jobs,
            ),
            generation=generation,
        )

    def setup_qzone_cron(self, *, generation: int | None = None):
        """设置 QQ 空间自动分享触发器。"""
        self.schedule.cron._setup_schedule_job(
            ScheduleJobDefinition(
                config=self.qzone_conf,
                schedule=QZONE_SCHEDULE,
                base_job_id="qzone_share",
                label="QQ 空间",
                execute=self.schedule.triggers._task_wrapper_qzone,
                random_scheduler_job_id="daily_qzone_random_scheduler",
                random_scheduler=self.schedule.random._schedule_daily_qzone_random_jobs,
                schedule_random=self.schedule.random._schedule_daily_qzone_random_jobs,
                smart_scheduler_job_id="daily_qzone_smart_scheduler",
                smart_scheduler=self.schedule.smart._schedule_daily_qzone_smart_jobs,
                schedule_smart=self.schedule.smart._schedule_daily_qzone_smart_jobs,
            ),
            generation=generation,
        )

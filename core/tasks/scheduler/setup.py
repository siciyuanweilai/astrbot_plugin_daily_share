from __future__ import annotations

from astrbot.api import logger

from ...config import CRON_TEMPLATES
from ...database.keys import target_state_key


class TaskSchedulerSetupMixin:
    def setup_cleanup_tasks(self):
        self.setup_weixin_temp_cleanup()
        self.setup_news_image_cleanup()

    def setup_tasks(self):
        self.setup_cleanup_tasks()

        if not self.plugin.config.get("enable_auto_share", False):
            logger.debug("[每日分享] 分享内容已禁用")
            return

        self.setup_cron()
        self.setup_custom_target_crons()

        enable_60s = self.extra_shares_conf.get("enable_60s_news", False)
        enable_ai = self.extra_shares_conf.get("enable_ai_news", False)

        if enable_60s or enable_ai:
            self.setup_briefing_schedule()

        if self.qzone_conf.get("enable_qzone", False):
            self.setup_qzone_cron()
            self.setup_qzone_auto_interaction_cron()

        self.plugin._track_task(self._recover_pending_jobs())

    def setup_custom_target_crons(self):
        """解析并为写了独立时间的群聊、私聊挂载独立定时。"""
        default_adapter_id = self._get_default_adapter_id(warn_on_fallback=False)
        r_groups = self._parse_targets_config(self.receiver_conf.get("groups", []))
        r_users = self._parse_targets_config(self.receiver_conf.get("users", []))

        job_ids = [job.id for job in self.scheduler.get_jobs() if job.id.startswith("custom_share_")]
        for jid in job_ids:
            self.scheduler.remove_job(jid)

        def add_custom_job(target_id, is_group, cron_str):
            job_id = f"custom_share_{target_id}"
            target_umo = self._build_target_umo(target_id, is_group, default_adapter_id)
            if self._is_unsupported_weixin_group_target(target_umo, is_group):
                logger.warning(f"[每日分享] 个人微信平台不支持群聊，已跳过独立定时目标: {target_id}")
                return

            async def delayed_custom_execute():
                async def run_custom_share():
                    logger.debug(f"[每日分享] 独立时间到达，开始独立分享任务: {target_id}")
                    await self.execute_share(specific_target=target_umo)

                await self._run_tracked_pending_job(
                    target_state_key(target_id),
                    run_custom_share,
                    lock=self._lock,
                    locked_warning=f"[每日分享] 独立任务 {target_id} 触发，系统繁忙排队中...",
                    background=True,
                )

            async def custom_wrapper():
                if self.plugin._is_terminated:
                    return
                await delayed_custom_execute()

            actual_cron = CRON_TEMPLATES.get(cron_str, cron_str)
            cron_kwargs = self._parse_cron_to_kwargs(actual_cron)

            if cron_kwargs:
                self.scheduler.add_job(
                    custom_wrapper,
                    "cron",
                    **cron_kwargs,
                    id=job_id,
                    replace_existing=True,
                    max_instances=1,
                )
                logger.debug(f"[每日分享] 独立群聊、私聊任务 [{target_id}] 已挂载独立定时: {actual_cron}")
            else:
                logger.error(f"[每日分享] 独立群聊、私聊任务 [{target_id}] 无效的定时表达式（支持 5/6/7 位）: {cron_str}")

        for gid, conf in r_groups.items():
            if isinstance(conf, dict) and conf.get("cron"):
                add_custom_job(gid, True, conf["cron"])

        for uid, conf in r_users.items():
            if isinstance(conf, dict) and conf.get("cron"):
                add_custom_job(uid, False, conf["cron"])

    def setup_cron(self, cron_str: str = ""):
        """设置自动分享触发器。"""
        if cron_str:
            self.basic_conf["share_cron"] = cron_str
        self._setup_schedule_job(
            self.basic_conf,
            mode_key="trigger_mode",
            mode_default="llm_smart",
            fixed_key="fixed_times",
            fixed_default=["08:00", "20:00"],
            cron_key="share_cron",
            cron_default="0 8,20 * * *",
            base_job_id="auto_share",
            label="全局分享",
            func=self._task_wrapper,
            random_scheduler_job_id="daily_random_scheduler",
            random_scheduler_func=self._schedule_daily_random_jobs,
            schedule_random_func=self._schedule_daily_random_jobs,
            smart_scheduler_job_id="daily_smart_scheduler",
            smart_scheduler_func=self._schedule_daily_smart_jobs,
            schedule_smart_func=self._schedule_daily_smart_jobs,
        )

    def setup_briefing_schedule(self):
        """设置早报分享触发器。"""
        self._setup_schedule_job(
            self.extra_shares_conf,
            mode_key="briefing_schedule_mode",
            mode_default="llm_smart",
            fixed_key="briefing_fixed_times",
            fixed_default=["08:00"],
            cron_key="cron_briefing",
            cron_default="0 8 * * *",
            base_job_id="share_briefing",
            label="早报",
            func=self._task_wrapper_briefing,
            random_scheduler_job_id="daily_briefing_random_scheduler",
            random_scheduler_func=self._schedule_daily_briefing_random_jobs,
            schedule_random_func=self._schedule_daily_briefing_random_jobs,
            smart_scheduler_job_id="daily_briefing_smart_scheduler",
            smart_scheduler_func=self._schedule_daily_briefing_smart_jobs,
            schedule_smart_func=self._schedule_daily_briefing_smart_jobs,
        )

    def setup_qzone_cron(self):
        """设置 QQ 空间自动分享触发器。"""
        self._setup_schedule_job(
            self.qzone_conf,
            mode_key="qzone_trigger_mode",
            mode_default="llm_smart",
            fixed_key="qzone_fixed_times",
            fixed_default=["20:00"],
            cron_key="qzone_cron",
            cron_default="0 20 * * *",
            base_job_id="qzone_share",
            label="QQ 空间",
            func=self._task_wrapper_qzone,
            random_scheduler_job_id="daily_qzone_random_scheduler",
            random_scheduler_func=self._schedule_daily_qzone_random_jobs,
            schedule_random_func=self._schedule_daily_qzone_random_jobs,
            smart_scheduler_job_id="daily_qzone_smart_scheduler",
            smart_scheduler_func=self._schedule_daily_qzone_smart_jobs,
            schedule_smart_func=self._schedule_daily_qzone_smart_jobs,
        )

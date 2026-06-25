from datetime import datetime

from astrbot.api import logger

from ...database.keys import BRIEFING_STATE_KEY, GLOBAL_STATE_KEY, QZONE_STATE_KEY
from ..qinteract import QZONE_AUTO_INTERACTION_STATE_KEY


class TaskSchedulerTriggerMixin:
    """定时任务触发入口。"""

    def _scheduled_random_delay_minutes(
        self,
        *,
        mode_conf: dict,
        mode_key: str,
        delay_conf: dict,
        delay_key: str,
        mode_default: str = "llm_smart",
    ) -> int:
        mode = str((mode_conf or {}).get(mode_key, mode_default) or mode_default).strip()
        if mode not in {"fixed_time", "cron"}:
            return 0
        return self._read_delay_minutes(delay_conf or {}, delay_key)

    async def _task_wrapper(self):
        """主任务触发器（处理防抖与随机延迟记录）"""
        if self.plugin._is_terminated: return

        # 数据库自动清理        
        try:
            days_limit = self.content_service.dedup_days
            await self.db.clean_expired_data(days_limit)
        except Exception as e:
            logger.warning(f"[每日分享] 数据库清理失败: {e}")

        random_delay_min = self._scheduled_random_delay_minutes(
            mode_conf=self.basic_conf,
            mode_key="trigger_mode",
            delay_conf=self.basic_conf,
            delay_key="cron_random_delay",
        )
        await self._schedule_or_execute_delayed(
            state_key=GLOBAL_STATE_KEY,
            delay_minutes=random_delay_min,
            delayed_func=self._execute_delayed_task,
            delayed_job_id="delayed_auto_share",
            log_label="定时任务",
        )

    async def _execute_delayed_task(self):
        """主分享任务入口。"""
        async def before_share():
            now = datetime.now()
            if self.plugin._last_share_time:
                if (now - self.plugin._last_share_time).total_seconds() < 60:
                    logger.debug("[每日分享] 检测到近期已分享，跳过本次触发。")
                    return False
            self.plugin._last_share_time = now
            return True

        async def run_share():
            logger.info("[每日分享] 开始分享任务...")
            await self.execute_share()

        await self._run_tracked_pending_job(
            GLOBAL_STATE_KEY,
            run_share,
            lock=self._lock,
            locked_warning="[每日分享] 上一个任务正在进行中，本次触发将排队等待...",
            before_action=before_share,
            background=True,
        )

    async def _task_wrapper_briefing(self):
        """早报任务触发器（处理随机延迟记录）"""
        if self.plugin._is_terminated: return
        random_delay_min = self._scheduled_random_delay_minutes(
            mode_conf=self.extra_shares_conf,
            mode_key="briefing_schedule_mode",
            delay_conf=self.extra_shares_conf,
            delay_key="briefing_cron_random_delay",
        )
        await self._schedule_or_execute_delayed(
            state_key=BRIEFING_STATE_KEY,
            delay_minutes=random_delay_min,
            delayed_func=self._execute_delayed_briefing_task,
            delayed_job_id="delayed_briefing_share",
            log_label="早报任务",
        )

    async def _execute_delayed_briefing_task(self):
        """早报分享任务入口。"""
        async def run_briefing_share():
            await self.execute_briefing_share()

        await self._run_tracked_pending_job(BRIEFING_STATE_KEY, run_briefing_share, background=True)

    async def _task_wrapper_qzone(self):
        """QQ 空间任务触发器（处理防抖与随机延迟记录）。"""
        if self.plugin._is_terminated: return
        
        random_delay_min = self._scheduled_random_delay_minutes(
            mode_conf=self.qzone_conf,
            mode_key="qzone_trigger_mode",
            delay_conf=self.basic_conf,
            delay_key="cron_random_delay",
        )
        await self._schedule_or_execute_delayed(
            state_key=QZONE_STATE_KEY,
            delay_minutes=random_delay_min,
            delayed_func=self._execute_delayed_qzone_task,
            delayed_job_id="delayed_qzone_share",
            log_label="QQ 空间任务",
        )

    async def _execute_delayed_qzone_task(self):
        """QQ 空间分享任务入口。"""
        async def run_qzone_share():
            logger.info("[每日分享] 开始 QQ 空间分享任务...")
            await self.execute_qzone_share()

        await self._run_tracked_pending_job(QZONE_STATE_KEY, run_qzone_share, lock=self._lock, background=True)

    async def _task_wrapper_qzone_auto_interaction(self):
        """QQ 空间自动互动任务入口。"""
        if self.plugin._is_terminated:
            return

        async def run_qzone_auto_interaction():
            logger.info("[每日分享] 开始 QQ 空间自动互动任务...")
            await self.execute_qzone_auto_interaction()

        await self._run_tracked_pending_job(
            QZONE_AUTO_INTERACTION_STATE_KEY,
            run_qzone_auto_interaction,
            lock=self._qzone_auto_interaction_lock,
            locked_warning="[每日分享] 上一个 QQ 空间自动互动任务正在进行中，本次触发将排队等待...",
            background=True,
        )

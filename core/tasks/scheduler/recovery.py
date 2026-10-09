import random
from datetime import datetime, timedelta

from astrbot.api import logger

from ...database.keys import (
    BRIEFING_STATE_KEY,
    GLOBAL_STATE_KEY,
    QZONE_STATE_KEY,
    target_state_key,
)
from .schedulerbase import SchedulerComponent

_RECENT_MISSED_JOB_WINDOW_SECONDS = 3600


class TaskSchedulerRecoveryService(SchedulerComponent):
    """延迟任务清理和重启恢复。"""

    async def clear_pending_delay_jobs(self):
        """清理已记录但尚未完成的延迟任务，确保关闭后不会补发旧任务。"""
        await self.db.update_share_state(GLOBAL_STATE_KEY, {"pending_delay_job": None})
        await self.db.update_share_state(QZONE_STATE_KEY, {"pending_delay_job": None})
        await self.db.update_share_state(
            BRIEFING_STATE_KEY, {"pending_delay_job": None}
        )

        r_groups = self.services.targets.parse_targets_config(
            self.receiver_conf.get("groups", []), expected_group=True
        )
        r_users = self.services.targets.parse_targets_config(
            self.receiver_conf.get("users", []), expected_group=False
        )
        for target_id in list(r_groups.keys()) + list(r_users.keys()):
            if target_id:
                await self.db.update_share_state(
                    target_state_key(target_id), {"pending_delay_job": None}
                )

    @staticmethod
    def _pending_target_timestamp(pending: dict) -> float | None:
        try:
            target_ts = float((pending or {}).get("target_time") or 0)
        except (TypeError, ValueError):
            return None
        return target_ts if target_ts > 0 else None

    def _pending_recovery_plan(
        self,
        pending: dict,
        *,
        now: datetime,
        now_ts: float,
        missed_delay_seconds: int,
    ) -> tuple[datetime | None, str]:
        target_ts = self._pending_target_timestamp(pending)
        if target_ts is None:
            return None, "expired"
        if target_ts > now_ts:
            return datetime.fromtimestamp(target_ts), "future"
        if 0 <= now_ts - target_ts < _RECENT_MISSED_JOB_WINDOW_SECONDS:
            return now + timedelta(seconds=missed_delay_seconds), "missed"
        return None, "expired"

    async def _recover_pending_delay_job(
        self,
        *,
        state_key: str,
        state: dict,
        job,
        job_id: str,
        missed_delay_seconds: int,
        future_log: str = "",
        missed_log: str = "",
        now: datetime,
        now_ts: float,
        generation: int,
    ) -> None:
        if not self.schedule.is_current_build(generation):
            return
        pending = state.get("pending_delay_job") if isinstance(state, dict) else None
        if not pending:
            return

        run_time, status = self._pending_recovery_plan(
            pending,
            now=now,
            now_ts=now_ts,
            missed_delay_seconds=missed_delay_seconds,
        )
        if run_time is None:
            if self.schedule.is_current_build(generation):
                await self.db.update_share_state(state_key, {"pending_delay_job": None})
            return

        if not self.schedule.is_current_build(generation):
            return
        self.scheduler.add_job(
            job,
            "date",
            run_date=run_time,
            id=job_id,
            replace_existing=True,
        )
        if status == "future" and future_log:
            logger.debug(future_log.format(time=run_time.strftime("%H:%M:%S")))
        elif status == "missed" and missed_log:
            logger.debug(missed_log)

    async def _recover_standard_pending_jobs(
        self, *, now: datetime, now_ts: float, generation: int
    ) -> None:
        jobs = [
            (
                GLOBAL_STATE_KEY,
                self.schedule.triggers._execute_delayed_task,
                "resume_auto_share",
                5,
                "[日常分享] 已恢复未完成的延迟分享任务，将在 {time} 分享",
                "[日常分享] 检测到近期错过的延迟分享任务，即将补偿分享",
            ),
            (
                QZONE_STATE_KEY,
                self.schedule.triggers._execute_delayed_qzone_task,
                "resume_qzone_share",
                10,
                "[日常分享] 已恢复未完成的 QQ 空间延迟分享任务，将在 {time} 分享",
                "[日常分享] 检测到近期错过的 QQ 空间延迟任务，即将补偿分享",
            ),
            (
                BRIEFING_STATE_KEY,
                self.schedule.triggers._execute_delayed_briefing_task,
                "resume_briefing_share",
                10,
                "[日常分享] 已恢复未完成的早报延迟分享任务，将在 {time} 分享",
                "[日常分享] 检测到近期错过的早报延迟任务，即将补偿分享",
            ),
        ]
        for state_key, job, job_id, delay, future_log, missed_log in jobs:
            state = await self.db.get_share_state(state_key, {})
            await self._recover_pending_delay_job(
                state_key=state_key,
                state=state,
                job=job,
                job_id=job_id,
                missed_delay_seconds=delay,
                future_log=future_log,
                missed_log=missed_log,
                now=now,
                now_ts=now_ts,
                generation=generation,
            )

    def _custom_recovery_targets(self) -> list[tuple[str, bool]]:
        r_groups = self.services.targets.parse_targets_config(
            self.receiver_conf.get("groups", []), expected_group=True
        )
        r_users = self.services.targets.parse_targets_config(
            self.receiver_conf.get("users", []), expected_group=False
        )
        return [(gid, True) for gid in r_groups.keys() if gid] + [
            (uid, False) for uid in r_users.keys() if uid
        ]

    def _recover_custom_job(self, tid: str):
        async def delayed_recover():
            if self.plugin._is_terminated:
                return
            await self.db.update_share_state(
                target_state_key(tid), {"pending_delay_job": None}
            )

            async def run_custom_recover():
                logger.debug(f"[日常分享] 补偿恢复，开始独立分享任务: {tid}")
                await self.services.share.execute_share(specific_target=tid)

            await self.schedule.delay._run_tracked_pending_job(
                target_state_key(tid),
                run_custom_recover,
                lock=self._lock,
                locked_warning=f"[日常分享] 恢复独立任务 {tid} 时系统仍在分享，已跳过本次恢复",
            )

        return delayed_recover

    async def _recover_custom_pending_jobs(
        self, *, now: datetime, now_ts: float, generation: int
    ) -> None:
        for tid, is_group in self._custom_recovery_targets():
            if not self.schedule.is_current_build(generation):
                return
            state_key = target_state_key(tid)
            if self.services.targets.is_unsupported_weixin_group_target(tid, is_group):
                logger.warning(
                    f"[日常分享] 个人微信平台不支持群聊，已跳过恢复目标: {tid}"
                )
                await self.db.update_share_state(state_key, {"pending_delay_job": None})
                continue

            state = await self.db.get_share_state(state_key, {})
            await self._recover_pending_delay_job(
                state_key=state_key,
                state=state,
                job=self._recover_custom_job(tid),
                job_id=f"resume_custom_share_{tid}",
                missed_delay_seconds=random.randint(10, 30),
                now=now,
                now_ts=now_ts,
                generation=generation,
            )

    async def _recover_pending_jobs(self, *, generation: int | None = None):
        """恢复因重启中断的延迟任务。"""
        generation = (
            self.schedule._build_generation if generation is None else generation
        )
        if not self.schedule.is_current_build(generation):
            return

        now = datetime.now()
        now_ts = now.timestamp()
        await self._recover_standard_pending_jobs(
            now=now, now_ts=now_ts, generation=generation
        )
        await self._recover_custom_pending_jobs(
            now=now, now_ts=now_ts, generation=generation
        )

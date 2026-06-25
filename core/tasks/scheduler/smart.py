import hashlib
import json
import random
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from astrbot.api import logger

from ...config import ShareType
from ...constants import normalize_share_type_token
from ...database.keys import (
    BRIEFING_STATE_KEY,
    GLOBAL_STATE_KEY,
    QZONE_STATE_KEY,
    QZONE_TARGET_ID,
    SOURCE_SMART,
)
from ...prompt import build_smart_schedule_rules


class TaskSchedulerSmartMixin:
    """智能定时每日计划生成。"""

    @staticmethod
    def _smart_json_loads(text: str) -> Any:
        raw = str(text or "").strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
        if not raw:
            raise ValueError("智能定时未返回计划")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("[")
            end = raw.rfind("]")
            if start >= 0 and end > start:
                return json.loads(raw[start : end + 1])
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                return json.loads(raw[start : end + 1])
            raise

    @staticmethod
    def _smart_today_time(now: datetime, value: str) -> Optional[datetime]:
        raw = str(value or "").strip()
        if not raw:
            return None
        raw = raw.replace("T", " ").replace("/", "-")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%H:%M:%S", "%H:%M"):
            try:
                parsed = datetime.strptime(raw, fmt)
                if "%Y" in fmt:
                    return parsed
                return now.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)
            except ValueError:
                continue
        return None

    @staticmethod
    def _smart_minutes(dt: datetime) -> int:
        return dt.hour * 60 + dt.minute

    @staticmethod
    def _smart_time_range_minutes(value: str) -> Optional[tuple[int, int]]:
        match = re.match(
            r"^\s*((?:[01]?\d|2[0-3]):[0-5]\d)\s*-\s*((?:[01]?\d|2[0-3]):[0-5]\d)\s*$",
            str(value or ""),
        )
        if not match:
            return None
        start_text, end_text = match.groups()
        start_h, start_m = [int(part) for part in start_text.split(":", 1)]
        end_h, end_m = [int(part) for part in end_text.split(":", 1)]
        start = start_h * 60 + start_m
        end = end_h * 60 + end_m
        return (start, end) if start != end else None

    def _smart_quiet_contains(self, dt: datetime, quiet_hours: list[str]) -> bool:
        minute = self._smart_minutes(dt)
        for item in quiet_hours:
            parsed = self._smart_time_range_minutes(item)
            if not parsed:
                continue
            start, end = parsed
            if start < end and start <= minute < end:
                return True
            if start > end and (minute >= start or minute < end):
                return True
        return False

    def _smart_schedule_signature(
        self,
        *,
        task_kind: str,
        conf: dict,
        max_key: str,
        quiet_hours: list[str],
        prompt_key: str,
        share_type_key: str = "",
    ) -> str:
        payload = {
            "task": task_kind,
            "max": conf.get(max_key),
            "quiet_hours": quiet_hours,
            "prompt": conf.get(prompt_key),
            "share_type": conf.get(share_type_key) if share_type_key else "",
        }
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha1(data.encode("utf-8")).hexdigest()[:16]

    def _smart_max_count(self, conf: dict, key: str, default: int) -> int:
        try:
            value = int(conf.get(key, default))
        except Exception:
            value = default
        return max(1, min(6, value))

    def _smart_quiet_hours(self, conf: dict, key: str, default: list[str]) -> list[str]:
        source = conf.get(key, default) if key in conf else default
        return [str(item).strip() for item in (source or []) if str(item).strip()]

    def _smart_share_type(self, value: Any) -> Optional[ShareType]:
        normalized = normalize_share_type_token(value, allow_auto=True)
        if not normalized or normalized == "auto":
            return None
        try:
            return ShareType(normalized)
        except ValueError:
            return None

    @staticmethod
    def _smart_min_gap_minutes(task_kind: str) -> int:
        return 120 if task_kind == "qzone" else 60

    @staticmethod
    def _smart_naturalize_seconds(dt: datetime) -> datetime:
        if dt.second != 0:
            return dt.replace(microsecond=0)
        return dt.replace(second=random.randrange(5, 56), microsecond=0)

    def _smart_normalize_jobs(
        self,
        raw_jobs: Any,
        *,
        now: datetime,
        max_count: int,
        quiet_hours: list[str],
        allow_share_type: bool,
        source: str = "llm",
        min_gap_minutes: int = 60,
    ) -> list[dict]:
        if isinstance(raw_jobs, dict):
            raw_jobs = raw_jobs.get("jobs") or raw_jobs.get("schedule") or []
        if not isinstance(raw_jobs, list):
            return []

        result = []
        seen_minutes = set()
        accepted_times = []
        for item in raw_jobs:
            if not isinstance(item, dict):
                continue
            run_at = self._smart_today_time(now, item.get("run_at") or item.get("time") or item.get("datetime"))
            if not run_at or run_at.date() != now.date():
                continue
            run_at = self._smart_naturalize_seconds(run_at)
            if run_at <= now + timedelta(seconds=30):
                continue
            if self._smart_quiet_contains(run_at, quiet_hours):
                continue
            minute_key = run_at.strftime("%Y-%m-%d %H:%M")
            if minute_key in seen_minutes:
                continue
            if any(abs((run_at - accepted).total_seconds()) < min_gap_minutes * 60 for accepted in accepted_times):
                continue
            share_type = str(item.get("share_type") or item.get("type") or "自动").strip() or "自动"
            if allow_share_type and share_type != "自动" and not self._smart_share_type(share_type):
                share_type = "自动"
            else:
                share_type = "自动" if not allow_share_type else share_type
            result.append(
                {
                    "run_at": run_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "share_type": share_type,
                    "reason": str(item.get("reason") or "").strip()[:120],
                    "source": source,
                }
            )
            seen_minutes.add(minute_key)
            accepted_times.append(run_at)
            if len(result) >= max_count:
                break
        result.sort(key=lambda item: item["run_at"])
        return result

    def _smart_targets_summary(self, task_kind: str) -> str:
        if task_kind == "briefing":
            groups = self.extra_shares_conf.get("briefing_groups", []) or []
            users = self.extra_shares_conf.get("briefing_users", []) or []
            enabled = []
            if self.extra_shares_conf.get("enable_60s_news", False):
                enabled.append("60s早报")
            if self.extra_shares_conf.get("enable_ai_news", False):
                enabled.append("AI资讯")
            return (
                f"早报类型：{'、'.join(enabled) if enabled else '未开启'}；"
                f"群聊目标 {len(groups)} 个，私聊目标 {len(users)} 个；"
                f"同步QQ空间：{'是' if self.extra_shares_conf.get('sync_briefing_to_qzone', False) else '否'}"
            )
        if task_kind == "qzone":
            return (
                f"QQ空间说说；默认类型：{self.qzone_conf.get('qzone_share_type', '自动')}；"
                f"配图：{'开启' if self.qzone_conf.get('qzone_enable_image', False) else '关闭'}"
            )
        groups = self.receiver_conf.get("groups", []) or []
        users = self.receiver_conf.get("users", []) or []
        return (
            f"全局分享；群聊目标 {len(groups)} 个，私聊目标 {len(users)} 个；"
            f"默认类型：{self.basic_conf.get('share_type', '自动')}"
        )

    async def _smart_life_summary(self) -> str:
        try:
            life_ctx = await self.ctx_service.get_life_context()
        except Exception:
            return ""
        text = str(life_ctx or "").strip()
        if len(text) > 800:
            text = f"{text[:800].rstrip()}..."
        return text

    async def _smart_recent_history_summary(self, task_kind: str) -> str:
        try:
            if task_kind == "qzone":
                records = await self.db.get_recent_history_by_target(QZONE_TARGET_ID, limit=6)
            else:
                records = await self.db.get_recent_history(limit=6)
        except Exception:
            return ""

        lines = []
        for item in records or []:
            if not item.get("success", True):
                continue
            timestamp = str(item.get("timestamp") or "")[:16]
            share_type = str(item.get("type") or "未知类型")
            source = str(item.get("source_type") or "未知来源")
            target = "QQ空间" if item.get("target_id") == QZONE_TARGET_ID else str(item.get("target_id") or "未知目标")
            lines.append(f"{timestamp} {target} {share_type} 来源:{source}".strip())
            if len(lines) >= 5:
                break
        return "；".join(lines)

    async def _generate_llm_smart_jobs(
        self,
        *,
        task_kind: str,
        label: str,
        now: datetime,
        max_count: int,
        quiet_hours: list[str],
        custom_prompt: str,
        allow_share_type: bool,
    ) -> list[dict]:
        call_llm = getattr(self.plugin, "_call_llm_wrapper", None)
        if not callable(call_llm):
            raise RuntimeError("未配置可用 LLM")

        share_types = "自动、问候、新闻、心情、知识、推荐" if allow_share_type else "自动"
        quiet_text = "、".join(quiet_hours) if quiet_hours else "未设置"
        life_summary = await self._smart_life_summary()
        history_summary = await self._smart_recent_history_summary(task_kind)
        prompt = (
            "请为每日分享插件生成今天剩余时间的智能定时计划。"
            "需要综合任务目标、生活/日程摘要、近期分享记录和用户偏好选择自然时间。\n"
            f"当前本地时间：{now.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"任务：{label}\n"
            f"最多安排 {max_count} 次。\n"
            f"勿扰时间：{quiet_text}。\n"
            f"允许分享类型：{share_types}\n"
            f"任务上下文：{self._smart_targets_summary(task_kind)}\n"
            f"{'生活/日程摘要：' + life_summary + chr(10) if life_summary else ''}"
            f"{'近期分享记录：' + history_summary + chr(10) if history_summary else ''}"
            f"{'用户偏好：' + custom_prompt + chr(10) if custom_prompt else ''}"
            "run_at 必须使用 YYYY-MM-DD HH:MM:SS，秒数请选择 05-55 的自然随机秒，不要使用 :00。\n"
            "请只输出 JSON 数组，不要解释。数组项格式："
            "{\"run_at\":\"YYYY-MM-DD HH:MM:SS\",\"share_type\":\"自动|问候|新闻|心情|知识|推荐\",\"reason\":\"简短原因\"}。"
        )
        system_prompt = build_smart_schedule_rules()
        result = await call_llm(
            prompt=prompt,
            system_prompt=system_prompt,
            timeout=45,
            max_retries=1,
        )
        jobs = self._smart_json_loads(result)
        return self._smart_normalize_jobs(
            jobs,
            now=now,
            max_count=max_count,
            quiet_hours=quiet_hours,
            allow_share_type=allow_share_type,
            source="llm",
            min_gap_minutes=self._smart_min_gap_minutes(task_kind),
        )

    async def _schedule_daily_llm_smart_jobs(
        self,
        *,
        state_key: str,
        task_kind: str,
        label: str,
        conf: dict,
        max_key: str,
        max_default: int,
        quiet_key: str,
        quiet_default: list[str],
        prompt_key: str,
        job_prefix: str,
        allow_share_type: bool,
        default_share_type_key: str = "",
    ) -> None:
        if self.plugin._is_terminated:
            return

        get_jobs = getattr(self.scheduler, "get_jobs", None)
        for job in list(get_jobs() if callable(get_jobs) else []):
            job_id = getattr(job, "id", "")
            if not job_id and isinstance(job, dict):
                job_id = (job.get("kwargs") or {}).get("id", "")
            if str(job_id).startswith(job_prefix):
                self.scheduler.remove_job(job_id)

        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        max_count = self._smart_max_count(conf, max_key, max_default)
        quiet_hours = self._smart_quiet_hours(conf, quiet_key, quiet_default)
        min_gap_minutes = self._smart_min_gap_minutes(task_kind)
        custom_prompt = str(conf.get(prompt_key, "") or "").strip()
        signature = self._smart_schedule_signature(
            task_kind=task_kind,
            conf=conf,
            max_key=max_key,
            quiet_hours=quiet_hours,
            prompt_key=prompt_key,
            share_type_key=default_share_type_key,
        )
        state = await self.db.get_state(state_key, {})
        smart_schedule = state.get("smart_schedule", {}) if isinstance(state, dict) else {}
        jobs = []
        if (
            isinstance(smart_schedule, dict)
            and smart_schedule.get("date") == date_str
            and smart_schedule.get("signature") == signature
            and isinstance(smart_schedule.get("jobs"), list)
        ):
            jobs = self._smart_normalize_jobs(
                smart_schedule.get("jobs"),
                now=now,
                max_count=max_count,
                quiet_hours=quiet_hours,
                allow_share_type=allow_share_type,
                source=str(smart_schedule.get("source") or "llm"),
                min_gap_minutes=min_gap_minutes,
            )
        else:
            error = ""
            try:
                jobs = await self._generate_llm_smart_jobs(
                    task_kind=task_kind,
                    label=label,
                    now=now,
                    max_count=max_count,
                    quiet_hours=quiet_hours,
                    custom_prompt=custom_prompt,
                    allow_share_type=allow_share_type,
                )
            except Exception as exc:
                error = str(exc).strip() or exc.__class__.__name__
                logger.warning(f"[每日分享] {label}智能定时生成失败，今日不安排智能定时任务: {error}")

            if not jobs:
                error = error or "智能定时未返回可用计划"
                logger.warning(f"[每日分享] {label}智能定时未生成可用计划，今日不安排智能定时任务: {error}")

            await self.db.update_state_dict(
                state_key,
                {
                    "smart_schedule": {
                        "date": date_str,
                        "signature": signature,
                        "source": "llm" if jobs else "none",
                        "jobs": jobs,
                        "last_error": error,
                        "updated_at": now.isoformat(timespec="seconds"),
                    }
                },
            )

        for index, item in enumerate(jobs):
            run_time = self._smart_today_time(now, item.get("run_at"))
            if not run_time or run_time <= now:
                continue
            share_type = str(item.get("share_type") or "自动")
            reason = str(item.get("reason") or "").strip()

            async def smart_job(item=item):
                await self._execute_llm_smart_schedule_item(task_kind, item)

            job_name = f"{label}智能定时"
            if allow_share_type and share_type and share_type != "自动":
                job_name = f"{job_name} · {share_type}"
            self.scheduler.add_job(
                smart_job,
                "date",
                run_date=run_time,
                id=f"{job_prefix}{index}",
                name=job_name,
                replace_existing=True,
            )
            logger.debug(
                f"[每日分享] {label}智能定时已安排: {run_time.strftime('%H:%M')} "
                f"{share_type if allow_share_type else ''} {reason}"
            )

    async def _execute_llm_smart_schedule_item(self, task_kind: str, item: dict) -> None:
        share_type = self._smart_share_type(item.get("share_type"))
        source_type = SOURCE_SMART
        if task_kind == "briefing":
            async def run_briefing():
                logger.info("[每日分享] 开始智能定时早报任务...")
                await self.execute_briefing_share(source_type=source_type)

            await self._run_tracked_pending_job(BRIEFING_STATE_KEY, run_briefing, background=True)
            return

        if task_kind == "qzone":
            async def run_qzone():
                logger.info("[每日分享] 开始智能定时 QQ 空间任务...")
                await self.execute_qzone_share(force_type=share_type, source_type=source_type)

            await self._run_tracked_pending_job(QZONE_STATE_KEY, run_qzone, lock=self._lock, background=True)
            return

        async def before_share():
            now = datetime.now()
            last_share_time = getattr(self.plugin, "_last_share_time", None)
            if last_share_time:
                if (now - last_share_time).total_seconds() < 60:
                    logger.debug("[每日分享] 检测到近期已分享，跳过本次智能定时触发。")
                    return False
            setattr(self.plugin, "_last_share_time", now)
            return True

        async def run_share():
            logger.info("[每日分享] 开始智能定时分享任务...")
            await self.execute_share(force_type=share_type, source_type=source_type)

        await self._run_tracked_pending_job(
            GLOBAL_STATE_KEY,
            run_share,
            lock=self._lock,
            locked_warning="[每日分享] 上一个任务正在进行中，智能定时分享将排队等待...",
            before_action=before_share,
            background=True,
        )

    async def _schedule_daily_smart_jobs(self):
        await self._schedule_daily_llm_smart_jobs(
            state_key=GLOBAL_STATE_KEY,
            task_kind="global",
            label="全局分享",
            conf=self.basic_conf,
            max_key="smart_schedule_max_count",
            max_default=2,
            quiet_key="smart_schedule_quiet_hours",
            quiet_default=["23:30-07:30"],
            prompt_key="smart_schedule_prompt",
            job_prefix="smart_share_",
            allow_share_type=True,
            default_share_type_key="share_type",
        )

    async def _schedule_daily_briefing_smart_jobs(self):
        await self._schedule_daily_llm_smart_jobs(
            state_key=BRIEFING_STATE_KEY,
            task_kind="briefing",
            label="早报",
            conf=self.extra_shares_conf,
            max_key="briefing_smart_schedule_max_count",
            max_default=1,
            quiet_key="briefing_smart_schedule_quiet_hours",
            quiet_default=["23:30-07:30"],
            prompt_key="briefing_smart_schedule_prompt",
            job_prefix="briefing_smart_share_",
            allow_share_type=False,
        )

    async def _schedule_daily_qzone_smart_jobs(self):
        await self._schedule_daily_llm_smart_jobs(
            state_key=QZONE_STATE_KEY,
            task_kind="qzone",
            label="QQ 空间",
            conf=self.qzone_conf,
            max_key="qzone_smart_schedule_max_count",
            max_default=1,
            quiet_key="qzone_smart_schedule_quiet_hours",
            quiet_default=["23:30-07:30"],
            prompt_key="qzone_smart_schedule_prompt",
            job_prefix="qzone_smart_share_",
            allow_share_type=True,
            default_share_type_key="qzone_share_type",
        )

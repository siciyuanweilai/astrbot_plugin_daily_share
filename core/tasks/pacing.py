"""独立分享的持久节奏；只保存时间和事实摘要，不跨会话传递正文。"""

from __future__ import annotations

import asyncio
import math
import time
from datetime import datetime

from ..database.keys import BILIBILI_TARGET_ID, SOURCE_LIFE, SOURCE_SMART, is_public_share_target
from .opportunity import digest

PACED_SOURCES = frozenset({SOURCE_LIFE, SOURCE_SMART})
STATE_KEY = "autonomous_share_pacing"


def timestamp(value):
    try:
        if isinstance(value, str):
            # 历史由 datetime.now() 写入，使用同一宿主时区解释。
            value = datetime.fromisoformat(value).timestamp()
        value = float(value)
        return value if math.isfinite(value) and value > 0 else 0
    except (TypeError, ValueError, OverflowError, OSError):
        return 0


def episodes(materials):
    return list(dict.fromkeys(
        row.get("episode_id") or row.get("id")
        for row in materials if row.get("episode_id") or row.get("id")
    ))[:16]


class SharePacingService:
    def __init__(self, plugin):
        self.plugin = plugin
        # 首次提交的检查与登记串行；原任务的分段不重新领取机会。
        self.lock = asyncio.Lock()

    def interval(self, target):
        public = is_public_share_target(target)
        conf = (self.plugin.config.get("bilibili_conf", {}) if target == BILIBILI_TARGET_ID
                else self.plugin.qzone_conf if public else self.plugin.basic_conf)
        default = 90 if public else 45
        try:
            value = conf.get("autonomous_share_interval_minutes", default)
            value = int(value) if not isinstance(value, bool) else default
            return max(15, min(360, value)) * 60
        except (TypeError, ValueError, OverflowError):
            return default * 60

    async def records(self, target, now):
        states = await self.plugin.db.get_share_state(STATE_KEY, {})
        key = digest(target)
        own = list((states.get(key) or {}).get("records") or [])
        rows = [dict(row) for row in own]
        history = await self.plugin.db.get_recent_history_by_target(target, limit=48)
        # 已有成功记录立即成为升级基线。已登记的自主历史仍提供完成时点，
        # 但不重复计算联系轮数；手动及定时记录也可让下一次自主分享稍歇。
        first = min((timestamp(row.get("at")) for row in own), default=now + 1)
        for row in history:
            if not row.get("success", True):
                continue
            at = timestamp(row.get("timestamp"))
            source = row.get("source_type")
            if source in PACED_SOURCES and at >= first - 1:
                source = None
            rows.append({"at": at, "source": source, "episodes": []})
        rows = [row for row in rows if 0 < timestamp(row.get("at")) <= now + 60
                and now - timestamp(row.get("at")) < 86400]
        return states, sorted(rows, key=lambda row: timestamp(row.get("at")))

    def episode_wait(self, target, selected, states, now):
        if not selected:
            return 0
        key = digest(target)
        public = is_public_share_target(target)
        remaining = 0
        for scope, state in states.items():
            same = scope == key
            # 不同私聊对象互不压制；私聊与公开渠道只比较不透明事实摘要。
            if not same and not (public or state.get("public")):
                continue
            window = 180 * 60 if same else 90 * 60
            for row in state.get("records") or []:
                if set(selected).intersection(row.get("episodes") or []):
                    remaining = max(remaining, timestamp(row.get("at")) + window - now)
        return max(0, remaining)

    async def check(self, target, *, data=None, selected=(), source=SOURCE_LIFE, now=None):
        if source not in PACED_SOURCES:
            return {"ready": True, "retry_after": 0, "reason": ""}
        now = time.time() if now is None else now
        states, rows = await self.records(target, now)
        interval = self.interval(target)
        reason = "刚分享过，留一点交流和生活的空隙"
        if rows:
            if not is_public_share_target(target) and ":GroupMessage:" not in target:
                if data is None:
                    data = await self.plugin.daily_life_bridge.get_share_context(target)
                rhythm = (data or {}).get("contact_rhythm") or {}
                received = timestamp(rhythm.get("last_received_at"))
                unanswered = [timestamp(row["at"]) for row in rows
                              if row.get("source") in PACED_SOURCES
                              and timestamp(row["at"]) > received
                              and now - timestamp(row["at"]) < 12 * 3600]
                rounds, previous = 0, 0
                for at in unanswered:
                    if not previous or at - previous > 120:
                        rounds += 1
                    previous = at
                if rounds:
                    interval = max(interval, (120 if rounds == 1 else 360) * 60)
                    reason = "先前的主动分享尚无回应，等一等再开启新话题"
            remaining = max(0, timestamp(rows[-1]["at"]) + interval - now)
        else:
            remaining = 0
        episode_remaining = self.episode_wait(target, selected, states, now)
        if episode_remaining > remaining:
            remaining = episode_remaining
            reason = "同一经历刚分享过，积累有意义的进展后再说"
        return {"ready": remaining <= 0, "retry_after": math.ceil(remaining),
                "reason": reason if remaining > 0 else ""}

    async def filter_materials(self, target, materials, *, now=None):
        now = time.time() if now is None else now
        states = await self.plugin.db.get_share_state(STATE_KEY, {})
        merged = {}
        for row in materials:
            if not self.episode_wait(target, episodes([row]), states, now):
                # 提取顺序中完成事实位于进行事实之后；同次选题只保留一个版本。
                merged[row.get("episode_id") or row["id"]] = row
        return list(merged.values())

    async def record(self, target, job, *, now=None):
        """在平台请求前持久登记，失败或结果未知也不能立刻另起一条。"""
        source = (job.get("params") or {}).get("history_source")
        if source not in PACED_SOURCES:
            return
        now = time.time() if now is None else now
        key = digest(target)
        states = await self.plugin.db.get_share_state(STATE_KEY, {})
        rows = [row for row in (states.get(key) or {}).get("records", [])
                if now - timestamp(row.get("at")) < 86400 and row.get("job") != job["id"]]
        rows.append({"job": job["id"], "at": now, "source": source,
                     "episodes": list(job.get("pacing_episodes") or [])})
        await self.plugin.db.merge_cache_entries(
            "share", STATE_KEY,
            {key: {"public": is_public_share_target(target), "records": rows[-48:]}},
            max_items=256,
        )

    async def check_job(self, job):
        params = job.get("params") or {}
        target = params.get("uid") or params.get("target_umo") or "qzone_broadcast"
        return await self.check(target, selected=job.get("pacing_episodes") or [],
                                source=params.get("history_source"))

    async def coordinate(self, target, *, owner="", action="check", rhythm=None, selected=()):
        """生活插件的公开协调入口；只接收会话、时间和不透明事实编号。"""
        if action not in {"check", "submit"} or not isinstance(target, str) or not target:
            raise ValueError("无效的主动联系协调请求")
        if action == "submit" and (not isinstance(owner, str) or not owner or len(owner) > 200):
            raise ValueError("主动提交需要稳定任务编号")
        if not isinstance(selected, (list, tuple)) or any(
                not isinstance(identity, str) or not identity or len(identity) > 200 for identity in selected):
            raise ValueError("分享事实编号格式无效")
        selected = list(dict.fromkeys(selected))[:16]
        if rhythm is not None and not isinstance(rhythm, dict):
            raise ValueError("联系节奏格式无效")
        data = {"contact_rhythm": {"last_received_at": timestamp((rhythm or {}).get("last_received_at"))}}
        if action == "check":
            return await self.check(target, data=data, selected=selected)
        async with self.lock:
            gate = await self.check(target, data=data, selected=selected)
            if gate["ready"] and action == "submit":
                await self.record(target, {"id": owner, "params": {"history_source": SOURCE_LIFE},
                                           "pacing_episodes": list(selected)[:16]})
            return gate

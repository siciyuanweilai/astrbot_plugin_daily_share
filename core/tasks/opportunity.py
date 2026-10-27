"""按事实身份提取新经历；时间流逝和身体数值漂移不产生分享任务。"""

from __future__ import annotations

import hashlib
import json
import math
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

SHANGHAI = timezone(timedelta(hours=8))
current_opportunity = ContextVar("daily_share_opportunity", default=None)


def compact(value, limit=240):
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()[:24]


def recent(value, now):
    try:
        at = datetime.fromisoformat(value)
        at = at.replace(tzinfo=SHANGHAI) if at.tzinfo is None else at
        return 0 <= (now - at).total_seconds() <= 6 * 3600
    except (ValueError, TypeError):
        return False


def share_material(data: dict, now: datetime) -> list[dict]:
    facts = data.get("current_facts") or {}
    if facts.get("valid") is not True:
        return []
    result = {}

    def add(kind, identity, row):
        fields = {
            key: compact(value, 400 if key == "evidence" else 240)
            for key, value in row.items()
            if isinstance(value, str) and value.strip()
        }
        fields.update(
            {
                key: value
                for key, value in row.items()
                if key in {"quantity", "artifact_version"}
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and value >= 0
            }
        )
        if not fields:
            return
        key = digest([kind, identity])
        result[key] = {"id": key, "kind": kind, **fields}

    action = facts.get("current_action") or {}
    if (
        action.get("status") == "running"
        and action.get("observation_state") == "observed"
        and action.get("action_id")
        and recent(action.get("observed_at") or action.get("started_at"), now)
    ):
        add(
            "activity",
            action["action_id"],
            {
                "activity": action.get("activity"),
                "state": "running",
            },
        )
    for row in data.get("timeline") or []:
        if not isinstance(row, dict):
            continue
        if (
            row.get("execution_state") == "completed"
            and row.get("execution_evidence")
            and recent(row.get("execution_updated_at"), now)
        ):
            add(
                "completed_activity",
                [facts.get("date"), row.get("time"), row.get("activity")],
                {
                    "activity": row.get("activity"),
                    "state": "completed",
                    "evidence": row.get("execution_evidence"),
                },
            )
    continuity = data.get("continuity") or {}
    for kind in ("activities", "objects"):
        for row in continuity.get(kind) or []:
            if (
                not isinstance(row, dict)
                or row.get("state")
                not in {
                    "active",
                    "completed",
                    "ready",
                    "available",
                    "created",
                }
                or not recent(row.get("at"), now)
            ):
                continue
            selected = {
                key: row.get(key)
                for key in (
                    "title",
                    "state",
                    "detail",
                    "progress",
                    "provenance",
                    "owner",
                    "quantity",
                    "unit",
                    "artifact_version",
                    "delivery",
                    "available_at",
                )
            }
            add(
                kind,
                [row.get("title"), row.get("state"), row.get("artifact_version")],
                selected,
            )
    for row in data.get("bili_experiences") or []:
        if (
            not isinstance(row, dict)
            or not row.get("evidence")
            or not row.get("impression")
            or row.get("already_shared_here")
            or row.get("delivery_pending")
            or row.get("status") == "abandoned"
            or not recent(row.get("updated_at"), now)
        ):
            continue
        selected = {
            key: row.get(key)
            for key in (
                "title",
                "url",
                "status",
                "impression",
                "share_reason",
            )
        }
        # 视频依据可能为结构化片段；限制单条材料大小，保留处理范围。
        selected["evidence"] = (
            json.dumps(row["evidence"], ensure_ascii=False)
            if not isinstance(row["evidence"], str)
            else row["evidence"]
        )
        add("bilibili", [row.get("bvid"), row.get("page")], selected)
    return list(result.values())[-16:]


def opportunity_prompt(target):
    value = current_opportunity.get()
    if not value or value["target"] != target:
        return ""
    return "\n【本次自主选中的分享材料】\n" + json.dumps(
        value["materials"], ensure_ascii=False
    )

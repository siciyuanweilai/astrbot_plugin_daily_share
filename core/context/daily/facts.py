"""从生活插件公开快照选取当前身体事实，不透传原始依据。"""

import json
import math


def body_prompt(data: dict) -> str:
    facts = data.get("current_facts")
    facts = facts if isinstance(facts, dict) else {}
    if facts.get("valid") is False:
        return ""
    material = {}
    body = facts.get("body")
    if isinstance(body, dict):
        for key in (
            "energy",
            "sleep_pressure",
            "fatigue",
            "hunger",
            "thirst",
            "social_battery",
            "discomfort",
        ):
            value = body.get(key)
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and 0 <= value <= 100
            ):
                material[key] = value
        gap = body.get("uncertain_minutes")
        if (
            isinstance(gap, (int, float))
            and not isinstance(gap, bool)
            and math.isfinite(gap)
            and gap >= 0
        ):
            material["uncertain_minutes"] = gap
        updated = body.get("updated_at")
        if isinstance(updated, str) and updated.strip():
            material["updated_at"] = " ".join(updated.split())[:40]
    state = data.get("state")
    rhythm = state.get("physiological_rhythm") if isinstance(state, dict) else None
    condition = rhythm.get("body_condition") if isinstance(rhythm, dict) else None
    if isinstance(condition, dict):
        selected = {
            key: " ".join(value.split())[:limit]
            for key, limit in (
                ("label", 60),
                ("kind", 24),
                ("phase", 24),
                ("started_at", 40),
                ("expires_at", 40),
            )
            if isinstance(value := condition.get(key), str) and value.strip()
        }
        if isinstance(condition.get("burden_present"), bool):
            selected["burden_present"] = condition["burden_present"]
        intensity = condition.get("intensity")
        if (
            isinstance(intensity, (int, float))
            and not isinstance(intensity, bool)
            and math.isfinite(intensity)
            and 0 <= intensity <= 100
        ):
            selected["intensity"] = (
                0 if selected.get("burden_present") is False else intensity
            )
        if selected:
            material["condition"] = selected
    if not material:
        return ""
    return (
        "【当前身体状态】\n"
        + json.dumps(material, ensure_ascii=False, sort_keys=True)
        + "\n仅作当前感受参考，不逐项播报；onset/ongoing=仍有不适、recovering=恢复中、resolved=已确认缓解。"
        "到复核时间或休息一次不等于痊愈，建议不等于已执行；未观测时段不补造经历，不据数值诊断。"
    )

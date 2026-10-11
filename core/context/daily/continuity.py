"""消费生活插件的有界分享投影，不直接读取生活数据库。"""

import json


def continuity_prompt(data: dict, *, max_items: int = 4, max_chars: int = 400) -> str:
    value = data.get("continuity")
    if not isinstance(value, dict) or value.get("version") != 1:
        return ""
    material = {}
    fields = {
        "title",
        "state",
        "at",
        "content",
        "detail",
        "progress",
        "provenance",
        "location",
        "label",
        "last_practiced_at",
        "delivery",
        "delivered_at",
    }
    for key, label in (
        ("corrections", "已确认纠正"),
        ("activities", "共同活动"),
        ("objects", "已登记物品作品"),
        ("interests", "自身兴趣"),
        ("goals", "自身目标"),
    ):
        rows = value.get(key)
        if not isinstance(rows, list):
            continue
        selected = []
        for row in rows[:max_items]:
            if not isinstance(row, dict):
                continue
            item = {
                k: v[:max_chars]
                for k, v in row.items()
                if k in fields and isinstance(v, str) and v
            }
            if key == "goals" and isinstance(row.get("steps"), list):
                item["steps"] = [
                    {
                        k: v[: min(160, max_chars)]
                        for k, v in step.items()
                        if k in {"title", "state"} and isinstance(v, str)
                    }
                    for step in row["steps"][:max_items]
                    if isinstance(step, dict)
                ]
            if item:
                selected.append(item)
        if selected:
            material[label] = selected
    if not material:
        return ""
    return (
        "【已确认生活连续性】\n"
        "纠正优先于旧摘要；共同活动 preparing=准备、active=进行、paused=暂停、completed=结束、cancelled=取消。"
        "兴趣 paused=暂缓、retired=已放下，不当作当前爱好强推；目标 pending/needs_practice=仍需练习、awaiting_review=等待验收，不能写成掌握或完成。"
        "物品已生成不等于已发送，计划不等于经历；只采用与本次分享有关的信息，不逐项播报。\n"
        + json.dumps(material, ensure_ascii=False, sort_keys=True)
    )


def timing_prompt(data: dict) -> str:
    value = data.get("conversation_timing")
    if not isinstance(value, dict) or value.get("version") != 1:
        return ""
    previous = str(value.get("last_sent_at") or "")[:40]
    now = str(value.get("now") or "")[:40]
    return (
        f"【会话时间事实】当前：{now}；本会话上次确认发送：{previous or '未知'}。"
        "据完整日期判断跨日与久别，不沿用历史场景作为当下；不固定播报间隔。"
        + (
            "群聊发送间隔不代表当前某位群友的离开时间。"
            if value.get("scope_kind") == "group"
            else ""
        )
    )


def topic_continuity(context: str) -> str:
    """从当前任务已有的投影选兴趣和目标，不额外读取可能更新的快照。"""
    try:
        group = json.loads(context)
        if isinstance(group, dict):
            context = str(group.get("生活连续性") or "")
    except (ValueError, TypeError):
        pass
    marker = "【已确认生活连续性】"
    if not isinstance(context, str) or marker not in context:
        return ""
    section = context.split(marker, 1)[1]
    start = section.find("\n{")
    if start < 0:
        return ""
    try:
        data, _ = json.JSONDecoder().raw_decode(section[start:].lstrip())
    except ValueError:
        return ""
    if not isinstance(data, dict):
        return ""
    return continuity_prompt(
        {
            "continuity": {
                "version": 1,
                "interests": data.get("自身兴趣", []),
                "goals": data.get("自身目标", []),
            }
        }
    )

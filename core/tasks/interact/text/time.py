from __future__ import annotations

import re
from datetime import datetime
from typing import Any


def _qzone_period_label(hour: int) -> str:
    if 5 <= hour < 8:
        return "清晨"
    if 8 <= hour < 11:
        return "上午"
    if 11 <= hour < 14:
        return "中午"
    if 14 <= hour < 18:
        return "下午"
    if 18 <= hour < 20:
        return "傍晚"
    if 20 <= hour < 24:
        return "晚上"
    return "深夜"


def _format_qzone_local_datetime(timestamp: Any = None) -> str:
    try:
        if timestamp is None:
            dt = datetime.now().astimezone()
        else:
            ts = int(timestamp or 0)
            if ts <= 0:
                return "未知"
            dt = datetime.fromtimestamp(ts).astimezone()
    except Exception:
        if timestamp is not None:
            return "未知"
        dt = datetime.now()
    return f"{dt.strftime('%Y年%m月%d日 %H:%M')}（{_qzone_period_label(dt.hour)}）"


def _qzone_auto_interaction_time_context() -> str:
    return f"当前本地时间：{_format_qzone_local_datetime()}"


def _compact_qzone_auto_life_context(value: Any, *, max_len: int = 900) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > max_len:
        text = f"{text[:max_len].rstrip()}..."
    return text

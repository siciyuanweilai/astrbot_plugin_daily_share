from __future__ import annotations

from datetime import datetime
from html import unescape
from typing import Any


def _safe_int(value: Any) -> int:
    text = str(value or "").strip()
    if text.lower().startswith("o"):
        text = text[1:]
    if not text:
        return 0
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return 0


def _optional_int(value: Any) -> int | None:
    number = _safe_int(value)
    return number if number else None


def _first_text(*values: Any) -> str:
    for value in values:
        text = unescape(str(value or "")).strip()
        if text:
            return text
    return ""


def _avatar_url(value: Any, uin: int) -> str:
    url = _first_text(value)
    if url.startswith("//"):
        url = f"https:{url}"
    if url.startswith(("http://", "https://", "data:image/")):
        return url.replace("/30?", "/100?").replace("/30&", "/100&")
    return f"https://q.qlogo.cn/headimg_dl?dst_uin={uin}&spec=100" if uin else ""


def _payload_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else {}
    return data if isinstance(data, dict) else {}


def _first_list(*values: Any) -> list[dict[str, Any]]:
    for value in values:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _relation_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = _payload_data(payload)
    nested = data.get("data") if isinstance(data.get("data"), dict) else {}
    return _first_list(
        data.get("items_list"),
        data.get("items"),
        data.get("list"),
        data.get("friendlist"),
        nested.get("items_list"),
        nested.get("items"),
        payload.get("items_list") if isinstance(payload, dict) else None,
        payload.get("items") if isinstance(payload, dict) else None,
    )


def _time_source(item: dict[str, Any]) -> Any:
    for key in (
        "time_label",
        "date_label",
        "last_time",
        "lasttime",
        "lastVisitTime",
        "last_visit_time",
        "visit_time",
        "abstime",
        "timestamp",
        "time",
        "date",
    ):
        value = item.get(key)
        if value not in (None, ""):
            return value
    return ""


def _format_time_label(value: Any) -> str:
    text = _first_text(value)
    if not text:
        return ""
    if not text.replace(".", "", 1).isdigit():
        return text

    number = _safe_int(text)
    if not number:
        return ""
    if number > 10_000_000_000:
        number //= 1000
    if number < 100_000_000:
        return text

    try:
        dt = datetime.fromtimestamp(number)
    except (OSError, OverflowError, ValueError):
        return text

    now = datetime.now()
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    if dt.year == now.year:
        return f"{dt.month}月{dt.day}日"
    return f"{dt.year}-{dt.month}-{dt.day}"


def parse_qzone_relations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, item in enumerate(_relation_items(payload), start=1):
        uin = _safe_int(
            item.get("uin")
            or item.get("fuin")
            or item.get("friend_uin")
            or item.get("qq")
            or item.get("qqnum")
            or item.get("opuin")
        )
        if not uin or uin in seen:
            continue
        seen.add(uin)
        name = _first_text(
            item.get("name"),
            item.get("nick"),
            item.get("nickname"),
            item.get("uinname"),
            item.get("qqnick"),
            item.get("remark"),
            item.get("markname"),
            uin,
        )
        remark = _first_text(item.get("remark"), item.get("markname"), item.get("remarkname"))
        score = _optional_int(
            item.get("score")
            or item.get("intimacy")
            or item.get("degree")
            or item.get("value")
            or item.get("rank_score")
        )
        result.append(
            {
                "uin": uin,
                "name": name,
                "remark": remark,
                "avatar": _avatar_url(
                    item.get("img") or item.get("avatar") or item.get("headurl") or item.get("portrait"),
                    uin,
                ),
                "score": score,
                "time_label": _format_time_label(_time_source(item)),
                "rank": index,
                "home": f"https://user.qzone.qq.com/{uin}",
            }
        )
    return result


def parse_qzone_visit_stats(payload: dict[str, Any]) -> dict[str, Any]:
    data = _payload_data(payload)
    mods = _first_list(data.get("modvisitcount"), payload.get("modvisitcount") if isinstance(payload, dict) else None)
    selected = max(
        mods,
        key=lambda item: _safe_int(item.get("totalcount") or item.get("total")),
        default={},
    )
    total = _safe_int(selected.get("totalcount") or selected.get("total"))
    today = _safe_int(selected.get("todaycount") or selected.get("today"))
    items = data.get("items") if isinstance(data.get("items"), list) else []
    return {
        "available": bool(mods or total or today or items),
        "today_views": today,
        "total_views": total,
        "visitor_count": _safe_int(data.get("count")) or len(items),
    }

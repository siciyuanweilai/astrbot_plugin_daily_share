from __future__ import annotations

from datetime import datetime
from html import unescape
import re
from typing import Any

from .models import QzonePost
from .parse import clean_qzone_text, parse_recent_feed_list


def _safe_int(value: Any) -> int:
    text = str(value or "").strip()
    if text.lower().startswith("o"):
        text = text[1:]
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return 0


def _first_text(*values: Any) -> str:
    for value in values:
        text = clean_qzone_text(value)
        if text:
            return text
    return ""


def _clean_url(value: Any) -> str:
    url = unescape(str(value or "").strip())
    if url.startswith("//"):
        url = f"https:{url}"
    return url if url.startswith(("http://", "https://")) else ""


def _first_url(*values: Any) -> str:
    for value in values:
        url = _clean_url(value)
        if url:
            return url
    return ""


def _time_label(value: Any) -> str:
    number = _safe_int(value)
    if not number:
        return ""
    if number > 10_000_000_000:
        number //= 1000
    try:
        dt = datetime.fromtimestamp(number)
    except (OSError, OverflowError, ValueError):
        return ""
    now = datetime.now()
    if dt.date() == now.date():
        return dt.strftime("今天 %H:%M")
    if dt.year == now.year:
        return dt.strftime("%m-%d %H:%M")
    return dt.strftime("%Y-%m-%d")


def _payload_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else {}
    return data if isinstance(data, dict) else {}


def _feed_payload_items(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    data = _payload_data(payload)
    items: list[dict[str, Any]] = []
    for key in keys or ("data",):
        value = data.get(key)
        if isinstance(value, list):
            items.extend(item for item in value if isinstance(item, dict))
    return items


def _posts_from_feed_items(items: list[dict[str, Any]]) -> list[QzonePost]:
    return parse_recent_feed_list({"data": {"data": items}})


def parse_about_me(payload: dict[str, Any]) -> dict[str, Any]:
    data = _payload_data(payload)
    main = data.get("main") if isinstance(data.get("main"), dict) else {}
    posts = _posts_from_feed_items(_feed_payload_items(payload, "data"))
    return {
        "items": posts,
        "has_more": bool(main.get("hasMoreFeeds")) and bool(posts),
        "next_offset": _safe_int(main.get("offset")) or len(posts),
        "message": clean_qzone_text(main.get("host_more") or main.get("friend_more")),
    }


def parse_last_year(payload: dict[str, Any]) -> dict[str, Any]:
    data = _payload_data(payload)
    main = data.get("main") if isinstance(data.get("main"), dict) else {}
    posts = _posts_from_feed_items(
        _feed_payload_items(
            payload,
            "data",
            "host_data",
            "friend_data",
            "about_data",
            "firstpage_data",
        )
    )
    return {
        "items": posts,
        "has_more": bool(main.get("hasMoreFeeds_0") or main.get("hasMoreFeeds_1")) and bool(posts),
        "message": clean_qzone_text(main.get("friend_more") or main.get("host_more")),
    }


def _fav_image(item: dict[str, Any]) -> str:
    for key in ("img_list", "origin_img_list", "images"):
        value = item.get(key)
        if isinstance(value, list):
            for image in value:
                if isinstance(image, dict):
                    url = _first_url(image.get("url"), image.get("origin_url"), image.get("pic_url"))
                else:
                    url = _first_url(image)
                if url:
                    return url
    return _first_url(item.get("img"), item.get("pic"), item.get("thumb"))


def _fav_link(item: dict[str, Any]) -> str:
    shuoshuo = item.get("shuoshuo_info") if isinstance(item.get("shuoshuo_info"), dict) else {}
    owner = _safe_int(shuoshuo.get("owner_uin") or item.get("owner_uin") or item.get("uin"))
    tid = str(shuoshuo.get("tid") or item.get("tid") or item.get("id") or "").strip()
    if owner and tid:
        return f"https://user.qzone.qq.com/{owner}/mood/{tid}"
    return _first_url(item.get("url"), item.get("link"), item.get("source_url"))


def parse_favorites(payload: dict[str, Any]) -> dict[str, Any]:
    data = _payload_data(payload) or payload
    raw_items = data.get("fav_list") if isinstance(data, dict) else []
    items = []
    for index, item in enumerate(raw_items if isinstance(raw_items, list) else []):
        if not isinstance(item, dict):
            continue
        shuoshuo = item.get("shuoshuo_info") if isinstance(item.get("shuoshuo_info"), dict) else {}
        title = _first_text(
            item.get("title"),
            item.get("abstract"),
            item.get("desp"),
            shuoshuo.get("content"),
            item.get("summary"),
        )
        items.append(
            {
                "id": str(item.get("id") or item.get("fid") or index),
                "type": str(item.get("type") or ""),
                "title": title or "收藏内容",
                "summary": _first_text(item.get("abstract"), item.get("desp"), shuoshuo.get("content")),
                "image": _fav_image(item),
                "url": _fav_link(item),
                "time_label": _time_label(item.get("create_time") or item.get("time")),
                "author": _first_text(
                    shuoshuo.get("owner_name"),
                    shuoshuo.get("owner_nick"),
                    item.get("nick"),
                    item.get("author"),
                ),
            }
        )
    return {
        "items": items,
        "total": _safe_int(data.get("total_num") if isinstance(data, dict) else 0) or len(items),
        "has_more": len(items) > 0 and (_safe_int(data.get("total_num")) > len(items) if isinstance(data, dict) else False),
    }


def _message_author(item: dict[str, Any]) -> dict[str, Any]:
    for key in ("userinfo", "user", "owner", "authorInfo", "author"):
        value = item.get(key)
        if isinstance(value, dict):
            return value
    return {}


def parse_message_board(payload: dict[str, Any], *, start: int = 0) -> dict[str, Any]:
    data = _payload_data(payload)
    raw_items = data.get("commentList") if isinstance(data.get("commentList"), list) else []
    total = _safe_int(data.get("total"))
    items = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            continue
        user = _message_author(item)
        uin = _safe_int(item.get("uin") or item.get("posterUin") or user.get("uin") or user.get("user_id"))
        avatar = _first_url(item.get("avatar"), user.get("avatar"), user.get("headurl"))
        if not avatar and uin:
            avatar = f"https://q.qlogo.cn/headimg_dl?dst_uin={uin}&spec=100"
        content = _first_text(item.get("content"), item.get("htmlContent"), item.get("ubbContent"), item.get("message"))
        floor = total - start - index if total else 0
        items.append(
            {
                "id": str(item.get("id") or item.get("commentid") or item.get("tid") or f"{start}-{index}"),
                "content": content,
                "time_label": _time_label(item.get("create_time") or item.get("pubtime") or item.get("time")),
                "floor": floor if floor > 0 else 0,
                "author": {
                    "uin": uin,
                    "nickname": _first_text(
                        user.get("nickname"),
                        user.get("nick"),
                        user.get("name"),
                        item.get("nickname"),
                        item.get("name"),
                    ) or (str(uin) if uin else "QQ 用户"),
                    "avatar": avatar,
                },
            }
        )
    return {
        "items": items,
        "total": total,
        "has_more": start + len(items) < total if total else False,
        "message": clean_qzone_text(payload.get("message")),
    }


def compact_html_text(value: Any, *, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", clean_qzone_text(value)).strip()
    return f"{text[:limit]}..." if len(text) > limit else text

from __future__ import annotations

import re
from typing import Any

from .decoder import (
    _decode_js_escaped_text,
    _html_first_attr,
    _mapping_first,
    _mapping_first_from_paths,
    _safe_int,
    _tag_attrs,
    _walk_mappings,
    clean_qzone_text,
)


FEED_PRIMARY_ID_KEYS = ("sourceFkey", "fkey")
FEED_STRUCTURAL_ID_KEYS = ("fid", "tid", "cellid", "ugcrightkey", "ugckey", "key")
FEED_ID_PATHS = (("id", "cellid"), ("cell_id", "cellid"), ("cellId", "cellid"))
FEED_HTML_ID_ATTRS = ("data-fkey", "data-fid", "fid", "data-tid", "tid", "data-cellid")
FEED_UIN_KEYS = ("uin", "opuin", "owneruin", "ownerUin", "fuin", "hostuin", "hostUin")
FEED_UIN_PATHS = (
    ("userinfo", "uin"),
    ("cell_userinfo", "uin"),
    ("cellUserInfo", "uin"),
    ("user", "uin"),
    ("userinfo", "user", "uin"),
)
FEED_HTML_UIN_ATTRS = ("data-uin", "data-opuin", "uin", "opuin")
FEED_COMMON_KEYS = ("common", "comm", "cell_comm", "cellComm")
FEED_OPERATION_KEYS = ("operation", "cell_operation")
FEED_LIKE_KEYS = ("like", "cell_like")
FEED_CONTAINER_KEYS = ("data", "host_data", "friend_data", "firstpage_data", "about_data", "items", "feeds", "list")


def _first_feed_data_attrs(raw_html: str) -> dict[str, str]:
    match = re.search(
        r"<[^>]*\bname\s*=\s*([\"'])feed_data\1[^>]*>",
        str(raw_html or ""),
        re.I | re.S,
    )
    return _tag_attrs(match.group(0)) if match else {}


def _feed_data_attr(attrs: dict[str, str], name: str) -> str:
    return _decode_js_escaped_text(attrs.get(f"data-{name}") or attrs.get(name) or "").strip()


def _feed_block_meta(raw_html: str) -> dict[str, str]:
    match = re.search(
        r'\bid\s*=\s*(["\'])feed_(\d+)_(\d+)_(\d+)_(\d+)_\d+_\d+\1',
        str(raw_html or ""),
        re.I,
    )
    if not match:
        return {}
    return {
        "opuin": match.group(2),
        "appid": match.group(3),
        "typeid": match.group(4),
        "abstime": match.group(5),
    }


def _fid_from_ugc_key(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.fullmatch(r"\d+_\d+_([^_]+)_?", text)
    return match.group(1) if match else text


def _recent_item_fid(item: dict[str, Any], common: dict[str, Any], raw_html: str) -> str:
    feed_attrs = _first_feed_data_attrs(raw_html)
    candidates = (
        _mapping_first(item, FEED_PRIMARY_ID_KEYS),
        common.get("fkey"),
        _feed_data_attr(feed_attrs, "fkey"),
        _mapping_first(item, FEED_STRUCTURAL_ID_KEYS),
        _mapping_first_from_paths(item, FEED_ID_PATHS),
        common.get("ugcrightkey"),
        common.get("ugckey"),
        _html_first_attr(raw_html, FEED_HTML_ID_ATTRS),
    )
    for candidate in candidates:
        fid = _fid_from_ugc_key(candidate)
        if fid:
            return fid
    return ""


def _recent_item_uin(item: dict[str, Any], raw_html: str, common: dict[str, Any] | None = None) -> int:
    common = common or {}
    candidates = (
        _mapping_first(item, FEED_UIN_KEYS),
        _mapping_first(common, FEED_UIN_KEYS),
        _mapping_first_from_paths(item, FEED_UIN_PATHS),
        _html_first_attr(raw_html, FEED_HTML_UIN_ATTRS),
    )
    for candidate in candidates:
        uin = _safe_int(candidate)
        if uin:
            return uin
    return 0


def _strip_feed_author_prefix(text: str, author: str = "") -> str:
    value = clean_qzone_text(text)
    author = str(author or "").strip()
    for sep in ("：", ":"):
        index = value.find(sep)
        if index <= 0:
            continue
        prefix = value[:index].strip()
        if not prefix or len(prefix) > 40:
            continue
        if not author or prefix == author or "回复" in prefix or re.search(r"[\u4e00-\u9fffA-Za-z0-9_ -]+$", prefix):
            return value[index + 1 :].strip()
    return value


def _html_text_by_class(raw_html: str, class_name: str) -> str:
    pattern = re.compile(
        rf'<(?P<tag>div|p|span|h[1-6])\b[^>]*class=(["\'])[^"\']*\b{re.escape(class_name)}\b[^"\']*\2[^>]*>'
        rf'(?P<body>.*?)</(?P=tag)>',
        re.I | re.S,
    )
    for match in pattern.finditer(raw_html or ""):
        text = clean_qzone_text(match.group("body"))
        if text:
            return text
    return ""


def _recent_item_name(item: dict[str, Any], raw_html: str, uin: int) -> str:
    for value in (item.get("name"), item.get("nickname"), item.get("uinname")):
        text = clean_qzone_text(value)
        if text:
            return text

    source = str(raw_html or "")
    if uin:
        match = re.search(
            rf'<a\b[^>]*(?:link|href)=["\'][^"\']*nameCard_{uin}\b[^"\']*["\'][^>]*>(.*?)</a>',
            source,
            re.I | re.S,
        )
        if match:
            text = clean_qzone_text(match.group(1))
            if text:
                return text

    f_nick = re.search(
        r'<div\b[^>]*class=(["\'])[^"\']*\bf-nick\b[^"\']*\1[^>]*>(.*?)</div>',
        source,
        re.I | re.S,
    )
    if f_nick:
        text = clean_qzone_text(f_nick.group(2))
        if text:
            return text

    for match in re.finditer(
        r'<a\b[^>]*class=(["\'])[^"\']*\bf-name\b[^"\']*\1[^>]*>(.*?)</a>',
        source,
        re.I | re.S,
    ):
        text = clean_qzone_text(match.group(2))
        if text and "播放" not in text and "点赞" not in text:
            return text
    return str(uin or "")


def _recent_item_text(raw_html: str, author: str = "") -> str:
    for class_name in ("f-info", "txt-box-title", "txt-box", "content-box", "qz_summary"):
        text = _html_text_by_class(raw_html, class_name)
        if text:
            return _strip_feed_author_prefix(text, author)
    return _strip_feed_author_prefix(raw_html, author)


def _qzone_unikey(appid: int, uin: int, fid: str) -> str:
    if not uin or not fid:
        return ""
    if int(appid or 311) == 311:
        return f"https://user.qzone.qq.com/{uin}/mood/{fid}"
    return f"https://user.qzone.qq.com/{uin}/app/{appid}/{fid}"


def _recent_payload_array_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    items: list[dict[str, Any]] = []
    for container in (data, payload):
        if not isinstance(container, dict):
            continue
        for key in FEED_CONTAINER_KEYS:
            value = container.get(key)
            if isinstance(value, list):
                items.extend(item for item in value if isinstance(item, dict))
    return items


def _feed_html_blocks(markup: Any) -> list[str]:
    source = _decode_js_escaped_text(markup)
    if "feed_data" not in source:
        return []
    matches = list(
        re.finditer(
            r"<[^>]*\bname\s*=\s*([\"'])feed_data\1[^>]*>",
            source,
            re.I | re.S,
        )
    )
    blocks: list[str] = []
    for index, match in enumerate(matches):
        start = source.rfind("<li", 0, match.start())
        if start < 0:
            start = source.rfind("<div", 0, match.start())
        if start < 0:
            start = max(0, match.start() - 4000)
        end = matches[index + 1].start() if index + 1 < len(matches) else min(len(source), match.start() + 12000)
        block = source[start:end].strip()
        if block:
            blocks.append(block)
    return blocks


def _recent_payload_html_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for mapping in _walk_mappings(payload):
        for value in mapping.values():
            if not isinstance(value, str):
                continue
            if "feed_data" not in value and "feed_data" not in _decode_js_escaped_text(value[:2000]):
                continue
            for block in _feed_html_blocks(value):
                attrs = _first_feed_data_attrs(block)
                key = "|".join(
                    item
                    for item in (
                        _feed_data_attr(attrs, "fkey"),
                        _feed_data_attr(attrs, "tid"),
                        _feed_data_attr(attrs, "uin"),
                    )
                    if item
                )
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                items.append({"html": block})
    return items


def _recent_payload_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = _recent_payload_array_items(payload)
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items + _recent_payload_html_items(payload):
        raw_html = str(item.get("html") or "")
        attrs = _first_feed_data_attrs(raw_html)
        key = "|".join(
            str(part or "")
            for part in (
                item.get("fid") or item.get("tid") or _feed_data_attr(attrs, "fkey") or _feed_data_attr(attrs, "tid"),
                item.get("uin") or _feed_data_attr(attrs, "uin"),
            )
        )
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        result.append(item)
    return result

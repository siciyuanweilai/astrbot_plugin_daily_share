from __future__ import annotations

import re
from typing import Any

from ..models import QzonePost
from .decoder import (
    _decode_js_escaped_text,
    _first_json_mapping,
    _html_attr,
    _html_first_attr,
    _mapping_first,
    _safe_int,
    clean_qzone_text,
    has_qzone_expand_marker,
)
from .homeparse import parse_home_feed_list
from .remarks import _feed_comment_items, parse_comments
from .asset import (
    _avatar_url,
    _extract_attr_values,
    _extract_payload_image_sources,
    _extract_video_sources,
    _first_image_url,
)
from .latest import (
    FEED_COMMON_KEYS,
    FEED_LIKE_KEYS,
    FEED_OPERATION_KEYS,
    _feed_block_meta,
    _feed_data_attr,
    _first_feed_data_attrs,
    _qzone_unikey,
    _recent_item_fid,
    _recent_item_name,
    _recent_item_text,
    _recent_item_uin,
    _recent_payload_items,
)


def _qzone_liked(*sources: dict[str, Any]) -> bool:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in ("isliked", "ismylike", "isLike", "islike", "liked"):
            if key in source:
                value = source.get(key)
                return value is True or str(value).strip().lower() in {
                    "1",
                    "true",
                    "yes",
                }
    return False


def _qzone_conlist_text(value: Any) -> str:
    items = value if isinstance(value, list) else []
    parts = []
    for item in items:
        if isinstance(item, dict):
            parts.append(str(item.get("con") or ""))
        else:
            parts.append(str(item or ""))
    return clean_qzone_text("".join(parts))


def _qzone_mapping_text(mapping: dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = clean_qzone_text(mapping.get(key))
        if text:
            return text
    return _qzone_conlist_text(mapping.get("conlist"))


def _qzone_repost_mapping(item: dict[str, Any]) -> dict[str, Any]:
    rtitem = item.get("rtitem")
    return rtitem if isinstance(rtitem, dict) else {}


def _qzone_repost_text(item: dict[str, Any]) -> str:
    rt_con = item.get("rt_con")
    if isinstance(rt_con, dict):
        text = _qzone_mapping_text(rt_con, "content", "con")
        if text:
            return text
    else:
        text = clean_qzone_text(rt_con)
        if text:
            return text

    rtitem = _qzone_repost_mapping(item)
    return _qzone_mapping_text(
        rtitem, "rt_con", "rt_originalcon", "content", "originalcontent"
    )


def _qzone_repost_image_urls(
    item: dict[str, Any], rtitem: dict[str, Any] | None = None
) -> list[str]:
    rtitem = rtitem or _qzone_repost_mapping(item)
    rt_con = item.get("rt_con") if isinstance(item.get("rt_con"), dict) else {}
    rt_fields = {
        key: value
        for key, value in item.items()
        if str(key or "").lower().startswith("rt_")
    }
    return _extract_payload_image_sources(rt_con, rtitem, rt_fields)


def _qzone_repost_pic_reference_text(pic: dict[str, Any]) -> str:
    return " ".join(
        str(pic.get(key) or "")
        for key in ("unilikekey", "unlikekey", "source_unilikekey", "source_unikey")
    )


def _qzone_pic_belongs_to_repost(
    pic: dict[str, Any], item: dict[str, Any], rtitem: dict[str, Any]
) -> bool:
    rt_tid = str(item.get("rt_tid") or rtitem.get("rt_tid") or "").strip()
    rt_uin = str(
        item.get("rt_uin") or rtitem.get("rt_uin") or rtitem.get("rt_wc_uin") or ""
    ).strip()
    if not rt_tid and not rt_uin:
        return False

    ref_text = _qzone_repost_pic_reference_text(pic)
    if not ref_text:
        return False
    return bool(
        (rt_tid and rt_tid in ref_text) or (rt_uin and f"/{rt_uin}/mood/" in ref_text)
    )


def _qzone_feed_pic_image_urls(
    item: dict[str, Any], rtitem: dict[str, Any]
) -> tuple[list[str], list[str]]:
    images: list[str] = []
    rt_images: list[str] = []
    for pic in item.get("pic") or []:
        if not isinstance(pic, dict):
            continue
        url = _first_image_url(pic)
        if not url:
            continue
        target = (
            rt_images if _qzone_pic_belongs_to_repost(pic, item, rtitem) else images
        )
        target.append(url)
    return images, rt_images


def parse_feed_item(item: dict[str, Any]) -> QzonePost | None:
    if not isinstance(item, dict):
        return None
    tid = str(_mapping_first(item, ("tid", "key")) or "")
    uin = _safe_int(_mapping_first(item, ("uin", "hostuin")))
    if not tid or not uin:
        return None

    rtitem = _qzone_repost_mapping(item)
    images, inline_rt_images = _qzone_feed_pic_image_urls(item, rtitem)
    videos: list[str] = []
    for video in item.get("video") or []:
        if not isinstance(video, dict):
            continue
        cover = video.get("url1") or video.get("pic_url")
        url = video.get("url3") or video.get("url2")
        if cover:
            images.append(str(cover))
        if url:
            videos.append(str(url))
    videos.extend(_extract_video_sources("", item))

    return QzonePost(
        tid=tid,
        uin=uin,
        name=str(_mapping_first(item, ("name", "nickname")) or uin),
        avatar_url=_avatar_url(
            _mapping_first(item, ("portrait", "avatar", "headurl")), uin
        ),
        text=_qzone_mapping_text(item, "content", "originalcontent"),
        images=list(dict.fromkeys(images)),
        videos=list(dict.fromkeys(videos)),
        create_time=_safe_int(
            _mapping_first(item, ("created_time", "create_time", "abstime"))
        ),
        rt_con=_qzone_repost_text(item),
        rt_uin=_safe_int(
            item.get("rt_uin") or rtitem.get("rt_uin") or rtitem.get("rt_wc_uin")
        ),
        rt_uinname=clean_qzone_text(
            item.get("rt_uinname")
            or rtitem.get("rt_uinname")
            or rtitem.get("rt_wc_nick")
        ),
        rt_tid=str(item.get("rt_tid") or rtitem.get("rt_tid") or ""),
        rt_images=list(
            dict.fromkeys(_qzone_repost_image_urls(item, rtitem) + inline_rt_images)
        ),
        comments=parse_comments(_feed_comment_items(item)),
        expandable=has_qzone_expand_marker(item.get("content")),
        appid=_safe_int(item.get("appid")) or 311,
        curkey=str(item.get("curkey") or item.get("curlikekey") or ""),
        unikey=str(item.get("unikey") or item.get("unlikekey") or ""),
        liked=_qzone_liked(
            item["like"] if isinstance(item.get("like"), dict) else {},
            item,
        ),
        busi_param=(
            item["busi_param"] if isinstance(item.get("busi_param"), dict) else {}
        ),
    )


def parse_feed_list(items: list[dict[str, Any]]) -> list[QzonePost]:
    posts = []
    for item in items or []:
        post = parse_feed_item(item)
        if post:
            posts.append(post)
    return posts


def parse_recent_feed_list(payload: dict[str, Any]) -> list[QzonePost]:
    posts: list[QzonePost] = []
    for item in _recent_payload_items(payload):
        if not isinstance(item, dict):
            continue
        raw_html = _decode_js_escaped_text(item.get("html") or "")
        feed_attrs = _first_feed_data_attrs(raw_html)
        block_meta = _feed_block_meta(raw_html)
        common = _first_json_mapping(item, FEED_COMMON_KEYS)
        appid = (
            _safe_int(
                _mapping_first(common, ("appid",))
                or _mapping_first(item, ("appid",))
                or _feed_data_attr(feed_attrs, "appid")
                or block_meta.get("appid")
            )
            or 311
        )
        tid = _recent_item_fid(item, common, raw_html)
        uin = _recent_item_uin(item, raw_html, common)
        if not tid or not uin:
            continue
        rtitem = _qzone_repost_mapping(item)
        name = _recent_item_name(item, raw_html, uin)
        text_source = _recent_item_text(raw_html, name) or _qzone_mapping_text(
            item, "content", "originalcontent"
        )
        rt_text = _qzone_repost_text(item)
        image_urls = _extract_attr_values(raw_html, "img-box", "src")
        image_urls.extend(_extract_attr_values(raw_html, "video-img", "src"))
        operation = _first_json_mapping(item, FEED_OPERATION_KEYS)
        like = _first_json_mapping(item, FEED_LIKE_KEYS)
        video_urls = _extract_video_sources(raw_html, item, common, operation)
        if (
            not clean_qzone_text(text_source)
            and not rt_text
            and not image_urls
            and not video_urls
        ):
            continue
        curkey = str(
            _mapping_first(item, ("curkey", "curlikekey"))
            or _mapping_first(common, ("curkey", "curlikekey"))
            or _feed_data_attr(feed_attrs, "curkey")
            or _html_first_attr(raw_html, ("data-curkey", "curkey"))
            or _qzone_unikey(appid, uin, tid)
        )
        unikey = str(
            _mapping_first(item, ("unikey", "unlikekey"))
            or _mapping_first(common, ("unikey", "unlikekey"))
            or _feed_data_attr(feed_attrs, "unikey")
            or _html_first_attr(raw_html, ("data-unikey", "unikey"))
            or _qzone_unikey(appid, uin, tid)
        )
        busi_param = operation.get("busi_param") or {}
        if not isinstance(busi_param, dict):
            busi_param = {}
        posts.append(
            QzonePost(
                tid=tid,
                uin=uin,
                name=name,
                avatar_url=_avatar_url(item.get("pic"), uin),
                text=text_source,
                images=list(dict.fromkeys(image_urls)),
                videos=list(dict.fromkeys(video_urls)),
                create_time=_safe_int(
                    _mapping_first(item, ("abstime", "created_time"))
                    or _feed_data_attr(feed_attrs, "abstime")
                    or block_meta.get("abstime")
                ),
                rt_con=rt_text,
                rt_uin=_safe_int(
                    item.get("rt_uin")
                    or rtitem.get("rt_uin")
                    or rtitem.get("rt_wc_uin")
                ),
                rt_uinname=clean_qzone_text(
                    item.get("rt_uinname")
                    or rtitem.get("rt_uinname")
                    or rtitem.get("rt_wc_nick")
                ),
                rt_tid=str(item.get("rt_tid") or rtitem.get("rt_tid") or ""),
                rt_images=_qzone_repost_image_urls(item, rtitem),
                expandable=has_qzone_expand_marker(text_source)
                or has_qzone_expand_marker(raw_html),
                appid=appid,
                feed_key=str(item.get("key") or ""),
                curkey=curkey,
                unikey=unikey,
                liked=_qzone_liked(like, item, common),
                busi_param=busi_param,
                comments=parse_comments(_feed_comment_items(item)),
            )
        )
    return posts


def parse_feedinfo_html(
    markup: Any,
    *,
    context_uin: int = 0,
    context_tid: str = "",
    context_time: int = 0,
) -> QzonePost | None:
    raw_html = str(markup or "").strip()
    if not raw_html:
        return None
    item = {
        "html": raw_html,
        "fid": context_tid
        or _html_attr(raw_html, "data-fid")
        or _html_attr(raw_html, "fid"),
        "tid": context_tid
        or _html_attr(raw_html, "data-tid")
        or _html_attr(raw_html, "tid"),
        "uin": context_uin
        or _html_attr(raw_html, "data-uin")
        or _html_attr(raw_html, "uin"),
        "appid": _html_attr(raw_html, "data-appid")
        or _html_attr(raw_html, "appid")
        or 311,
        "abstime": context_time,
    }
    match = re.search(r'id=(["\'])fct_(\d+)_(\d+)_[^"\']*?([^_"\'\s<>]+)\1', raw_html)
    if match:
        item["uin"] = item["uin"] or match.group(2)
        item["appid"] = item["appid"] or match.group(3)
        item["fid"] = item["fid"] or match.group(4)
        item["tid"] = item["tid"] or match.group(4)
    posts = parse_recent_feed_list({"data": {"data": [item]}})
    return posts[0] if posts else None


__all__ = [
    "parse_feed_item",
    "parse_feed_list",
    "parse_feedinfo_html",
    "parse_home_feed_list",
    "parse_recent_feed_list",
]

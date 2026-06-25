from __future__ import annotations

import re
from typing import Any

from .decoder import _clean_media_url, _tag_attrs, _walk_mappings


def _first_image_url(item: dict[str, Any]) -> str:
    for key in ("url2", "url3", "url1", "smallurl", "pic_url", "src"):
        value = item.get(key)
        if value:
            return str(value)
    return ""


def _is_qzone_content_image(url: str) -> bool:
    lower = str(url or "").lower()
    if not lower:
        return False
    if lower in {"#", "about:blank", "javascript:;", "javascript:void(0)"}:
        return False
    if lower.startswith(("about:", "javascript:")):
        return False
    if not lower.startswith(("http://", "https://", "data:image/")):
        return False
    blocked = (
        "qzonestyle.gtimg.cn",
        "qlogo.cn",
        "q.qlogo.cn",
        "q1.qlogo.cn",
        "thirdqq.qlogo.cn",
        "headimg_dl",
        "/head/",
        "/portrait/",
        "blank.gif",
        "loading.gif",
        "transparent.gif",
        "space.gif",
    )
    return not any(item in lower for item in blocked)


def _avatar_url(value: Any, uin: int = 0) -> str:
    url = _clean_media_url(value)
    lower = url.lower()
    if url and lower.startswith(("http://", "https://", "data:image/")):
        return url
    return f"https://q.qlogo.cn/headimg_dl?dst_uin={uin}&spec=100" if uin else ""


def _extract_image_sources(block: str) -> list[str]:
    values: list[str] = []
    for tag in re.findall(r"<img\b[^>]*>", block or "", re.I | re.S):
        attrs = _tag_attrs(tag)
        for key in ("data-origin", "data-original", "data-src", "origin-src", "src"):
            url = _clean_media_url(attrs.get(key))
            if _is_qzone_content_image(url):
                values.append(url)
                break
    return values


def _extract_attr_values(raw_html: str, selector_class: str, attr: str) -> list[str]:
    values: list[str] = []
    pattern = re.compile(
        rf'<div[^>]*class="[^"]*\b{re.escape(selector_class)}\b[^"]*"[^>]*>(.*?)</div>',
        re.S,
    )
    for block in pattern.findall(raw_html or ""):
        if attr.lower() == "src":
            values.extend(_extract_image_sources(block))
            continue
        for value in (
            match[2]
            for match in re.findall(
                rf'([:\w-]+)\s*=\s*(["\'])(.*?)\2',
                block,
                re.I | re.S,
            )
            if match[0].lower() == attr.lower()
        ):
            url = _clean_media_url(value)
            if _is_qzone_content_image(url):
                values.append(url)
    return values


def _is_video_url(value: str) -> bool:
    lower = str(value or "").lower()
    if re.search(r"\.(?:jpe?g|png|gif|webp|bmp)(?:[?#].*)?$", lower):
        return False
    return lower.startswith(("http://", "https://")) and (
        "video" in lower
        or lower.endswith((".mp4", ".mov", ".m4v", ".webm"))
        or "/v/" in lower
    )


def _qzone_video_uri(value: Any) -> str:
    vid = str(value or "").strip()
    if not vid or len(vid) < 8:
        return ""
    if vid.startswith(("http://", "https://", "qzone://video/")):
        return _clean_media_url(vid)
    if not re.fullmatch(r"[0-9A-Za-z_\-.]+", vid):
        return ""
    return f"qzone://video/{vid}"


def _extract_video_sources(raw_html: str, *payloads: Any) -> list[str]:
    values: list[str] = []
    for tag in re.findall(r"<(?:div|a|video|source)\b[^>]*>", raw_html or "", re.I | re.S):
        attrs = _tag_attrs(tag)
        for key, value in attrs.items():
            url = _clean_media_url(value)
            if key in {"src", "url", "url2", "url3", "href", "data-url", "data-src", "playurl", "play-url"} and _is_video_url(url):
                values.append(url)
            if key in {
                "vid",
                "data-vid",
                "videoid",
                "video-id",
                "data-videoid",
                "data-video-id",
                "svid",
                "data-svid",
                "vvid",
                "data-vvid",
                "vvideourl",
                "data-vvideourl",
            }:
                uri = _qzone_video_uri(value)
                if uri:
                    values.append(uri)
    for value in re.findall(
        r'["\']?(?:sVid|vid|vvid|vidid|videoId|video_id)["\']?\s*[:=]\s*["\']([0-9A-Za-z_\-.]{8,})["\']',
        raw_html or "",
        re.I,
    ):
        uri = _qzone_video_uri(value)
        if uri:
            values.append(uri)
    for payload in payloads:
        for mapping in _walk_mappings(payload):
            for key, value in mapping.items():
                key_text = str(key).lower()
                if key_text in {"svid", "vid", "videoid", "video_id", "vvid", "vidid"}:
                    uri = _qzone_video_uri(value)
                    if uri:
                        values.append(uri)
                if isinstance(value, str) and (
                    "video" in key_text
                    or "vvidio" in key_text
                    or key_text in {"url", "url2", "url3", "playurl", "vurl", "vurl2", "vurl3"}
                ):
                    url = _clean_media_url(value)
                    if _is_video_url(url):
                        values.append(url)
                if isinstance(value, str) and "richval" in key_text:
                    for match in re.finditer(r"(?:^|[?&])vid=([0-9A-Za-z_\-.]{8,})", value):
                        uri = _qzone_video_uri(match.group(1))
                        if uri:
                            values.append(uri)
    return list(dict.fromkeys(values))

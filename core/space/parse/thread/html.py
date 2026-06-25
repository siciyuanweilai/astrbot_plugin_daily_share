from __future__ import annotations

import html
import re
from typing import Any

from ..decoder import _html_attr, _safe_int, clean_qzone_text
from .fields import FEED_COMMENT_KEYS


def _find_matching_comments_item_li(text: str, open_end: int) -> int:
    depth = 1
    position = int(open_end or 0)
    open_pattern = re.compile(r'<li\b[^>]*class=(["\'])[^"\']*\bcomments-item\b[^"\']*\1', re.I)
    while position < len(text):
        close_index = text.find("</li>", position)
        if close_index < 0:
            return -1
        open_match = open_pattern.search(text, position)
        if open_match and open_match.start() < close_index:
            depth += 1
            position = open_match.end()
            continue
        depth -= 1
        if depth == 0:
            return close_index + len("</li>")
        position = close_index + len("</li>")
    return -1


def _comment_data_param(block: str, name: str) -> str:
    source = html.unescape(str(block or ""))
    match = re.search(rf"(?:^|[?&]){re.escape(name)}=([^&\"'<>\s]+)", source, re.I)
    return match.group(1).strip() if match else ""


def _comment_content_html(block: str) -> str:
    match = re.search(
        r'<div\b[^>]*class=(["\'])[^"\']*\bcomments-content\b[^"\']*\1[^>]*>(.*?)</div>',
        block or "",
        re.I | re.S,
    )
    return match.group(2) if match else block


def _comment_text_from_html(block: str) -> str:
    text = clean_qzone_text(_comment_content_html(block))
    for sep in ("：", ":"):
        index = text.rfind(sep)
        if index >= 0:
            text = text[index + 1 :].strip()
            break
    return text


def _reply_to_nickname_from_html(block: str) -> str:
    match = re.search(
        r"回复\s*<a\b[^>]*class=(['\"])[^'\"]*\bnickname\b[^'\"]*\1[^>]*>(.*?)</a>",
        block or "",
        re.I | re.S,
    )
    return clean_qzone_text(match.group(2)) if match else ""


def _feed_html_comment_items(raw_html: str) -> list[dict[str, Any]]:
    source = str(raw_html or "")
    if "comments-item" not in source:
        return []
    comments: list[dict[str, Any]] = []
    root_pattern = re.compile(
        r'<li\b[^>]*class=(["\'])[^"\']*\bcomments-item\b[^"\']*\1[^>]*\bdata-type=(["\'])commentroot\2[^>]*>',
        re.I | re.S,
    )
    for root_match in root_pattern.finditer(source):
        open_tag = root_match.group(0)
        close_end = _find_matching_comments_item_li(source, root_match.end())
        if close_end < 0:
            continue
        full_block = source[root_match.start() : close_end]
        root_body = re.split(
            r'<div\b[^>]*class=(["\'])[^"\']*\bmod-comments-sub\b[^"\']*\1',
            full_block,
            maxsplit=1,
            flags=re.I | re.S,
        )[0]
        root_tid = _html_attr(open_tag, "data-tid")
        root_uin = _safe_int(_html_attr(open_tag, "data-uin"))
        if not root_tid or not root_uin:
            continue
        root = {
            "commentid": root_tid,
            "uin": root_uin,
            "nickname": clean_qzone_text(_html_attr(open_tag, "data-nick")),
            "content": _comment_text_from_html(root_body),
            "html": root_body,
            "replyList": [],
        }
        reply_pattern = re.compile(
            r'<li\b[^>]*class=(["\'])[^"\']*\bcomments-item\b[^"\']*\1[^>]*\bdata-type=(["\'])replyroot\2[^>]*>',
            re.I | re.S,
        )
        for reply_match in reply_pattern.finditer(full_block):
            reply_open = reply_match.group(0)
            reply_close = _find_matching_comments_item_li(full_block, reply_match.end())
            if reply_close < 0:
                continue
            reply_block = full_block[reply_match.start() : reply_close]
            reply_tid = _html_attr(reply_open, "data-tid")
            reply_uin = _safe_int(_html_attr(reply_open, "data-uin"))
            if not reply_tid or not reply_uin:
                continue
            t2_tid = _comment_data_param(reply_block, "t2_tid") or root_tid
            t2_uin = _safe_int(_comment_data_param(reply_block, "t2_uin"))
            root["replyList"].append(
                {
                    "commentId": reply_tid,
                    "commentUin": reply_uin,
                    "nickname": clean_qzone_text(_html_attr(reply_open, "data-nick")),
                    "commentContent": _comment_text_from_html(reply_block),
                    "parent_tid": root_tid,
                    "reply_to_tid": t2_tid,
                    "reply_to_uin": t2_uin,
                    "reply_to_nickname": _reply_to_nickname_from_html(reply_block),
                    "html": reply_block,
                }
            )
        comments.append(root)
    return comments


def _feed_comment_items(item: dict[str, Any]) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for key in FEED_COMMENT_KEYS:
        value = item.get(key)
        if not isinstance(value, list):
            continue
        comments.extend(child for child in value if isinstance(child, dict))
    comments.extend(_feed_html_comment_items(str(item.get("html") or "")))
    return comments

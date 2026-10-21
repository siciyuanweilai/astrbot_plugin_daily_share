from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

from ..decoder import _html_attr, _safe_int, clean_qzone_text
from .fields import FEED_COMMENT_KEYS


def _find_matching_comments_item_li(text: str, open_end: int) -> int:
    depth = 1
    position = int(open_end or 0)
    open_pattern = re.compile(
        r'<li\b[^>]*class=(["\'])[^"\']*\bcomments-item\b[^"\']*\1', re.I
    )
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


def _photo_batch_comment_fields(block: str, comment_id: str) -> dict[str, Any]:
    """仅从该楼层的回复按钮读取上传批次绑定，不借用整条动态的目标。"""
    for match in re.finditer(r"<a\b[^>]*>", block, re.I | re.S):
        tag = match.group(0)
        if _html_attr(tag, "data-cmd") != "qz_reply":
            continue
        try:
            action = urlsplit(_html_attr(tag, "data-action"))
        except ValueError:
            continue
        if (
            action.hostname not in {"photo.qq.com", "photo.qzone.qq.com"}
            or action.path != "/cgi-bin/common/cgi_add_icreply"
        ):
            continue
        values = parse_qs(_html_attr(tag, "data-param"), keep_blank_values=True)
        if any(len(items) != 1 for items in values.values()):
            continue
        params = {key: items[0] for key, items in values.items()}
        batch = params.get("batchId", "")
        album, pic = params.get("albumid", ""), params.get("lloc", "")
        owner = _safe_int(params.get("oweruin"))
        if (
            params.get("cmtid") != comment_id
            or params.get("cmtType") != "4"
            or not batch.isascii()
            or not batch.isdigit()
            or len(batch) > 20
            or int(batch) <= 0
            or not owner
            or not album
            or not pic
        ):
            continue
        return {
            "photo_topic_id": f"{album}_{pic}_{batch}_4",
            "photo_owner_uin": owner,
            "photo_private": params.get("zz", "unknown"),
        }
    return {}


def _comment_content_html(block: str) -> str:
    match = re.search(
        r'<div\b[^>]*class=(["\'])[^"\']*\bcomments-content\b[^"\']*\1[^>]*>(.*?)</div>',
        block or "",
        re.I | re.S,
    )
    return match.group(2) if match else block


def _comment_text_from_html(block: str) -> str:
    content_html = _comment_content_html(block)
    content_html = re.split(
        r'<div\b[^>]*class=["\'][^"\']*\bcomments-op\b',
        content_html,
        maxsplit=1,
        flags=re.I,
    )[0]
    text = clean_qzone_text(content_html)
    nickname_anchor = (
        r'<a\b[^>]*class=["\'][^"\']*\bnickname\b[^"\']*["\']'
        r"[^>]*>.*?</a>"
    )
    prefix = re.search(
        rf"^\s*{nickname_anchor}"
        rf"(?:\s|&nbsp;)*(?:回复\s*{nickname_anchor}\s*)?"
        r"(?:\s|&nbsp;)*[:：]",
        content_html or "",
        re.I | re.S,
    )
    if prefix:
        body = clean_qzone_text(content_html[prefix.end() :])
        if body:
            return body
    return text


def _reply_target_from_html(block: str) -> tuple[int, str]:
    match = re.search(
        r"^\s*<a\b[^>]*>.*?</a>(?:\s|&nbsp;)*回复\s*"
        r"(<a\b[^>]*class=(['\"])[^'\"]*\bnickname\b[^'\"]*\2[^>]*>)"
        r"(.*?)</a>(?:\s|&nbsp;)*[:：]",
        _comment_content_html(block),
        re.I | re.S,
    )
    if not match:
        return 0, ""
    tag, nickname = match.group(1), clean_qzone_text(match.group(3))
    identities = set()
    card = re.search(r"(?:^|\s)nameCard_([0-9]+)(?:\s|$)", _html_attr(tag, "link"))
    if card:
        identities.add(_safe_int(card.group(1)))
    try:
        href = urlsplit(_html_attr(tag, "href"))
        if href.hostname == "user.qzone.qq.com" and re.fullmatch(
            r"/[0-9]+/?", href.path
        ):
            identities.add(_safe_int(href.path.strip("/")))
    except ValueError:
        pass
    # 昵称会重名；只认回复前缀里的账号链接，冲突或缺失时不推测对象。
    uin = identities.pop() if len(identities) == 1 else 0
    return max(uin, 0), nickname


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
        photo_fields = _photo_batch_comment_fields(root_body, root_tid)
        root: dict[str, Any] = {
            **photo_fields,
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
            target_uin, target_nickname = _reply_target_from_html(reply_block)
            content = _comment_text_from_html(reply_block)
            created_at = 0
            if photo_fields:
                t2_uin = target_uin
                if target_uin:
                    content = f"@{{uin:{target_uin}}} {content}"
                # 相册楼中楼的 data-tid 是 Unix 秒；一级评论 ID 不是时间。
                if re.fullmatch(r"[0-9]{10}", reply_tid):
                    timestamp = int(reply_tid)
                    if 946684800 <= timestamp < 4102444800:
                        created_at = timestamp
            root["replyList"].append(
                {
                    **photo_fields,
                    "commentId": reply_tid,
                    "commentUin": reply_uin,
                    "nickname": clean_qzone_text(_html_attr(reply_open, "data-nick")),
                    "commentContent": content,
                    "create_time": created_at,
                    "parent_tid": root_tid,
                    "reply_to_tid": t2_tid,
                    "reply_to_uin": t2_uin,
                    "reply_to_nickname": target_nickname,
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

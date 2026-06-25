from __future__ import annotations

import html
import re
from typing import Any

from ...models import QzoneComment
from ..decoder import _first_text, _mapping_first, _safe_int, clean_qzone_text
from .fields import (
    COMMENT_CONTENT_KEYS,
    COMMENT_ID_KEYS,
    COMMENT_NICKNAME_KEYS,
    COMMENT_PARENT_KEYS,
    COMMENT_REPLY_NICKNAME_KEYS,
    COMMENT_REPLY_TID_KEYS,
    COMMENT_REPLY_UIN_KEYS,
    COMMENT_TIME_KEYS,
    COMMENT_UIN_KEYS,
    COMMENT_USER_NICKNAME_KEYS,
    COMMENT_USER_UIN_KEYS,
    RAW_COMMENT_FIELD_KEYS,
)


def _comment_user(item: dict[str, Any]) -> dict[str, Any]:
    for key in ("user", "userinfo", "commenter"):
        value = item.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _comment_param(item: dict[str, Any], name: str) -> str:
    fields = ("html", "htmlContent", "raw_html", "rawHtml", "operation", "content", "commentContent")
    text = "\n".join(str(item.get(key) or "") for key in fields)
    if not text:
        return ""
    match = re.search(rf"(?:^|[?&\"'\s]){re.escape(name)}=([^&\"'\s<>]+)", html.unescape(text), re.I)
    return html.unescape(match.group(1)).strip() if match else ""


def _comment_mention_param(item: dict[str, Any], name: str) -> str:
    fields = ("content", "commentContent", "htmlContent", "text", "html", "raw_html", "rawHtml")
    text = html.unescape("\n".join(str(item.get(key) or "") for key in fields))
    if not text:
        return ""
    match = re.search(rf"@\{{[^}}]*\b{re.escape(name)}:([^,}}]+)", text, re.I)
    return html.unescape(match.group(1)).strip() if match else ""


def _first_named_text(item: dict[str, Any], *names: str) -> tuple[str, str]:
    for name in names:
        value = _first_text(item.get(name))
        if value:
            return value, name
    return "", ""


def _comment_children(item: dict[str, Any]) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []
    for key in ("list_3", "replyList", "replylist", "reply_list", "replies", "children"):
        for child in item.get(key) or []:
            if isinstance(child, dict):
                children.append(child)
    return children


def _raw_comment_fields(item: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key in RAW_COMMENT_FIELD_KEYS:
        value = item.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, (str, int, float, bool)):
            fields[key] = value
    params = {
        name: found
        for name in ("t1_tid", "t1_uin", "t2_tid", "t2_uin", "commentId", "commentUin", "replyUin")
        for found in (_comment_param(item, name),)
        if found
    }
    if params:
        fields["extracted_params"] = params
    for key in ("html", "htmlContent", "raw_html", "rawHtml", "operation"):
        value = str(item.get(key) or "")
        if not value:
            continue
        text = html.unescape(value).strip()
        fields[f"{key}_preview"] = text[:500] if len(text) > 500 else text
    return fields


def _comment_from_raw(item: dict[str, Any], *, parent_tid: str = "") -> QzoneComment:
    user = _comment_user(item)
    submit_tid = _first_text(_mapping_first(item, COMMENT_ID_KEYS))
    raw_tid = _first_text(item.get("tid"), submit_tid)
    reply_to_tid, reply_to_tid_source = _first_named_text(item, *COMMENT_REPLY_TID_KEYS)
    if not reply_to_tid:
        reply_to_tid = _comment_param(item, "t2_tid")
        reply_to_tid_source = "param:t2_tid" if reply_to_tid else ""
    reply_to_uin_text, _reply_to_uin_source = _first_named_text(item, *COMMENT_REPLY_UIN_KEYS)
    if not reply_to_uin_text:
        reply_to_uin_text = _comment_param(item, "t2_uin") or _comment_mention_param(item, "uin")
    reply_to_uin = _safe_int(reply_to_uin_text)
    reply_to_nickname = _first_text(_mapping_first(item, COMMENT_REPLY_NICKNAME_KEYS), _comment_mention_param(item, "nick"))
    return QzoneComment(
        uin=_safe_int(_mapping_first(item, COMMENT_UIN_KEYS) or _mapping_first(user, COMMENT_USER_UIN_KEYS)),
        nickname=_first_text(_mapping_first(user, COMMENT_USER_NICKNAME_KEYS), _mapping_first(item, COMMENT_NICKNAME_KEYS)),
        content=clean_qzone_text(_mapping_first(item, COMMENT_CONTENT_KEYS)),
        create_time=_safe_int(_mapping_first(item, COMMENT_TIME_KEYS)),
        tid=raw_tid,
        submit_tid=submit_tid,
        raw_tid=raw_tid,
        parent_tid=_first_text(parent_tid, _mapping_first(item, COMMENT_PARENT_KEYS)),
        reply_to_tid=reply_to_tid,
        raw_reply_to_tid=reply_to_tid,
        reply_to_uin=reply_to_uin,
        raw_reply_to_uin=reply_to_uin,
        reply_to_nickname=reply_to_nickname,
        reply_to_tid_source=reply_to_tid_source,
        raw_fields=_raw_comment_fields(item),
    )

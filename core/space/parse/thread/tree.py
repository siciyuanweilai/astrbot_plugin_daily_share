from __future__ import annotations

from typing import Any

from ...models import QzoneComment
from .raw import _comment_children, _comment_from_raw


def parse_comments(items: list[dict[str, Any]]) -> list[QzoneComment]:
    result: list[QzoneComment] = []
    seen_short_tid_count: dict[tuple[str, str, int], int] = {}
    seen_short_tid_target: dict[tuple[str, str, int], str] = {}

    def stable_child_tid(tid: str, parent_tid: str = "", uin: int = 0) -> str:
        tid = str(tid or "").strip()
        parent_tid = str(parent_tid or "").strip()
        if not tid or not parent_tid or "_r_" in tid or not tid.isdigit():
            return tid
        uin = int(uin or 0)
        key = (parent_tid, tid, uin)
        count = seen_short_tid_count.get(key, 0) + 1
        seen_short_tid_count[key] = count
        base = f"{parent_tid}_r_{tid}_{uin}" if uin else f"{parent_tid}_r_{tid}"
        return base if count <= 1 else f"{base}_n{count}"

    def append_item(item: dict[str, Any], *, parent_tid: str = "", reply_to_tid: str = "") -> None:
        if not isinstance(item, dict):
            return
        comment = _comment_from_raw(item, parent_tid=parent_tid)
        if reply_to_tid and not comment.reply_to_tid:
            comment.reply_to_tid = reply_to_tid
            comment.raw_reply_to_tid = reply_to_tid
            comment.reply_to_tid_source = "inherited"
        raw_tid = str(comment.tid or "").strip()
        parent_tid = str(comment.parent_tid or "").strip()
        raw_reply_to_tid = str(comment.reply_to_tid or "").strip()
        reply_to_uin = int(comment.reply_to_uin or 0)
        comment.tid = stable_child_tid(raw_tid, parent_tid, comment.uin)
        if parent_tid and raw_reply_to_tid.isdigit() and reply_to_uin:
            comment.reply_to_tid = seen_short_tid_target.get(
                (parent_tid, raw_reply_to_tid, reply_to_uin),
                raw_reply_to_tid,
            )
        if parent_tid and raw_tid.isdigit() and comment.uin:
            seen_short_tid_target[(parent_tid, raw_tid, int(comment.uin or 0))] = comment.tid
        if comment.tid or comment.content:
            result.append(comment)
        child_parent_tid = parent_tid or comment.tid
        child_reply_to_tid = comment.tid or reply_to_tid
        for child in _comment_children(item):
            append_item(child, parent_tid=child_parent_tid, reply_to_tid=child_reply_to_tid)

    for item in items or []:
        append_item(item)
    return result

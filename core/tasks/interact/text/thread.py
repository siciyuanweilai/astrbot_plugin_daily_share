from __future__ import annotations

from typing import Any

from .time import _format_qzone_local_datetime


def _qzone_auto_reply_comment_summary(post, comment) -> str:
    post_content = str(getattr(post, "text", "") or getattr(post, "rt_con", "") or "").strip()
    if len(post_content) > 220:
        post_content = f"{post_content[:220].rstrip()}..."
    comment_content = str(getattr(comment, "content", "") or "").strip()
    if len(comment_content) > 160:
        comment_content = f"{comment_content[:160].rstrip()}..."
    return "\n".join(
        [
            f"我的说说：{post_content or '（没有文字，可能主要是图片或视频）'}",
            f"说说发布时间：{_format_qzone_local_datetime(getattr(post, 'create_time', 0))}",
            f"评论人：{getattr(comment, 'nickname', '') or getattr(comment, 'uin', '')}",
            f"评论时间：{_format_qzone_local_datetime(getattr(comment, 'create_time', 0))}",
            f"对方评论：{comment_content}",
        ]
    )


def _qzone_comment_label(comment) -> str:
    return str(getattr(comment, "nickname", "") or getattr(comment, "uin", "") or "").strip() or "未知用户"


def _qzone_comment_ids(comment) -> set[str]:
    return {
        value
        for value in (
            str(getattr(comment, "tid", "") or "").strip(),
            str(getattr(comment, "submit_tid", "") or "").strip(),
            str(getattr(comment, "raw_tid", "") or "").strip(),
        )
        if value
    }


def _qzone_reply_target_ids(comment) -> set[str]:
    return {
        value
        for value in (
            str(getattr(comment, "reply_to_tid", "") or "").strip(),
            str(getattr(comment, "raw_reply_to_tid", "") or "").strip(),
        )
        if value
    }


def _same_qzone_comment(left, right) -> bool:
    if left is right:
        return True
    left_tid = str(getattr(left, "tid", "") or "").strip()
    right_tid = str(getattr(right, "tid", "") or "").strip()
    return bool(left_tid and right_tid and left_tid == right_tid)


def _qzone_comment_created_at(comment) -> int:
    try:
        return int(getattr(comment, "create_time", 0) or 0)
    except Exception:
        return 0


def _qzone_comment_index(comments: list, comment) -> int:
    for index, item in enumerate(comments):
        if _same_qzone_comment(item, comment):
            return index
    return -1


def _qzone_same_thread_comments(comments: list, parent_comment) -> list[tuple[int, Any]]:
    thread_ids = set(_qzone_comment_ids(parent_comment))
    if not thread_ids:
        return []

    selected: set[int] = set()
    changed = True
    while changed:
        changed = False
        for index, item in enumerate(comments):
            if index in selected or _same_qzone_comment(item, parent_comment):
                continue
            parent_tid = str(getattr(item, "parent_tid", "") or "").strip()
            in_thread = parent_tid in thread_ids if parent_tid else bool(_qzone_reply_target_ids(item) & thread_ids)
            if in_thread:
                selected.add(index)
                thread_ids.update(_qzone_comment_ids(item))
                changed = True
    return [(index, comments[index]) for index in sorted(selected)]


def _qzone_thread_history_before(post, parent_comment, comment, *, max_items: int = 6) -> list:
    comments = list(getattr(post, "comments", []) or [])
    target_index = _qzone_comment_index(comments, comment)
    target_time = _qzone_comment_created_at(comment)
    history = []
    for index, item in _qzone_same_thread_comments(comments, parent_comment):
        if _same_qzone_comment(item, comment):
            continue
        item_time = _qzone_comment_created_at(item)
        if target_time and item_time:
            is_before = item_time < target_time or (item_time == target_time and 0 <= index < target_index)
        elif target_index >= 0:
            is_before = index < target_index
        else:
            is_before = False
        if not is_before:
            continue

        if str(getattr(item, "content", "") or "").strip():
            history.append((item_time, index, item))

    history.sort(key=lambda value: (value[0] or 0, value[1]))
    return [item for _item_time, _index, item in history[-max_items:]]


def _qzone_thread_history_summary(post, parent_comment, comment) -> str:
    lines = []
    for item in _qzone_thread_history_before(post, parent_comment, comment):
        content = str(getattr(item, "content", "") or "").strip()
        if len(content) > 120:
            content = f"{content[:120].rstrip()}..."
        reply_to = str(getattr(item, "reply_to_nickname", "") or "").strip()
        speaker = _qzone_comment_label(item)
        if reply_to:
            speaker = f"{speaker} 回复 {reply_to}"
        lines.append(
            f"- {speaker}（{_format_qzone_local_datetime(getattr(item, 'create_time', 0))}）：{content}"
        )
    return "\n".join(lines)


def _qzone_auto_reply_thread_summary(post, parent_comment, comment) -> str:
    post_content = str(getattr(post, "text", "") or getattr(post, "rt_con", "") or "").strip()
    if len(post_content) > 220:
        post_content = f"{post_content[:220].rstrip()}..."
    parent_content = str(getattr(parent_comment, "content", "") or "").strip()
    if len(parent_content) > 140:
        parent_content = f"{parent_content[:140].rstrip()}..."
    comment_content = str(getattr(comment, "content", "") or "").strip()
    if len(comment_content) > 160:
        comment_content = f"{comment_content[:160].rstrip()}..."
    parts = [
        f"我的说说：{post_content or '（没有文字，可能主要是图片或视频）'}",
        f"说说发布时间：{_format_qzone_local_datetime(getattr(post, 'create_time', 0))}",
        f"这一楼的一级评论人：{_qzone_comment_label(parent_comment)}",
        f"一级评论时间：{_format_qzone_local_datetime(getattr(parent_comment, 'create_time', 0))}",
        f"一级评论：{parent_content}",
    ]
    history = _qzone_thread_history_summary(post, parent_comment, comment)
    if history:
        parts.append(f"同楼前文对话（按时间顺序，越靠后越新）：\n{history}")
    parts.extend(
        [
            f"新的二级回复人：{_qzone_comment_label(comment)}",
            f"新的二级回复时间：{_format_qzone_local_datetime(getattr(comment, 'create_time', 0))}",
            f"新的二级回复：{comment_content}",
        ]
    )
    return "\n".join(parts)

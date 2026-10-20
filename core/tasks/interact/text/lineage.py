from __future__ import annotations

from typing import Any

from .clean import _strip_qzone_mention_tags
from .time import _format_qzone_local_datetime


def _qzone_auto_reply_comment_summary(
    post, comment, *, as_post_owner: bool = True, self_uin: int = 0
) -> str:
    post_content = str(
        getattr(post, "text", "") or getattr(post, "rt_con", "") or ""
    ).strip()
    if len(post_content) > 220:
        post_content = f"{post_content[:220].rstrip()}..."
    comment_content = _strip_qzone_mention_tags(getattr(comment, "content", ""))
    if len(comment_content) > 160:
        comment_content = f"{comment_content[:160].rstrip()}..."
    post_label = "相册照片" if int(getattr(post, "appid", 311) or 311) == 4 else "说说"
    author = (
        "我"
        if as_post_owner
        else f"{getattr(post, 'name', '') or '好友'}（QQ：{getattr(post, 'uin', '')}）"
    )
    if as_post_owner:
        self_uin = self_uin or getattr(post, "uin", 0)
    parts = [
        f"{author}的{post_label}：{post_content or '（没有文字，可能主要是图片或视频）'}",
        f"{post_label}发布时间：{_format_qzone_local_datetime(getattr(post, 'create_time', 0))}",
    ]
    context = _qzone_root_reply_dialogue_context(post, comment, self_uin=self_uin)
    if context:
        parts.append(context)
    parts.extend(
        [
            f"评论人：{_qzone_comment_label(comment)}",
            f"评论时间：{_format_qzone_local_datetime(getattr(comment, 'create_time', 0))}",
            f"对方评论：{comment_content}",
        ]
    )
    return "\n".join(parts)


def _qzone_comment_label(comment, *, self_uin: int = 0) -> str:
    name = (
        str(
            getattr(comment, "nickname", "") or getattr(comment, "uin", "") or ""
        ).strip()
        or "未知用户"
    )
    uin = str(getattr(comment, "uin", "") or "").strip()
    label = f"{name}（QQ：{uin}）" if uin and uin != "0" else name
    return f"你（Bot）· {label}" if self_uin and uin == str(self_uin) else label


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


def _qzone_public_post_comments(post) -> list:
    return [
        item
        for item in (getattr(post, "comments", []) or [])
        if all(
            (getattr(item, "raw_fields", None) or {}).get(key) in (None, 0, "0", "")
            for key in ("photo_private", "private")
        )
    ]


def _qzone_same_thread_comments(
    comments: list, parent_comment
) -> list[tuple[int, Any]]:
    if not _qzone_comment_ids(parent_comment):
        return []
    # 优先使用稳定编号；二级回复的局部短编号会与其他楼层重复。
    items = list(comments)
    root_index = _qzone_comment_index(items, parent_comment)
    if root_index < 0:
        root_index = len(items)
        items.append(parent_comment)
    exact = {}
    aliases: dict[str, set[int]] = {}
    for index, item in enumerate(items):
        tid = str(getattr(item, "tid", "") or "").strip()
        if tid:
            exact[tid] = index
        for alias in _qzone_comment_ids(item):
            aliases.setdefault(alias, set()).add(index)
    parents = {}
    for index, item in enumerate(items):
        target = str(
            getattr(item, "parent_tid", "") or getattr(item, "reply_to_tid", "") or ""
        ).strip()
        if target in exact:
            parents[index] = exact[target]
        elif len(matches := aliases.get(target, set())) == 1:
            parents[index] = next(iter(matches))
    selected = {root_index}
    changed = True
    while changed:
        changed = False
        for index, parent_index in parents.items():
            if index not in selected and parent_index in selected:
                selected.add(index)
                changed = True
    return [
        (index, comments[index])
        for index in sorted(selected - {root_index})
        if index < len(comments)
    ]


def _qzone_dialogue_lines(comments: list, *, self_uin: int = 0) -> str:
    lines = []
    for item in comments:
        content = _strip_qzone_mention_tags(getattr(item, "content", ""))
        if not content:
            continue
        if len(content) > 120:
            content = f"{content[:120].rstrip()}..."
        speaker = _qzone_comment_label(item, self_uin=self_uin)
        reply_to = str(getattr(item, "reply_to_nickname", "") or "").strip()
        if reply_to:
            speaker = f"{speaker} 回复 {reply_to}"
        lines.append(
            f"- {speaker}（{_format_qzone_local_datetime(getattr(item, 'create_time', 0))}）：{content}"
        )
    return "\n".join(lines)


def _qzone_root_reply_dialogue_context(post, comment, *, self_uin: int) -> str:
    """使用本次已取得的公开评论，不额外查询或生成摘要。"""
    comments = _qzone_public_post_comments(post)
    same_floor = _qzone_same_thread_comments(comments, comment)
    same_floor.sort(key=lambda pair: (_qzone_comment_created_at(pair[1]), pair[0]))
    parts = []
    history = _qzone_dialogue_lines(
        [item for _index, item in same_floor[-6:]], self_uin=self_uin
    )
    if history:
        parts.append(f"目标评论楼中已有对话（按时间顺序）：\n{history}")

    # 保留本人已有发言及与当前评论人的往来，其他楼只作背景，分别展示。
    actor_uin = str(getattr(comment, "uin", "") or "0")
    related = []
    for index, root in enumerate(comments):
        if _same_qzone_comment(root, comment):
            continue
        if getattr(root, "parent_tid", "") or getattr(root, "reply_to_tid", ""):
            continue
        thread = _qzone_same_thread_comments(comments, root)
        participants = {
            str(getattr(item, "uin", "") or "0")
            for item in [root, *(item for _index, item in thread)]
        }
        has_self = bool(self_uin and str(self_uin) in participants)
        has_actor = actor_uin != "0" and actor_uin in participants
        if not (has_self or has_actor):
            continue
        thread.sort(key=lambda pair: (_qzone_comment_created_at(pair[1]), pair[0]))
        latest = max(
            [_qzone_comment_created_at(root)]
            + [_qzone_comment_created_at(item) for _index, item in thread]
        )
        related.append(((has_self, has_actor, latest, index), root, thread))
    for _rank, root, thread in sorted(related, key=lambda item: item[0], reverse=True)[
        :2
    ]:
        history = _qzone_dialogue_lines(
            [root, *(item for _index, item in thread[-4:])], self_uin=self_uin
        )
        if history:
            parts.append(f"同一动态的其他相关评论楼（仅作背景）：\n{history}")
    return "\n\n".join(parts)


def _qzone_thread_history_before(
    post, parent_comment, comment, *, max_items: int = 6
) -> list:
    comments = _qzone_public_post_comments(post)
    target_index = _qzone_comment_index(comments, comment)
    target_time = _qzone_comment_created_at(comment)
    history = []
    for index, item in _qzone_same_thread_comments(comments, parent_comment):
        if _same_qzone_comment(item, comment):
            continue
        item_time = _qzone_comment_created_at(item)
        if target_time and item_time:
            is_before = item_time < target_time or (
                item_time == target_time and 0 <= index < target_index
            )
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
    return _qzone_dialogue_lines(
        _qzone_thread_history_before(post, parent_comment, comment)
    )


def _qzone_auto_reply_thread_summary(post, parent_comment, comment) -> str:
    post_content = str(
        getattr(post, "text", "") or getattr(post, "rt_con", "") or ""
    ).strip()
    if len(post_content) > 220:
        post_content = f"{post_content[:220].rstrip()}..."
    parent_content = str(getattr(parent_comment, "content", "") or "").strip()
    if len(parent_content) > 140:
        parent_content = f"{parent_content[:140].rstrip()}..."
    comment_content = str(getattr(comment, "content", "") or "").strip()
    if len(comment_content) > 160:
        comment_content = f"{comment_content[:160].rstrip()}..."
    parts = [
        f"动态作者：{getattr(post, 'name', '') or '未知昵称'}（QQ：{getattr(post, 'uin', '')}）",
        f"这条说说：{post_content or '（没有文字，可能主要是图片或视频）'}",
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

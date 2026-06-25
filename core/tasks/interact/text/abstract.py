from __future__ import annotations

from .time import _format_qzone_local_datetime


def _qzone_summary_generation_failed_suffix(result: dict) -> str:
    failed = int(result.get("generation_failed", 0) or 0) if isinstance(result, dict) else 0
    return f"，生成/判断失败 {failed} 条" if failed > 0 else ""


def _qzone_post_plain_text(post) -> str:
    parts = []
    for name in ("text", "rt_con", "content", "summary", "desc", "description"):
        value = getattr(post, name, "")
        if isinstance(value, dict):
            value = value.get("content") or value.get("text") or value.get("desc") or value.get("description")
        text = str(value or "").strip()
        if text:
            parts.append(text)

    busi_param = getattr(post, "busi_param", None)
    if isinstance(busi_param, dict):
        for name in ("content", "text", "desc", "description", "summary"):
            text = str(busi_param.get(name) or "").strip()
            if text:
                parts.append(text)

    return " ".join(" ".join(parts).split()).strip()


def _qzone_auto_comment_post_summary(post) -> str:
    content = _qzone_post_plain_text(post)
    if len(content) > 260:
        content = f"{content[:260].rstrip()}..."
    media = []
    images = getattr(post, "images", []) or []
    videos = getattr(post, "videos", []) or []
    if images:
        media.append(f"{len(images)} 张图片")
    if videos:
        media.append(f"{len(videos)} 个视频")
    comments = []
    for comment in (getattr(post, "comments", []) or [])[:3]:
        nickname = str(getattr(comment, "nickname", "") or getattr(comment, "uin", "") or "").strip()
        body = str(getattr(comment, "content", "") or "").strip()
        if body:
            comments.append(f"{nickname}: {body}" if nickname else body)
    return "\n".join(
        [
            f"作者：{getattr(post, 'name', '') or getattr(post, 'uin', '')}",
            f"发布时间：{_format_qzone_local_datetime(getattr(post, 'create_time', 0))}",
            f"正文：{content or '（没有文字，主要看图片或视频）'}",
            f"媒体：{'、'.join(media) if media else '无'}",
            f"已有评论：{'；'.join(comments) if comments else '无'}",
        ]
    )

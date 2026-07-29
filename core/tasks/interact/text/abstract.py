from __future__ import annotations

from .time import _format_qzone_local_datetime


def _qzone_summary_generation_failed_suffix(result: dict) -> str:
    failed = (
        int(result.get("generation_failed", 0) or 0) if isinstance(result, dict) else 0
    )
    return f"，生成/判断失败 {failed} 条" if failed > 0 else ""


def _qzone_post_plain_text(post) -> str:
    parts = []
    for name in ("text", "rt_con", "content", "summary", "desc", "description"):
        value = getattr(post, name, "")
        if isinstance(value, dict):
            value = (
                value.get("content")
                or value.get("text")
                or value.get("desc")
                or value.get("description")
            )
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


def _qzone_compact_text(value, *, limit: int = 260) -> str:
    if isinstance(value, dict):
        value = (
            value.get("content")
            or value.get("text")
            or value.get("desc")
            or value.get("description")
        )
    text = " ".join(str(value or "").split()).strip()
    if limit > 0 and len(text) > limit:
        return f"{text[:limit].rstrip()}..."
    return text


def _qzone_media_summary(*, images: list, rt_images: list, videos: list) -> str:
    media = []
    if images:
        media.append(f"正文图片 {len(images)} 张")
    if rt_images:
        media.append(f"转发图片 {len(rt_images)} 张")
    if videos:
        media.append(f"视频 {len(videos)} 个")
    return "、".join(media) if media else "无"


def _qzone_comment_preview(post) -> str:
    comments = []
    for comment in (getattr(post, "comments", []) or [])[:3]:
        nickname = str(
            getattr(comment, "nickname", "") or getattr(comment, "uin", "") or ""
        ).strip()
        body = _qzone_compact_text(getattr(comment, "content", ""), limit=80)
        if body:
            comments.append(f"{nickname}: {body}" if nickname else body)
    return "；".join(comments) if comments else "无"


def _qzone_auto_comment_post_summary(post) -> str:
    text = _qzone_compact_text(getattr(post, "text", ""))
    rt_con = _qzone_compact_text(getattr(post, "rt_con", ""))
    fallback_text = (
        _qzone_compact_text(_qzone_post_plain_text(post))
        if not text and not rt_con
        else ""
    )
    images = getattr(post, "images", []) or []
    rt_images = getattr(post, "rt_images", []) or []
    videos = getattr(post, "videos", []) or []
    lines = [
        f"发布者：{getattr(post, 'name', '') or getattr(post, 'uin', '')}",
        f"发布时间：{_format_qzone_local_datetime(getattr(post, 'create_time', 0))}",
        f"发布者正文：{text or fallback_text or '（没有文字）'}",
    ]
    if (
        rt_con
        or rt_images
        or getattr(post, "rt_uin", 0)
        or getattr(post, "rt_uinname", "")
        or getattr(post, "rt_tid", "")
    ):
        source = (
            getattr(post, "rt_uinname", "") or getattr(post, "rt_uin", "") or "未知"
        )
        lines.extend(
            [
                f"转发来源：{source}",
                f"转发正文：{rt_con or '（没有文字）'}",
            ]
        )
    lines.extend(
        [
            f"媒体：{_qzone_media_summary(images=images, rt_images=rt_images, videos=videos)}",
            f"已有评论：{_qzone_comment_preview(post)}",
        ]
    )
    return "\n".join(lines)

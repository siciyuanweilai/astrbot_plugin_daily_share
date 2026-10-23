from __future__ import annotations

import hashlib
from datetime import datetime

from astrbot.api import logger


async def record_qzone_interaction(
    owner,
    post,
    content: str,
    *,
    scene: str,
    comment_id: str = "",
    actor_id: str = "",
    target_comment=None,
    parent_comment=None,
    photo_key: str = "",
) -> None:
    try:
        bridge = getattr(owner.plugin, "daily_life_bridge", None)
        record = getattr(bridge, "record_public_activity", None)
        if not callable(record):
            return
        digest = hashlib.sha256(
            f"{scene}:{post.key}:{comment_id}:{content}".encode()
        ).hexdigest()

        def incoming(comment):
            return {
                "id": str(getattr(comment, "tid", "") or "")[:200],
                "author_id": str(getattr(comment, "uin", "") or "")[:80],
                "author_name": str(getattr(comment, "nickname", "") or "")[:80],
                "content": str(getattr(comment, "content", "") or "")[:1200],
                "reply_to_id": str(getattr(comment, "reply_to_tid", "") or "")[:200],
                "reply_to_author_id": str(getattr(comment, "reply_to_uin", "") or "")[
                    :80
                ],
                "occurred_at": getattr(comment, "create_time", 0),
            }

        conversation = []
        for item in (parent_comment, target_comment):
            if item is not None:
                row = incoming(item)
                if row not in conversation:
                    conversation.append(row)
        await record(
            {
                "event_id": f"{scene}:{digest}",
                "scene": scene,
                "post_id": post.key,
                "comment_id": comment_id,
                "actor_id": actor_id,
                "content": content,
                "post_context": {
                    "author_id": str(getattr(post, "uin", "") or ""),
                    "author_name": str(getattr(post, "name", "") or "")[:80],
                    "content": str(getattr(post, "text", "") or "")[:1600],
                    "occurred_at": getattr(post, "create_time", 0),
                },
                "scope": (
                    "album_batch"
                    if getattr(post, "appid", 311) == 4
                    and getattr(post, "photo_comment_scope", "photo") == "batch"
                    else "album_photo"
                    if getattr(post, "appid", 311) == 4
                    else "post"
                ),
                "photo_key": photo_key,
                "conversation": conversation,
                "reply_to_comment_id": str(
                    getattr(target_comment, "tid", "") or comment_id
                ),
                "reply_to_author_id": str(
                    getattr(target_comment, "uin", "") or actor_id
                ),
                "occurred_at": datetime.now().isoformat(),
            }
        )
    except Exception as exc:
        logger.warning(f"[日常分享] 公开互动已成功，回执登记失败：{type(exc).__name__}")

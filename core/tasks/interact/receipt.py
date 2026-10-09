from __future__ import annotations

import hashlib
from datetime import datetime

from astrbot.api import logger


async def record_qzone_interaction(
    owner, post, content: str, *, scene: str, comment_id: str = "", actor_id: str = ""
) -> None:
    try:
        bridge = getattr(owner.plugin, "daily_life_bridge", None)
        record = getattr(bridge, "record_public_activity", None)
        if not callable(record):
            return
        digest = hashlib.sha256(
            f"{scene}:{post.key}:{comment_id}:{content}".encode()
        ).hexdigest()
        await record(
            {
                "event_id": f"{scene}:{digest}",
                "scene": scene,
                "post_id": post.key,
                "comment_id": comment_id,
                "actor_id": actor_id,
                "content": content,
                "occurred_at": datetime.now().isoformat(),
            }
        )
    except Exception as exc:
        logger.warning(f"[日常分享] 公开互动已成功，回执登记失败：{type(exc).__name__}")

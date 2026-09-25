from __future__ import annotations

from astrbot.api import logger


def qzone_actor_uin(actor) -> str:
    value = str(getattr(actor, "uin", "") or "").strip()
    if not value.isascii() or not value.isdigit() or len(value) > 20:
        return ""
    return str(int(value)) if int(value) > 0 else ""


def qzone_relationship_target(owner, actor) -> str:
    """用空间实际使用的 QQ 客户端定位会话，绝不借用触发人的会话。"""
    uin = qzone_actor_uin(actor)
    if not uin:
        return ""
    try:
        return owner.plugin.qzone_service.relationship_target(uin)
    except Exception as exc:
        logger.debug(f"[日常分享] 无法确认 QQ 空间互动对象会话: {exc}")
    return ""

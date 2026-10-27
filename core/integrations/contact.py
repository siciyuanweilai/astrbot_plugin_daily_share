from __future__ import annotations

import uuid
from contextvars import ContextVar
from functools import wraps

from astrbot.api import logger

from ..database.keys import AUTONOMOUS_SOURCES

current_contact = ContextVar("daily_share_contact", default=None)


class ShareContactChanged(RuntimeError):
    pass


class ShareContactPending(RuntimeError):
    """已准备的内容仍然有效，但暂时无法向该目标发送消息。"""


async def contact(plugin, target, owner, *, action="reserve", expected=None):
    method = getattr(
        getattr(plugin, "daily_life_bridge", None), "coordinate_contact", None
    )
    if not callable(method):
        return {"allowed": True}
    return await method(target, owner=owner, action=action, expected=expected)


def coordinate_share(method):
    @wraps(method)
    async def run(self, *args, **kwargs):
        if kwargs.get("history_source") not in AUTONOMOUS_SOURCES:
            return await method(self, *args, **kwargs)
        target = kwargs["uid"]
        owner = "share:" + uuid.uuid4().hex
        token = None
        try:
            result = await contact(self.plugin, target, owner)
            if not result.get("allowed"):
                logger.debug(
                    f"[日常分享] 本轮主动分享延后：{result.get('reason', '主动任务冲突')}"
                )
                return False
            token = current_contact.set(
                {"target": target, "owner": owner, "snapshot": result.get("snapshot")}
            )
            return await method(self, *args, **kwargs)
        finally:
            if token is not None:
                current_contact.reset(token)
            await contact(self.plugin, target, owner, action="release")

    return run

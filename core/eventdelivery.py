from __future__ import annotations

import asyncio

from astrbot.api.event import AstrMessageEvent, MessageChain


EVENT_SEND_TIMEOUT_SECONDS = 120


async def send_event_message(
    event: AstrMessageEvent,
    chain: MessageChain,
) -> None:
    """发送事件消息，并防止异常平台连接永久占用业务任务。"""
    await asyncio.wait_for(
        event.send(chain),
        timeout=EVENT_SEND_TIMEOUT_SECONDS,
    )


__all__ = ["EVENT_SEND_TIMEOUT_SECONDS", "send_event_message"]

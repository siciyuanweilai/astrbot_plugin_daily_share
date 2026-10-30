"""等待平台实例及连接；暂时离线不等于已经提交消息。"""

from __future__ import annotations

import asyncio
from typing import Any

from .platform import ONEBOT_PLATFORM_TYPES, get_platform_client


class PlatformNotReady(RuntimeError):
    """尚未提交，允许在当前生活和联系状态仍合适时恢复。"""


def onebot_connected(bot: Any) -> bool:
    if not bot:
        return False
    markers = []
    for attr in ("_wsr_api_clients", "_wsr_event_clients"):
        value = getattr(bot, attr, None)
        if value is not None:
            markers.append(value)
    return any(bool(value) for value in markers) if markers else True


async def wait_target_ready(targets: Any, target: str, *, timeout: float = 15.0) -> Any:
    """精确等待指定平台，不因另一个平台离线阻塞全部分享。"""
    deadline = asyncio.get_running_loop().time() + max(0.0, float(timeout))
    while True:
        binding = None
        try:
            binding = targets.ensure_target_platform_routable(str(target or ""))
        except ValueError as exc:
            if "当前不可用" not in str(exc) and "当前没有可绑定" not in str(exc):
                raise
        if binding is not None:
            if binding.platform_type not in ONEBOT_PLATFORM_TYPES:
                return binding
            bot = get_platform_client(binding.instance)
            if onebot_connected(bot):
                return binding
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise PlatformNotReady("目标平台尚未就绪，保留原分享等待连接")
        await asyncio.sleep(min(0.25, remaining))

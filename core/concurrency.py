"""只读准备工作的并发与同键请求协调，不用于发送或发布。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Awaitable


async def gather_readonly(*awaitables: Awaitable[Any]) -> list[Any]:
    """并行读取；失败或取消时回收同组任务，避免卸载后继续运行。"""
    tasks = [asyncio.ensure_future(item) for item in awaitables]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


class KeyedLocks:
    """仅保留有持有者或等待者的锁，避免长期轮询积累动态键。"""

    def __init__(self) -> None:
        self._entries: dict[Any, tuple[asyncio.Lock, int]] = {}

    @asynccontextmanager
    async def hold(self, key: Any):
        lock, users = self._entries.get(key, (asyncio.Lock(), 0))
        self._entries[key] = (lock, users + 1)
        try:
            async with lock:
                yield
        finally:
            _, users = self._entries[key]
            if users == 1:
                del self._entries[key]
            else:
                self._entries[key] = (lock, users - 1)

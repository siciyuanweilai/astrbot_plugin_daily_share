"""公共资料的有界短缓存；不存储模型正文、互动决定或发布结果。"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable
from copy import deepcopy
from time import monotonic
from typing import Any

from ..concurrency import KeyedLocks


class NewsReadCache:
    MAX_ITEMS = 128
    MAX_PENDING_KEYS = 32
    MAX_PENDING_READERS = 128
    FAILURE_TTL_SECONDS = 1.0

    def __init__(self) -> None:
        self._entries = OrderedDict()
        self._locks = KeyedLocks()
        self._slots = asyncio.Semaphore(3)
        self._copy_slots = asyncio.Semaphore(2)
        self._tasks = set()
        self._pending = {}
        self._closed = False
        self._scope = None
        self._revision = 0

    def _ensure_scope(self, scope: Hashable) -> None:
        if scope != self._scope:
            self._scope = scope
            self._revision += 1
            self._entries.clear()

    async def _copy(self, value):
        # 常见短资料直接复制，避免每次命中都调度线程；只检查有限节点。
        remaining = 256

        def small(item, depth=0):
            nonlocal remaining
            remaining -= 1
            if remaining <= 0 or depth > 8:
                return False
            if type(item) in (str, int, float, bool, type(None)):
                return True
            if type(item) is dict and len(item) <= 32:
                return all(
                    type(k) is str and small(v, depth + 1) for k, v in item.items()
                )
            if type(item) is list and len(item) <= 32:
                return all(small(v, depth + 1) for v in item)
            return False

        if small(value):
            return deepcopy(value)
        async with self._copy_slots:
            return await asyncio.to_thread(deepcopy, value)

    async def get(
        self,
        key: Hashable,
        loader: Callable[[], Awaitable[Any]],
        *,
        scope: Callable[[], Hashable],
        ttl: float,
        timeout: float,
    ) -> Any:
        self._ensure_scope(scope())
        if self._closed:
            return None
        revision = self._revision

        def current():
            self._ensure_scope(scope())
            return not self._closed and revision == self._revision

        entry = self._entries.get(key)
        if entry and monotonic() < entry[0]:
            self._entries.move_to_end(key)
            value = entry[1]
            try:
                result = await asyncio.wait_for(self._copy(value), timeout)
            except asyncio.TimeoutError:
                return None
            return result if current() else None

        lock_key = (revision, key)
        if len(self._tasks) >= self.MAX_PENDING_READERS or (
            lock_key not in self._pending
            and len(self._pending) >= self.MAX_PENDING_KEYS
        ):
            return None
        self._pending[lock_key] = self._pending.get(lock_key, 0) + 1
        deadline = monotonic() + timeout

        async def lookup():
            async with self._locks.hold(lock_key):
                if not current():
                    return None
                entry = self._entries.get(key)
                if entry and monotonic() < entry[0]:
                    self._entries.move_to_end(key)
                    value = entry[1]
                else:
                    self._entries.pop(key, None)
                    async with self._slots:
                        if not current():
                            return None
                        try:
                            value = await asyncio.wait_for(
                                loader(), max(0.0, deadline - monotonic())
                            )
                        except Exception:
                            value = None
                    if not current():
                        return None
                    life = ttl if value else self.FAILURE_TTL_SECONDS
                    self._entries[key] = (monotonic() + life, value)
                    self._entries.move_to_end(key)
                    while len(self._entries) > self.MAX_ITEMS:
                        self._entries.popitem(last=False)
            # 调用者不能污染缓存；大载荷复制不会占用事件循环。
            result = await self._copy(value)
            return result if current() else None

        # 结构化等待：取消调用者会回收它拥有的读取，不遗留脱离生命周期的任务。
        task = asyncio.create_task(lookup())
        self._tasks.add(task)
        try:
            return await asyncio.wait_for(task, timeout)
        except asyncio.TimeoutError:
            if current():
                entry = self._entries.get(key)
                if not entry or monotonic() >= entry[0]:
                    self._entries[key] = (monotonic() + self.FAILURE_TTL_SECONDS, None)
                    while len(self._entries) > self.MAX_ITEMS:
                        self._entries.popitem(last=False)
            return None
        finally:
            self._tasks.discard(task)
            remaining = self._pending[lock_key] - 1
            if remaining:
                self._pending[lock_key] = remaining
            else:
                self._pending.pop(lock_key)

    async def close(self) -> None:
        self._closed = True
        self._revision += 1
        self._entries.clear()
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

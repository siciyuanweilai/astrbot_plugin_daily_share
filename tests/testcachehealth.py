"""新闻资料缓存的并发、隔离、失效和资源回收边界。"""

import asyncio
import unittest
from unittest.mock import AsyncMock

from .testnews import _load_news_module


class NewsReadCacheTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cache = _load_news_module().NewsReadCache()
        self.scope = "account-a"
        self.addAsyncCleanup(self.cache.close)

    async def read(self, loader, key="news", **kwargs):
        return await self.cache.get(
            key, loader, scope=lambda: self.scope, ttl=60, timeout=1, **kwargs
        )

    async def test_concurrent_readers_share_one_request_and_receive_copies(self):
        source = [{"title": "新闻", "tags": ["原始"]}]

        async def fetch():
            await asyncio.sleep(0)
            return source

        loader = AsyncMock(side_effect=fetch)
        first, second = await asyncio.gather(self.read(loader), self.read(loader))
        first[0]["tags"].append("调用者修改")
        self.assertEqual(second, source)
        self.assertEqual(await self.read(loader), source)
        loader.assert_awaited_once()

    async def test_source_and_limit_keys_remain_independent(self):
        loader = AsyncMock(side_effect=["weibo-5", "weibo-10", "zhihu-5"])
        keys = [("weibo", 5), ("weibo", 10), ("zhihu", 5)]
        for key, expected in zip(keys, ["weibo-5", "weibo-10", "zhihu-5"]):
            self.assertEqual(await self.read(loader, key), expected)
        self.assertEqual(await self.read(loader, keys[0]), "weibo-5")
        self.assertEqual(loader.await_count, 3)

    async def test_scope_change_discards_cached_result(self):
        loader = AsyncMock(side_effect=["old", "new"])
        self.assertEqual(await self.read(loader), "old")
        self.scope = "account-b"
        self.assertEqual(await self.read(loader), "new")
        self.assertEqual(loader.await_count, 2)

    async def test_scope_change_discards_inflight_result(self):
        started, release = asyncio.Event(), asyncio.Event()

        async def fetch():
            started.set()
            await release.wait()
            return "old"

        pending = asyncio.create_task(self.read(fetch))
        await asyncio.wait_for(started.wait(), 1)
        self.scope = "account-b"
        loader = AsyncMock(return_value="new")
        self.assertEqual(await self.read(loader), "new")
        release.set()
        self.assertIsNone(await pending)
        self.assertEqual(await self.read(loader), "new")
        loader.assert_awaited_once()

    async def test_failure_backoff_allows_recovery_after_expiry(self):
        loader = AsyncMock(side_effect=[RuntimeError("暂不可用"), "recovered"])
        self.assertIsNone(await self.read(loader))
        self.assertIsNone(await self.read(loader))
        loader.assert_awaited_once()
        self.cache._entries["news"] = (0, None)
        self.assertEqual(await self.read(loader), "recovered")
        self.assertEqual(loader.await_count, 2)

    async def test_cancelling_reader_releases_request_and_allows_retry(self):
        started, cancelled = asyncio.Event(), asyncio.Event()

        async def fetch():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        pending = asyncio.create_task(self.read(fetch))
        await asyncio.wait_for(started.wait(), 1)
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        self.assertTrue(cancelled.is_set())
        self.assertFalse(self.cache._tasks)
        self.assertFalse(self.cache._pending)
        self.assertEqual(await self.read(AsyncMock(return_value="retry")), "retry")

    async def test_close_cancels_pending_reads_and_prevents_new_requests(self):
        started = asyncio.Event()

        async def fetch():
            started.set()
            await asyncio.Event().wait()

        pending = asyncio.create_task(self.read(fetch))
        await asyncio.wait_for(started.wait(), 1)
        await self.cache.close()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        loader = AsyncMock(return_value="unexpected")
        self.assertIsNone(await self.read(loader))
        loader.assert_not_awaited()
        self.assertFalse(self.cache._entries)
        self.assertFalse(self.cache._tasks)
        self.assertFalse(self.cache._pending)

    async def test_capacity_evicts_oldest_entry_and_preserves_recent_hit(self):
        self.cache.MAX_ITEMS = 2
        loader = AsyncMock(side_effect=["a", "b", "c", "b-reloaded"])
        await self.read(loader, "a")
        await self.read(loader, "b")
        self.assertEqual(await self.read(loader, "a"), "a")
        await self.read(loader, "c")
        self.assertEqual(len(self.cache._entries), 2)
        self.assertEqual(await self.read(loader, "b"), "b-reloaded")
        self.assertEqual(loader.await_count, 4)

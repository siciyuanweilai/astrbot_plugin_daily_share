"""验证并发请求数、缓存复用、状态失效和取消，不依赖外部模型或发送。"""

import asyncio
import importlib
import types
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, patch

from .testintegration import DailyLifeBridge, _metadata
from .testqzone import _load_qzone_service, _new_qzone_service
from .testqzonecomment import _load_auto_comment_module

from astrbot_plugin_daily_share.core.concurrency import KeyedLocks, gather_readonly


class ReadConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_waiter_releases_reference_without_removing_owner_lock(
        self,
    ):
        locks = KeyedLocks()
        entered, release = asyncio.Event(), asyncio.Event()

        async def owner():
            async with locks.hold("same"):
                entered.set()
                await release.wait()

        first = asyncio.create_task(owner())
        await entered.wait()
        second = asyncio.create_task(owner())
        await asyncio.sleep(0)
        second.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await second
        self.assertEqual(len(locks._entries), 1)
        release.set()
        await first
        self.assertEqual(locks._entries, {})

    async def test_read_failure_cancels_and_joins_other_preparation(self):
        started, stopped = asyncio.Event(), asyncio.Event()

        async def slow():
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                stopped.set()

        async def broken():
            await started.wait()
            raise RuntimeError("读取失败")

        with self.assertRaisesRegex(RuntimeError, "读取失败"):
            await gather_readonly(slow(), broken())
        self.assertTrue(stopped.is_set())


class MemoryCacheTests(unittest.IsolatedAsyncioTestCase):
    def bridge(self, method):
        self.plugin = types.SimpleNamespace(search_share_memories=method)
        self.stars = [_metadata(self.plugin)]
        return DailyLifeBridge(types.SimpleNamespace(get_all_stars=lambda: self.stars))

    async def test_simultaneous_same_query_searches_once_and_targets_stay_isolated(
        self,
    ):
        async def search(query, target, **kwargs):
            await asyncio.sleep(0)
            return [{"text": target}]

        method = AsyncMock(side_effect=search)
        bridge = self.bridge(method)
        results = await gather_readonly(
            *(bridge.related_memory_prompt("周末", "a") for _ in range(8))
        )
        self.assertEqual(method.await_count, 1)
        self.assertEqual(len(set(results)), 1)
        self.assertIn("b", await bridge.related_memory_prompt("周末", "b"))
        self.assertEqual(method.await_count, 2)
        self.assertEqual(bridge._memory_locks._entries, {})

    async def test_reload_discards_same_target_same_query_cache(self):
        bridge = self.bridge(AsyncMock(return_value=[{"text": "旧实例"}]))
        self.assertIn("旧实例", await bridge.related_memory_prompt("周末", "a"))
        new_method = AsyncMock(return_value=[{"text": "新实例"}])
        self.stars[:] = [
            _metadata(types.SimpleNamespace(search_share_memories=new_method))
        ]
        self.assertIn("新实例", await bridge.related_memory_prompt("周末", "a"))
        new_method.assert_awaited_once()

    async def test_activity_invalidation_during_lookup_cannot_revive_old_cache(self):
        started, release = asyncio.Event(), asyncio.Event()

        async def search(*args, **kwargs):
            started.set()
            await release.wait()
            return [{"text": "旧背景"}]

        method = AsyncMock(side_effect=search)
        bridge = self.bridge(method)
        pending = asyncio.create_task(bridge.related_memory_prompt("周末", "a"))
        await started.wait()
        await bridge.record_public_activity({})
        release.set()
        await pending
        method.side_effect = None
        method.return_value = [{"text": "新活动"}]
        self.assertIn("新活动", await bridge.related_memory_prompt("周末", "a"))
        self.assertEqual(method.await_count, 2)


class QzoneCachePerformanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.module = _load_qzone_service()
        self.service = _new_qzone_service(self.module)

    async def test_concurrent_detail_requests_fetch_once(self):
        async def fetch(post):
            await asyncio.sleep(0)
            return replace(post, text="完整详情")

        self.service.details._fetch_detail = AsyncMock(side_effect=fetch)
        results = await gather_readonly(
            *(self.service.detail("101:post") for _ in range(8))
        )
        self.service.details._fetch_detail.assert_awaited_once()
        self.assertTrue(all(item.text == "完整详情" for item in results))
        self.assertEqual(self.service.details._locks._entries, {})

    async def test_account_switch_while_waiting_cannot_return_other_account_cache(self):
        old_bot, new_bot = object(), object()
        self.service._get_bot = lambda: old_bot
        self.service._ensure_bot_cache_scope()
        self.service.details._fetch_detail = AsyncMock()
        async with self.service.details._locks.hold((id(old_bot), "101:post")):
            pending = asyncio.create_task(self.service.detail("101:post"))
            await asyncio.sleep(0)
            self.service._get_bot = lambda: new_bot
            self.service._ensure_bot_cache_scope()
            self.service._remember_posts(
                [self.module.QzonePost(uin=101, tid="post", text="新账号资料")],
                detailed=True,
            )
        with self.assertRaisesRegex(RuntimeError, "实例已变化"):
            await pending
        self.service.details._fetch_detail.assert_not_awaited()
        self.assertEqual(self.service.details._locks._entries, {})

    async def test_account_switch_while_waiting_for_slot_stops_old_fetch(self):
        old_bot, new_bot = object(), object()
        self.service._get_bot = lambda: old_bot
        self.service.details._slots = asyncio.Semaphore(0)
        self.service.details._fetch_detail = AsyncMock()
        pending = asyncio.create_task(self.service.detail("101:post"))
        await asyncio.sleep(0)
        self.service._get_bot = lambda: new_bot
        self.service.details._slots.release()
        with self.assertRaisesRegex(RuntimeError, "实例已变化"):
            await pending
        self.service.details._fetch_detail.assert_not_awaited()

    async def test_cancelled_detail_releases_lock_and_retry_fetches(self):
        started = asyncio.Event()

        async def fetch(post):
            started.set()
            await asyncio.Event().wait()

        self.service.details._fetch_detail = AsyncMock(side_effect=fetch)
        pending = asyncio.create_task(self.service.detail("101:post"))
        await started.wait()
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        self.assertEqual(self.service.details._locks._entries, {})
        self.assertIsNone(self.service._cached_detail_post("101:post"))
        self.service.details._fetch_detail.side_effect = lambda post: post
        self.assertEqual((await self.service.detail("101:post")).key, "101:post")

    def test_summary_replacement_cannot_inherit_old_detail_cache_marker(self):
        post = self.module.QzonePost(uin=101, tid="post", text="完整详情")
        self.service._remember_posts([post], detailed=True)
        self.service._remember_posts([replace(post, text="新列表摘要")])
        self.assertIsNone(self.service._cached_detail_post("101:post"))

    async def test_failed_batch_comment_refresh_does_not_cache_fallback_as_detail(self):
        photobatch = importlib.import_module(self.module.__package__ + ".photobatch")
        post = types.SimpleNamespace(
            key="101:batch",
            uin=101,
            photo_comment_scope="batch",
            comment_target_error="",
            photo_batch_topic_id="topic",
            comments=[],
        )
        self.service.context = AsyncMock(
            return_value=self.module.QzoneContext(101, "s", "p")
        )
        self.service._request = AsyncMock(return_value={"code": -1})
        self.assertIs(await photobatch.refresh_batch_comments(self.service, post), post)
        self.assertIsNone(self.service._cached_detail_post(post.key))
        self.assertIs(self.service._require_post(post.key), post)
        await photobatch.refresh_batch_comments(self.service, post)
        self.assertEqual(self.service._request.await_count, 2)
        self.assertIsNone(self.service._cached_detail_post(post.key))

    async def test_detail_reads_overlap_with_global_limit_of_three_and_keep_order(self):
        active, peak = 0, 0
        three_started, release = asyncio.Event(), asyncio.Event()

        async def fetch(post):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if active == 3:
                three_started.set()
            try:
                await release.wait()
                return post
            finally:
                active -= 1

        self.service.details._fetch_detail = fetch
        keys = [f"101:{i}" for i in range(8)]
        pending = asyncio.create_task(
            gather_readonly(*(self.service.detail(key) for key in keys))
        )
        await asyncio.wait_for(three_started.wait(), 1)
        self.assertEqual(peak, 3)
        release.set()
        results = await pending
        self.assertEqual([post.key for post in results], keys)
        self.assertEqual(peak, 3)

    async def test_invalidated_inflight_detail_does_not_restore_cache(self):
        started, release = asyncio.Event(), asyncio.Event()

        async def fetch(post):
            started.set()
            await release.wait()
            return post

        self.service.details._fetch_detail = AsyncMock(side_effect=fetch)
        pending = asyncio.create_task(self.service.detail("101:post"))
        await started.wait()
        self.service._invalidate_qzone_cache(post_id="101:post")
        release.set()
        await pending
        self.assertIsNone(self.service._cached_detail_post("101:post"))
        await self.service.detail("101:post")
        self.assertEqual(self.service.details._fetch_detail.await_count, 2)

    async def test_failed_list_detail_can_be_retried_immediately(self):
        self.service.context = AsyncMock(
            return_value=self.module.QzoneContext(101, "s", "p")
        )
        self.service._request = AsyncMock(
            return_value={
                "code": 0,
                "msglist": [{"uin": 101, "tid": "post", "content": "列表摘要"}],
            }
        )
        self.service.details._fetch_detail = AsyncMock(
            side_effect=RuntimeError("临时失败")
        )
        posts = await self.service.query_posts(with_detail=True)
        self.assertEqual(posts[0].text, "列表摘要")
        self.assertIsNone(self.service._cached_detail_post("101:post"))
        self.service.details._fetch_detail.side_effect = None
        self.service.details._fetch_detail.return_value = replace(
            posts[0], text="恢复详情"
        )
        self.assertEqual((await self.service.detail("101:post")).text, "恢复详情")
        self.assertEqual(self.service.details._fetch_detail.await_count, 2)

    async def test_successful_like_preserves_lists_and_updates_every_cached_copy(self):
        post = self.module.QzonePost(uin=101, tid="post", text="照片")
        other_copy = replace(post)
        self.service._remember_posts([post], detailed=True)
        self.service._store_query_posts(("recent",), [other_copy])
        self.service.context = AsyncMock(
            return_value=self.module.QzoneContext(202, "s", "p")
        )
        self.service._request = AsyncMock(return_value={"code": 0})
        await self.service.like(post.key)
        self.assertTrue(self.service._cached_query_posts(("recent",))[0].liked)
        self.assertTrue(self.service._cached_detail_post(post.key).liked)
        await self.service.like(post.key)
        self.service._request.assert_awaited_once()

    async def test_hot_detail_and_query_survive_cache_pressure(self):
        service = self.service
        service.POST_CACHE_MAX_ITEMS = service.QUERY_CACHE_MAX_ITEMS = 2
        posts = [self.module.QzonePost(uin=101, tid=str(i)) for i in range(3)]
        for post in posts[:2]:
            service._remember_posts([post], detailed=True)
            service._store_query_posts((post.key,), [post])
        service._cached_detail_post(posts[0].key)
        service._cached_query_posts((posts[0].key,))
        service._remember_posts([posts[2]], detailed=True)
        service._store_query_posts((posts[2].key,), [posts[2]])
        self.assertIsNotNone(service._cached_detail_post(posts[0].key))
        self.assertIsNotNone(service._cached_query_posts((posts[0].key,)))
        self.assertIsNone(service._cached_detail_post(posts[1].key))
        self.assertIsNone(service._cached_query_posts((posts[1].key,)))


class InteractionPreparationTests(unittest.IsolatedAsyncioTestCase):
    async def test_unchanged_hot_image_cache_skips_model_and_database_write(self):
        module, models = _load_auto_comment_module()
        sight = importlib.import_module(module.__package__ + ".interact.sight")
        post = models.QzonePost(uin=101, tid="hot", text="照片")
        refs = [(post, "正文配图", "https://example.com/hot.jpg")]
        keys = sight._qzone_image_vision_cache_keys(
            post, refs[0][2], index=1, total=1, scope="正文配图"
        )
        state = {"image_vision_cache": {key: "咖啡" for key in keys}}
        with (
            patch.object(sight, "_enabled_qzone_image_refs", return_value=refs),
            patch.object(sight, "_describe_qzone_image", AsyncMock()) as describe,
            patch.object(sight, "_save_qzone_image_vision_cache", AsyncMock()) as save,
        ):
            result = await sight._qzone_image_refs_descriptions(
                types.SimpleNamespace(), refs, state=state
            )
        self.assertEqual(result, [(1, "正文配图", "咖啡")])
        describe.assert_not_awaited()
        save.assert_not_awaited()

    async def test_recent_expression_excludes_unknown_submission_and_current_post(self):
        module, models = _load_auto_comment_module()
        dialogue = importlib.import_module(module.__package__ + ".interact.dialogue")
        post = models.QzonePost(uin=101, tid="current", text="照片")
        state = {
            "processed": {
                "confirmed": {"action": "commented", "content": "已经发送的公开短句"},
                "alias": {"action": "commented", "content": "已经发送的公开短句"},
                "uncertain": {
                    "action": "commented",
                    "content": "不确定是否发出",
                    "submission_unknown": True,
                },
                post.key: {"action": "commented", "content": "当前动态原评论"},
                "pending": {"action": "pending", "content": "还没发出"},
            }
        }
        prompt = dialogue._recent_comment_expression(state, post)
        self.assertEqual(prompt.count("已经发送的公开短句"), 1)
        for excluded in ("不确定是否发出", "当前动态原评论", "还没发出"):
            self.assertNotIn(excluded, prompt)

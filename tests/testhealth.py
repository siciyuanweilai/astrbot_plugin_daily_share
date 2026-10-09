import asyncio
import importlib
import json
import tempfile
import threading
import time
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from . import testfailure, testidentity, testmedia, testmetrics, testqzonecomment
from .testqzone import _load_qzone_service, _new_qzone_service


def _account_service():
    module = _load_qzone_service()
    bots = {
        name: types.SimpleNamespace(uin=uin) for name, uin in (("a", 101), ("b", 202))
    }
    calls = []

    async def action(bot, name, **kwargs):
        calls.append((bot, name))
        if name == "get_cookies":
            return {"cookies": f"uin=o{bot.uin}; p_skey=test-{bot.uin}"}
        return {"nickname": str(bot.uin)}

    plugin = types.SimpleNamespace(
        qzone_conf={"qzone_adapter_id": "a"},
        _cached_qq_adapter_id="a",
        ctx_service=types.SimpleNamespace(
            bot_map=bots,
            get_bot_instance=lambda adapter_id: bots.get(adapter_id),
            get_onebot_bot=lambda **kwargs: bots.get(kwargs.get("adapter_id")),
            is_onebot_platform=lambda adapter_id: adapter_id in bots,
            call_onebot_action=action,
        ),
    )
    return _new_qzone_service(module, plugin), plugin, bots, calls


class AccountIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_switch_during_post_does_not_retry_as_new_account(self):
        service, plugin, _, _ = _account_service()
        await service.context()
        requests = []

        class Response:
            status = 401

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def text(self):
                plugin.qzone_conf["qzone_adapter_id"] = "b"
                return '{"code":-100}'

        def request(*args, **kwargs):
            requests.append(kwargs)
            return Response()

        service._http = lambda: asyncio.sleep(
            0, result=types.SimpleNamespace(request=request)
        )
        with self.assertRaisesRegex(RuntimeError, "提交状态未知"):
            await service._request("POST", "https://example.com/submit")
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["cookies"]["uin"], "o101")
        self.assertIsNone(service._ctx)

    async def test_account_change_discards_login_and_query_caches(self):
        service, plugin, _, _ = _account_service()
        first = await service.context()
        service._store_query_posts(("recent",), [object()])
        service._post_cache["101:old"] = object()
        service._last_friend_feeds_meta = {"account": 101}
        plugin.qzone_conf["qzone_adapter_id"] = "b"

        self.assertIsNone(service._cached_query_posts(("recent",)))
        self.assertEqual(service._post_cache, {})
        self.assertEqual(service._last_friend_feeds_meta, {})
        second = await service.context()
        self.assertEqual((first.uin, second.uin), (101, 202))
        self.assertIsNot(first, second)

    async def test_explicit_adapter_is_not_changed_by_chat_event_adapter(self):
        service, plugin, _, calls = _account_service()
        first = await service.context()
        call_count = len(calls)
        plugin._cached_qq_adapter_id = "b"
        self.assertIs(await service.context(), first)
        self.assertEqual(len(calls), call_count)

    async def test_account_change_during_cookie_fetch_rejects_mixed_context(self):
        service, plugin, bots, calls = _account_service()
        original = plugin.ctx_service.call_onebot_action

        async def switching_action(bot, name, **kwargs):
            result = await original(bot, name, **kwargs)
            plugin.qzone_conf["qzone_adapter_id"] = "b"
            return result

        plugin.ctx_service.call_onebot_action = switching_action
        with self.assertRaisesRegex(RuntimeError, "实例.*变化"):
            await service.context()
        self.assertIsNone(service._ctx)
        self.assertTrue(all(bot is bots["a"] for bot, _ in calls))
        self.assertEqual((await service.context()).uin, 202)

    async def test_missing_explicit_adapter_cannot_reuse_previous_login(self):
        service, plugin, _, _ = _account_service()
        await service.context()
        plugin.qzone_conf["qzone_adapter_id"] = "missing"
        with self.assertRaisesRegex(RuntimeError, "没有可用"):
            await service.context()
        self.assertIsNone(service._ctx)


class ChatAndModelHealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_busy_database_workers_do_not_hold_normal_chat_hook(self):
        module = testmedia._load_main_module()
        plugin = testmedia._new_plugin_with_support(module)
        db_module = testmetrics._load_db_module()
        with tempfile.TemporaryDirectory() as directory:
            plugin.db = db_module.DatabaseManager(Path(directory))
            release = threading.Event()
            started = [threading.Event(), threading.Event()]

            def busy(index):
                started[index].set()
                release.wait(2)

            workers = [
                asyncio.create_task(plugin.db._execute(busy, index))
                for index in range(2)
            ]
            try:
                self.assertTrue(
                    await asyncio.to_thread(
                        lambda: all(event.wait(1) for event in started)
                    )
                )
                req = types.SimpleNamespace(
                    system_prompt="persona",
                    func_tool=types.SimpleNamespace(names=lambda: ["qzone"]),
                    extra_user_content_parts=[],
                )
                begin = time.monotonic()
                await plugin.inject_tool_context(
                    types.SimpleNamespace(unified_msg_origin="session"), req
                )
                self.assertLess(time.monotonic() - begin, 0.35)
                self.assertEqual(req.extra_user_content_parts, [])
            finally:
                release.set()
                await asyncio.gather(*workers)
                await plugin.db.close()

    async def test_default_model_budget_uses_config_and_explicit_budget_is_preserved(
        self,
    ):
        module = testmedia._load_main_module()
        plugin = object.__new__(module.DailySharePlugin)
        plugin.llm_service = module.LlmService(
            types.SimpleNamespace(),
            {"llm_timeout": 120, "llm_provider_id": "test"},
            lambda: False,
        )
        budgets = []

        async def attempt(**kwargs):
            budgets.append(kwargs["timeout"])
            return "ok", "test", False

        plugin.llm_service._llm_attempt = attempt
        await plugin.call_llm("test", max_retries=0)
        await plugin.call_llm("test", timeout=10, max_retries=0)
        self.assertGreater(budgets[0], 119)
        self.assertLessEqual(budgets[0], 120)
        self.assertGreater(budgets[1], 9)
        self.assertLessEqual(budgets[1], 10)

    async def test_cache_usage_counts_only_provider_reported_tokens(self):
        module = testmedia._load_main_module()
        service = module.LlmService(types.SimpleNamespace(), {}, lambda: False)
        service._record_token_usage(types.SimpleNamespace(usage=None), "test")
        service._record_token_usage(
            types.SimpleNamespace(
                usage=types.SimpleNamespace(input_other=20, input_cached=80, output=10)
            ),
            "test",
        )
        self.assertEqual(
            service.token_usage,
            {
                "reported_calls": 1,
                "input_tokens": 100,
                "cached_input_tokens": 80,
                "output_tokens": 10,
            },
        )

    async def test_context_hook_shares_short_budget_and_preserves_system_prompt(self):
        module = testmedia._load_main_module()
        plugin = testmedia._new_plugin_with_support(module)
        helper = plugin.support_service.operations.tool_context
        qzone_calls = []

        async def busy_builder(target):
            await asyncio.sleep(1)
            return "unexpected"

        async def qzone_builder(target):
            qzone_calls.append(target)
            await asyncio.sleep(1)
            return "unexpected"

        helper._build_news_link_context_prompt = busy_builder
        helper._build_qzone_context_prompt = qzone_builder
        req = types.SimpleNamespace(
            system_prompt="persona",
            func_tool=types.SimpleNamespace(names=lambda: ["news_link", "qzone"]),
            extra_user_content_parts=[],
        )
        started = time.monotonic()
        await plugin.inject_tool_context(
            types.SimpleNamespace(unified_msg_origin="session"), req
        )
        self.assertLess(time.monotonic() - started, 0.35)
        self.assertEqual(qzone_calls, [])
        self.assertEqual(req.system_prompt, "persona")
        self.assertEqual(req.extra_user_content_parts, [])

    async def test_empty_context_cache_is_session_scoped_and_invalidatable(self):
        module = testmedia._load_main_module()
        helper = testmedia._new_plugin_with_support(
            module
        ).support_service.operations.tool_context
        calls = []

        async def builder(target):
            calls.append(target)
            return ""

        for target in ("a", "a", "b"):
            await helper.cached_context_prompt("qzone", target, builder, timeout=0.1)
        self.assertEqual(calls, ["a", "b"])
        helper._invalidate_context_prompt("qzone", "a")
        await helper.cached_context_prompt("qzone", "a", builder, timeout=0.1)
        self.assertEqual(calls, ["a", "b", "a"])

    async def test_repeated_context_hook_does_not_duplicate_or_overwrite_parts(self):
        module = testmedia._load_main_module()
        plugin = testmedia._new_plugin_with_support(module)
        helper = plugin.support_service.operations.tool_context
        helper._build_qzone_context_prompt = lambda target: asyncio.sleep(
            0, result=helper._QZONE_CONTEXT_MARKER + "\npost_id=101:tid"
        )
        req = types.SimpleNamespace(
            system_prompt="persona",
            func_tool=types.SimpleNamespace(names=lambda: ["qzone"]),
            extra_user_content_parts=[{"type": "text", "text": "user input"}],
        )
        event = types.SimpleNamespace(unified_msg_origin="session")
        await plugin.inject_tool_context(event, req)
        await plugin.inject_tool_context(event, req)
        self.assertEqual(req.system_prompt, "persona")
        self.assertEqual(len(req.extra_user_content_parts), 2)
        self.assertEqual(req.extra_user_content_parts[0]["text"], "user input")
        self.assertIn(
            helper._QZONE_CONTEXT_MARKER, req.extra_user_content_parts[1].text
        )
        self.assertEqual(
            req.extra_user_content_parts[1].model_dump_for_context()["type"], "text"
        )


class CacheHealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_interaction_metadata_save_preserves_newer_vision_cache(self):
        module, _ = testqzonecomment._load_auto_comment_module()
        db = testqzonecomment.FakeDb()
        await db.set_qzone_state("test", {"image_vision_cache": {"new": "correct"}})
        stale_state = {"image_vision_cache": {"old": "stale"}}
        await module.TaskQzoneAutoCommentService._qzone_auto_save_state(
            types.SimpleNamespace(db=db),
            "test",
            stale_state,
            {"done": {"action": "comment"}},
            {"commented": 1},
            run_at=123,
        )
        state = await db.get_qzone_state("test", {})
        self.assertEqual(state["image_vision_cache"], {"new": "correct"})
        self.assertEqual(state["last_run_at"], 123)
        self.assertIn("done", state["processed"])

    async def test_cancelled_short_url_waiter_does_not_leak_lock(self):
        tasks = testfailure._load_tasks_module()
        plugin = testfailure._Plugin()
        started, release = asyncio.Event(), asyncio.Event()

        async def shorten(url):
            started.set()
            await release.wait()
            return "https://short.example/a"

        plugin.news_service.shorten_url = shorten
        formatter = testfailure._new_manager(tasks, plugin).snapshot_store
        first = asyncio.create_task(
            formatter._shorten_news_url("https://example.com/a")
        )
        await started.wait()
        second = asyncio.create_task(
            formatter._shorten_news_url("https://example.com/a")
        )
        await asyncio.sleep(0)
        second.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await second
        release.set()
        self.assertEqual(await first, "https://short.example/a")
        self.assertEqual(formatter._news_short_url_locks, {})

    async def test_concurrent_cache_merge_is_atomic_bounded_and_preserves_metadata(
        self,
    ):
        module = testmetrics._load_db_module()
        with tempfile.TemporaryDirectory() as directory:
            db = module.DatabaseManager(Path(directory))
            try:
                await db.set_qzone_state("test", {"processed": ["keep"]})
                await asyncio.gather(
                    *(
                        db.merge_cache_entries(
                            "qzone",
                            "test",
                            {str(index): index},
                            max_items=30,
                            cache_field="image_vision_cache",
                        )
                        for index in range(20)
                    )
                )
                state = await db.get_qzone_state("test", {})
                self.assertEqual(state["processed"], ["keep"])
                self.assertEqual(
                    state["image_vision_cache"],
                    {str(index): index for index in range(20)},
                )
                await db.merge_cache_entries(
                    "qzone",
                    "test",
                    {"new": 99},
                    max_items=5,
                    cache_field="image_vision_cache",
                )
                state = await db.get_qzone_state("test", {})
                self.assertEqual(len(state["image_vision_cache"]), 5)
                self.assertEqual(state["image_vision_cache"]["new"], 99)
            finally:
                await db.close()

    async def test_vision_cache_save_does_not_restore_evicted_entries(self):
        module, _ = testqzonecomment._load_auto_comment_module()
        sight = importlib.import_module(module.__package__ + ".interact.sight")
        db_module = testmetrics._load_db_module()
        with tempfile.TemporaryDirectory() as directory:
            db = db_module.DatabaseManager(Path(directory))
            try:
                original = {
                    str(index): {"description": str(index)} for index in range(200)
                }
                await db.set_qzone_state(
                    "test", {"image_vision_cache": original, "processed": ["keep"]}
                )
                state = {"image_vision_cache": dict(original)}
                updates = {f"new-{index}": {"description": "new"} for index in range(5)}
                await sight._save_qzone_image_vision_cache(
                    types.SimpleNamespace(db=db),
                    state,
                    state_key="test",
                    updates=updates,
                )
                saved = await db.get_qzone_state("test", {})
                self.assertEqual(len(saved["image_vision_cache"]), 200)
                self.assertNotIn("0", saved["image_vision_cache"])
                self.assertEqual(saved["processed"], ["keep"])
                self.assertEqual(
                    state["image_vision_cache"], saved["image_vision_cache"]
                )
            finally:
                await db.close()

    async def test_image_cache_aliases_require_actual_identity_but_allow_token_rotation(
        self,
    ):
        module, models = testqzonecomment._load_auto_comment_module()
        sight = importlib.import_module(module.__package__ + ".interact.sight")
        post = models.QzonePost(uin=101, tid="same", text="same", create_time=123)

        def keys(url):
            return set(
                sight._qzone_image_vision_cache_keys(post, url, index=1, total=1)
            )

        self.assertEqual(
            keys("https://example.com/a.jpg?token=old"),
            keys("https://example.com/a.jpg?token=new"),
        )
        self.assertFalse(
            keys("https://example.com/a.jpg") & keys("https://example.com/b.jpg")
        )

    async def test_different_short_urls_keep_both_concurrent_writes(self):
        tasks = testfailure._load_tasks_module()
        plugin = testfailure._Plugin()
        module = testmetrics._load_db_module()
        with tempfile.TemporaryDirectory() as directory:
            plugin.db = module.DatabaseManager(Path(directory))

            async def shorten(url):
                await asyncio.sleep(0.02)
                return url + "/short"

            plugin.news_service.shorten_url = shorten
            manager = testfailure._new_manager(tasks, plugin)
            formatter = manager.snapshot_store
            try:
                urls = ["https://example.com/a", "https://example.com/b"]
                self.assertEqual(
                    await asyncio.gather(
                        *(formatter._shorten_news_url(url) for url in urls)
                    ),
                    [url + "/short" for url in urls],
                )
                self.assertEqual(
                    set(await plugin.db.get_cache_state("news_short_url_cache", {})),
                    set(urls),
                )
                self.assertEqual(formatter._news_short_url_locks, {})
            finally:
                await plugin.db.close()

    async def test_same_short_url_uses_one_request_and_releases_lock(self):
        tasks = testfailure._load_tasks_module()
        plugin = testfailure._Plugin()
        calls = []

        async def shorten(url):
            calls.append(url)
            await asyncio.sleep(0.02)
            return "https://short.example/a"

        plugin.news_service.shorten_url = shorten
        formatter = testfailure._new_manager(tasks, plugin).snapshot_store
        results = await asyncio.gather(
            *(formatter._shorten_news_url("https://example.com/a") for _ in range(5))
        )
        self.assertEqual(calls, ["https://example.com/a"])
        self.assertEqual(results, ["https://short.example/a"] * 5)
        self.assertEqual(formatter._news_short_url_locks, {})


class LogTranslationTests(unittest.TestCase):
    def test_candidate_skip_log_translates_label_and_preserves_reason_code(self):
        module, models = testqzonecomment._load_auto_comment_module()
        candidate = importlib.import_module(module.__package__ + ".interact.candidate")
        post = models.QzonePost(uin=101, tid="test", name="动态作者")
        comment = models.QzoneComment(uin=202, nickname="评论人")
        cases = (
            ("photo_reply_not_to_bot", "相册回复未明确指向机器人"),
            ("already_processed", "已处理该评论"),
            (
                "synthetic_thread_tid_without_real_submit_id",
                "楼层仅有合成 tid，缺少真实提交 ID",
            ),
            ("原因已是中文", "原因已是中文"),
            ("unknown_future_code", "unknown_future_code"),
        )
        for reason, translated in cases:
            with (
                self.subTest(reason=reason),
                patch.object(candidate.logger, "debug") as log,
            ):
                candidate._log_qzone_candidate_skip(
                    "相册自动回评", reason, post, comment
                )
                message = log.call_args.args[0]
                self.assertIn(f"原因={translated}", message)
                self.assertIn(reason, message)
                self.assertIn("动态=动态作者，评论=评论人", message)

    def test_model_usage_log_translates_labels_and_preserves_token_metric(self):
        module = testmedia._load_main_module()
        model = importlib.import_module(module.__package__ + ".core.host.model")
        service = module.LlmService(types.SimpleNamespace(), {}, lambda: False)
        response = types.SimpleNamespace(
            usage=types.SimpleNamespace(input_other=20, input_cached=80, output=10)
        )
        with patch.object(model.logger, "debug") as log:
            service._record_token_usage(response, "test-provider")
        message = log.call_args.args[0]
        self.assertIn("服务提供商=test-provider", message)
        self.assertIn("输入 token=100", message)
        self.assertIn("缓存输入 token（cached_input）=80", message)
        self.assertIn("输出 token=10", message)
        self.assertEqual(service.token_usage["cached_input_tokens"], 80)


class VisualHealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_nonperson_composition_survives_mode_enforcement(self):
        _, module = testidentity._load_daily_share_modules()
        service = module.ImageService(
            types.SimpleNamespace(), {}, lambda **kwargs: None
        )
        for mode, subject in (("object", "a cup"), ("landscape", "无")):
            with self.subTest(mode=mode):
                visuals = service._enforce_visual_mode(
                    {
                        "visual_mode": mode,
                        "subject": subject,
                        "composition": "close view",
                        "frame_logic": "focus on subject",
                    },
                    False,
                )
                self.assertEqual(
                    service._resolve_composition(visuals, False),
                    ("close view", "focus on subject"),
                )

    async def test_visual_system_prefix_stays_stable_when_current_hour_changes(self):
        _, module = testidentity._load_daily_share_modules()
        calls = []

        async def call_llm(prompt, system_prompt="", **kwargs):
            calls.append((prompt, system_prompt))
            return json.dumps({"visual_mode": "object", "subject": "cup"})

        service = module.ImageService(types.SimpleNamespace(), {}, call_llm)
        extraction = importlib.import_module(module.__package__ + ".vision.extract")
        for hour in (9, 10):
            with patch.object(
                extraction,
                "datetime",
                types.SimpleNamespace(now=lambda: datetime(2026, 10, 5, hour)),
            ):
                await service._agent_extract_visuals("a cup", None, involves_self=False)
        self.assertEqual(calls[0][1], calls[1][1])
        self.assertNotEqual(calls[0][0], calls[1][0])
        self.assertIn("当前小时：9:00", calls[0][0])
        self.assertIn("当前小时：10:00", calls[1][0])

"""已复现的取消、锁竞态、人设和错误分类缺陷回归；不调用外部服务。"""

import asyncio
import importlib
import types
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, patch

from . import testidentity, testmedia, testqzonecomment


def interaction(kind, *, posts_count=1, db=None):
    module, models = testqzonecomment._load_auto_comment_module()
    posts = [
        models.QzonePost(
            uin=1 if kind == "reply" else 3,
            tid=f"post-{index}",
            name="friend",
            text="今天很开心",
            comments=[
                models.QzoneComment(uin=2, nickname="friend", content="真好", tid="c1")
            ]
            if kind == "reply"
            else [],
        )
        for index in range(posts_count)
    ]
    service = types.SimpleNamespace(
        context=AsyncMock(return_value=types.SimpleNamespace(uin=1)),
        query_recent_posts=AsyncMock(return_value=posts),
        query_posts=AsyncMock(return_value=posts),
        comment=AsyncMock(),
        reply_comment=AsyncMock(),
    )
    manager = module.TaskQzoneAutoCommentService(
        *testqzonecomment._interaction_args(module)
    )
    manager.config.qzone = {
        "enable_qzone": True,
        f"qzone_enable_auto_{kind}": True,
        f"qzone_auto_{kind}_limit": posts_count,
    }
    manager.runtime = replace(
        manager.runtime,
        db=db or testqzonecomment.FakeDb(),
        plugin=types.SimpleNamespace(
            _is_terminated=False,
            qzone_service=service,
            emit_dashboard_event=lambda *a, **kw: None,
            call_llm=AsyncMock(return_value="真不错"),
        ),
    )
    return module, manager, service


class ConfirmedActionTests(unittest.IsolatedAsyncioTestCase):
    async def test_comment_and_reply_are_saved_before_cancellation(self):
        async def cancel_delay(_):
            raise asyncio.CancelledError

        for kind in ("comment", "reply"):
            with self.subTest(kind=kind):
                module, owner, service = interaction(kind)
                with patch.object(module.asyncio, "sleep", cancel_delay):
                    with self.assertRaises(asyncio.CancelledError):
                        await getattr(owner, f"execute_qzone_auto_{kind}")()
                sender = service.comment if kind == "comment" else service.reply_comment
                self.assertEqual(sender.await_count, 1)
                key = getattr(module, f"QZONE_AUTO_{kind.upper()}_STATE_KEY")
                records = owner.db.state[key]["processed"]
                self.assertTrue(
                    any(
                        item.get("action") in ("commented", "replied")
                        for item in records.values()
                    )
                )

    async def test_database_failure_stops_before_next_submission(self):
        class BrokenDb(testqzonecomment.FakeDb):
            async def update_qzone_state(self, key, updates):
                raise RuntimeError("database unavailable")

        _, owner, service = interaction("comment", posts_count=2, db=BrokenDb())
        task = importlib.import_module(
            owner.__module__.rsplit(".", 1)[0] + ".interact.task"
        )
        with self.assertRaises(task.QzoneStatePersistenceError):
            await owner.execute_qzone_auto_comment()
        self.assertEqual(service.comment.await_count, 1)

    async def test_checkpoint_finishes_snapshot_despite_repeated_cancellation(self):
        module, _, _ = interaction("comment")
        task_module = importlib.import_module(module.__package__ + ".interact.task")
        entered, release = asyncio.Event(), asyncio.Event()
        writes = []

        async def save(key, state, processed, result):
            entered.set()
            await release.wait()
            writes.append(processed)

        processed = {"confirmed": {"action": "commented"}}
        task = asyncio.create_task(
            task_module.checkpoint_qzone_action(
                types.SimpleNamespace(_qzone_auto_save_state=save),
                "state",
                {},
                processed,
                {},
            )
        )
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        processed["later"] = {}
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1)
        self.assertEqual(writes, [{"confirmed": {"action": "commented"}}])

    async def test_checkpoint_timeout_is_bounded_and_visible(self):
        module, _, _ = interaction("comment")
        task_module = importlib.import_module(module.__package__ + ".interact.task")
        owner = types.SimpleNamespace(
            _qzone_auto_save_state=AsyncMock(side_effect=lambda *a: None)
        )

        async def blocked(*args):
            await asyncio.Event().wait()

        owner._qzone_auto_save_state = blocked
        with patch.object(task_module, "QZONE_CHECKPOINT_TIMEOUT_SECONDS", 0.01):
            with self.assertRaises(task_module.QzoneStatePersistenceError):
                await asyncio.wait_for(
                    task_module.checkpoint_qzone_action(owner, "s", {}, {}, {}), 1
                )


class TargetLockTests(unittest.IsolatedAsyncioTestCase):
    async def test_waiter_keeps_original_lock_through_release_and_reclamation(self):
        main = testmedia._load_main_module()
        runtime = main.RuntimeService(
            types.SimpleNamespace(_lock=asyncio.Lock(), _target_locks={})
        )
        lock = runtime.get_share_lock("same-target")
        await lock.acquire()
        waiter = asyncio.create_task(lock.acquire())
        await asyncio.sleep(0)
        lock.release()
        runtime.release_idle_share_lock("same-target")
        self.assertTrue(runtime.is_share_busy("same-target"))
        self.assertIs(runtime.get_share_lock("same-target"), lock)
        await asyncio.wait_for(waiter, 1)
        third_entered = asyncio.Event()

        async def third():
            async with runtime.get_share_lock("same-target"):
                third_entered.set()

        third_task = asyncio.create_task(third())
        await asyncio.sleep(0)
        self.assertFalse(third_entered.is_set())
        lock.release()
        await asyncio.wait_for(third_task, 1)
        runtime.release_idle_share_lock("same-target")
        self.assertEqual(runtime.plugin._target_locks, {})

    async def test_cancelled_waiter_does_not_keep_idle_lock_forever(self):
        main = testmedia._load_main_module()
        runtime = main.RuntimeService(
            types.SimpleNamespace(_lock=asyncio.Lock(), _target_locks={})
        )
        lock = runtime.get_share_lock("target")
        await lock.acquire()
        waiter = asyncio.create_task(lock.acquire())
        await asyncio.sleep(0)
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter
        lock.release()
        runtime.release_idle_share_lock("target")
        self.assertEqual(runtime.plugin._target_locks, {})


class PersonaAndModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_target_override_disabled_persona_and_public_identity(self):
        testidentity._load_daily_share_modules()
        persona = importlib.import_module(testidentity.CORE_PACKAGE_NAME + ".persona")
        default = AsyncMock(return_value={"prompt": "global"})
        resolve = AsyncMock(
            return_value=("override", {"prompt": "session"}, None, False)
        )
        context = types.SimpleNamespace(
            persona_manager=types.SimpleNamespace(
                get_default_persona_v3=default, resolve_selected_persona=resolve
            ),
            conversation_manager=types.SimpleNamespace(
                get_curr_conversation_id=AsyncMock(return_value="conversation"),
                get_conversation=AsyncMock(
                    return_value=types.SimpleNamespace(persona_id="override")
                ),
            ),
        )
        self.assertEqual(
            await persona.selected_share_persona(context, "qq:FriendMessage:2"),
            {"prompt": "session"},
        )
        self.assertEqual(
            resolve.await_args.kwargs["conversation_persona_id"], "override"
        )
        resolve.return_value = ("[%None]", None, None, False)
        self.assertEqual(
            await persona.selected_share_persona(context, "qq:FriendMessage:2"), {}
        )
        self.assertEqual(
            await persona.selected_share_persona(context, "qzone_broadcast"),
            {"prompt": "global"},
        )
        default.assert_awaited_once_with()

    async def test_long_persona_tail_is_preserved_in_content(self):
        content, _ = testidentity._load_daily_share_modules()
        prompt = "角色设定" * 400 + "。末尾的重要身份约束"
        llm = AsyncMock(return_value="今天挺好")
        service = content.ContentService(
            {"news_conf": {}, "basic_conf": {}, "context_conf": {}},
            llm,
            context=types.SimpleNamespace(
                persona_manager=testidentity._PersonaManager(prompt)
            ),
            db_manager=types.SimpleNamespace(),
            news_service=None,
        )
        config = importlib.import_module(testidentity.CONFIG_MODULE_NAME)
        await service.generate(
            config.ShareType.MOOD,
            config.TimePeriod.AFTERNOON,
            "qq:FriendMessage:2",
            False,
            "",
        )
        self.assertIn("末尾的重要身份约束", llm.await_args.kwargs["system_prompt"])

    async def test_network_block_and_request_number_do_not_disable_fallback(self):
        main = testmedia._load_main_module()
        context = types.SimpleNamespace(
            get_config=lambda umo=None: {
                "agent_runner": {
                    "runner_type": "local",
                    "config": {"model": {"provider_id": "fallback"}},
                }
            },
            get_all_providers=lambda: [],
        )
        for error in (
            RuntimeError("Connection blocked by network firewall"),
            RuntimeError("temporary upstream error, request_id=140189"),
        ):
            with self.subTest(error=str(error)):
                context.llm_generate = AsyncMock(
                    side_effect=[error, types.SimpleNamespace(completion_text="ok")]
                )
                service = main.LlmService(
                    context, {"llm_provider_id": "primary"}, lambda: False
                )
                self.assertEqual(await service.call("test", max_retries=1), "ok")
                self.assertEqual(
                    [
                        c.kwargs["chat_provider_id"]
                        for c in context.llm_generate.await_args_list
                    ],
                    ["primary", "fallback"],
                )

    async def test_structured_content_rejection_stops(self):
        main = testmedia._load_main_module()
        error = RuntimeError("request rejected")
        error.body = {"error": {"code": "content_policy_violation"}}
        service = main.LlmService(None, {}, lambda: False)
        self.assertEqual(
            service._llm_exception_action(
                error,
                attempt=0,
                max_retries=2,
                primary_provider_id="primary",
                current_provider_id="primary",
                has_fallback=True,
            )[0],
            "stop",
        )

"""真实发送边界、重载恢复和生活互动去重回归。所有平台调用均使用替身。"""
import asyncio
import importlib
import types
import unittest
from unittest.mock import AsyncMock

from tests import testmediarecovery as media_fixtures
from tests import testfailure as fixtures


class SubmissionRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.h = media_fixtures.MediaRecoveryTests()
        self.h.setUp()
        self.submission = importlib.import_module(f"{fixtures.CORE_PACKAGE_NAME}.submission")
        self.readiness = importlib.import_module(f"{fixtures.CORE_PACKAGE_NAME}.readiness")
        prepared = (None, None, None, None, "")
        self.h.manager.share.media.generate_media = AsyncMock(return_value=prepared)
        self.h.manager.command_share._generate_command_media = AsyncMock(return_value=prepared)

    async def send(self, kind):
        progress = self.h.start_progress()
        if kind == "chat":
            return await self.h.manager.share.send_prepared_chat_share(**self.h.params(progress))
        return await self.h.manager.command_share.send_prepared_command_share(
            target_umo=fixtures.USER_TARGET_1, target_type_enum=self.h.mod.ShareType.MOOD,
            period=self.h.mod.TimePeriod.NIGHT, life_ctx="original", news_data=None,
            need_image=False, need_video=False, need_voice=False,
            history_source="command", progress_id=progress, content="original", event=None,
        )

    def job(self):
        return next(iter(self.h.plugin.db.state["share_media_continuations"].values()))

    async def check_cancel_before_send(self, kind):
        self.h.manager.delivery.media.prepare_image = AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await self.send(kind)
        self.assertEqual(self.job()["status"], "ready")
        self.assertEqual(self.h.sent, [])
        self.h.manager.delivery.media.prepare_image = AsyncMock(return_value=(None, None))
        await self.h.service.recover_once()
        self.assertEqual(self.job()["status"], "completed")
        self.assertEqual(len(self.h.sent), 1)
        await self.h.service.recover_once()
        self.assertEqual(len(self.h.sent), 1)

    async def test_chat_preparation_cancel_recovers_once(self):
        await self.check_cancel_before_send("chat")

    async def test_command_preparation_cancel_recovers_once(self):
        await self.check_cancel_before_send("command")

    async def test_offline_wait_preserves_original_and_resumes_once(self):
        self.h.manager.delivery.media.prepare_image = AsyncMock(
            side_effect=self.readiness.PlatformNotReady("offline"))
        self.assertFalse(await self.send("chat"))
        self.assertEqual(self.job()["status"], "waiting_platform")
        self.assertTrue(await self.h.service.has_pending_share(fixtures.USER_TARGET_1))
        self.h.manager.delivery.media.prepare_image = AsyncMock(return_value=(None, None))
        await self.h.service.recover_once()
        self.assertEqual(self.job()["status"], "completed")
        self.assertEqual(len(self.h.sent), 1)

    async def test_cancel_after_submission_remains_blocked(self):
        async def uncertain(*args, **kwargs):
            await self.submission.mark_submission()
            raise asyncio.CancelledError()
        self.h.manager.delivery.chains.send_message_chain = uncertain
        with self.assertRaises(asyncio.CancelledError):
            await self.send("chat")
        self.assertEqual(self.job()["status"], "submitting")
        await self.h.service.recover_once()
        self.assertTrue(await self.h.service.has_pending_share(fixtures.USER_TARGET_1))

    async def test_exception_after_submission_cannot_become_retryable_failure(self):
        async def uncertain(*args, **kwargs):
            await self.submission.mark_submission()
            raise TimeoutError("unconfirmed")
        self.h.manager.delivery.chains.send_message_chain = uncertain
        self.assertFalse(await self.send("chat"))
        self.assertEqual(self.job()["status"], "submitting")
        await self.h.service.recover_once()
        self.assertEqual(self.job()["status"], "submitting")

    async def test_waits_for_target_instance_created_later(self):
        calls = []
        bot = types.SimpleNamespace(_wsr_api_clients={1: object()}, _wsr_event_clients=set())
        binding = types.SimpleNamespace(platform_type="aiocqhttp", instance=types.SimpleNamespace(get_client=lambda: bot))
        def resolve(target):
            calls.append(target)
            if len(calls) == 1:
                raise ValueError("机器人实例当前不可用: test")
            return binding
        got = await self.readiness.wait_target_ready(
            types.SimpleNamespace(ensure_target_platform_routable=resolve),
            fixtures.USER_TARGET_1, timeout=0.3)
        self.assertIs(got, binding)
        self.assertEqual(len(calls), 2)

    async def test_invalid_target_is_not_retried(self):
        def resolve(target):
            raise ValueError("目标必须是完整的会话标识")
        with self.assertRaisesRegex(ValueError, "完整"):
            await self.readiness.wait_target_ready(
                types.SimpleNamespace(ensure_target_platform_routable=resolve), "bad", timeout=0)

    async def test_interaction_preflight_failure_does_not_consume_submission(self):
        intent = importlib.import_module(f"{fixtures.CORE_PACKAGE_NAME}.tasks.interact.intent")
        owner = self.h.manager.qzone_interaction
        owner.qzone_conf["qzone_trigger_mode"] = "life_driven"
        post = types.SimpleNamespace(key="test-post", text="test", name="test", images=[])
        for action in ("like", "comment", "reply"):
            with self.subTest(action=action):
                with self.assertRaises(RuntimeError):
                    async with intent.interaction_submission(owner, action, post):
                        raise RuntimeError("login failed before HTTP")
                states = await self.h.plugin.db.get_qzone_state("living_interaction_intents", {})
                self.assertNotIn(intent.interaction_key(action, post), states)
                with self.assertRaises(TimeoutError):
                    async with intent.interaction_submission(owner, action, post):
                        await self.submission.mark_request_submission()
                        raise TimeoutError("request may have arrived")
                states = await self.h.plugin.db.get_qzone_state("living_interaction_intents", {})
                self.assertEqual(states[intent.interaction_key(action, post)]["status"], "submitting")
                self.assertFalse(await intent.wants_interaction(owner, action, post))

    async def test_request_scope_does_not_leak_after_exit(self):
        checkpoint = AsyncMock()
        async with self.submission.request_submission(checkpoint):
            await self.submission.mark_request_submission()
            await self.submission.mark_request_submission()
        await self.submission.mark_request_submission()
        checkpoint.assert_awaited_once()

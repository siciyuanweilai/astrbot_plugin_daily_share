"""Qzone HTTP 边界回归：只读 POST、登录失败与真实写请求分别处理。"""
import asyncio
import importlib
import types
import unittest
from unittest.mock import AsyncMock

from tests import testqzone as fixtures


class GatewaySubmissionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.module = fixtures._load_qzone_service()
        self.service = fixtures._new_qzone_service(self.module)
        self.submission = importlib.import_module(fixtures.PACKAGE_NAME + ".core.submission")
        self.readiness = importlib.import_module(fixtures.PACKAGE_NAME + ".core.readiness")
        self.service.context = AsyncMock(return_value=self.module.QzoneContext(10001, "test", "test"))
        self.service._ensure_request_bot = lambda *args: None

    async def test_initially_missing_bot_is_polled_until_created(self):
        calls = []
        bot = types.SimpleNamespace(_wsr_api_clients={1: object()}, _wsr_event_clients=set())
        def get_bot(**kwargs):
            calls.append(True)
            return None if len(calls) == 1 else bot
        self.service.gateway._get_bot = get_bot
        self.service.gateway.BOT_READY_POLL_INTERVAL_SECONDS = 0.001
        self.assertIs(await self.service.wait_until_ready(timeout=0.1), bot)
        self.assertEqual(len(calls), 2)

    async def test_login_failure_never_marks_interaction_submitted(self):
        self.service.context = AsyncMock(side_effect=self.readiness.PlatformNotReady("offline"))
        checkpoint = AsyncMock()
        async with self.submission.request_submission(checkpoint):
            with self.assertRaises(self.readiness.PlatformNotReady):
                await self.service._request("POST", "https://unit.invalid", submission="interaction")
        checkpoint.assert_not_awaited()

    async def test_write_checkpoint_precedes_http_and_survives_timeout(self):
        checkpoint = AsyncMock()
        calls = []
        def request(*args, **kwargs):
            self.assertEqual(checkpoint.await_count, 1)
            calls.append(True)
            raise asyncio.TimeoutError()
        self.service._http = AsyncMock(return_value=types.SimpleNamespace(request=request))
        async with self.submission.request_submission(checkpoint):
            with self.assertRaisesRegex(RuntimeError, "超时"):
                await self.service._request("POST", "https://unit.invalid", submission="interaction")
        checkpoint.assert_awaited_once()
        self.assertEqual(calls, [True])

    async def test_readonly_post_never_consumes_interaction(self):
        class Response:
            status = 200
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def text(self):
                return '{"code":0}'
        self.service._http = AsyncMock(return_value=types.SimpleNamespace(request=lambda *a, **k: Response()))
        checkpoint = AsyncMock()
        async with self.submission.request_submission(checkpoint):
            result = await self.service._request("POST", "https://unit.invalid")
        self.assertEqual(result["code"], 0)
        checkpoint.assert_not_awaited()

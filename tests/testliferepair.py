import asyncio
import importlib
import types
import unittest
from unittest.mock import AsyncMock, patch

from .testsharelink import DailyLifeBridge, _Database, _metadata
from astrbot_plugin_daily_share.core.context.daily.parser import ContextLifeParseService
from astrbot_plugin_daily_share.core.context.tts import ContextTtsService
from astrbot_plugin_daily_share.core.integrations.delivery import (
    record_confirmed_history,
)
from astrbot_plugin_daily_share.core.integrations.mediajob import current_share_job
from astrbot_plugin_daily_share.core.integrations.contact import coordinate_share
from astrbot_plugin_daily_share.core.tasks.continuation import ShareContinuationService
from astrbot_plugin_daily_share.core.tasks.interact.receipt import (
    record_qzone_interaction,
)


class LifeRepairTests(unittest.IsolatedAsyncioTestCase):
    async def test_external_outbox_survives_reload_with_original_identity_and_time(
        self,
    ):
        db = _Database()
        context = types.SimpleNamespace(get_all_stars=lambda: [])
        bridge = DailyLifeBridge(context, db=db)
        job = {"id": "confirmed-send"}
        token = current_share_job.set(job)
        try:
            self.assertFalse(
                await bridge.record_external_activity(
                    "qq:FriendMessage:a",
                    "已发正文",
                    reason="分享",
                    sync_memory=True,
                )
            )
            original = next(iter(db.values["external_activity_outbox"].values()))
            await bridge.record_external_activity(
                "qq:FriendMessage:a",
                "已发正文",
                reason="分享",
                sync_memory=True,
            )
            self.assertEqual(
                next(iter(db.values["external_activity_outbox"].values())), original
            )
        finally:
            current_share_job.reset(token)
        receive = AsyncMock(return_value=True)
        context.get_all_stars = lambda: [
            _metadata(types.SimpleNamespace(record_external_activity_receipt=receive))
        ]
        await DailyLifeBridge(context, db=db).flush_public_receipts()
        receive.assert_awaited_once_with(original)
        self.assertEqual(db.values["external_activity_outbox"], {})

    async def test_failed_image_is_absent_from_confirmed_audio_history(self):
        history = types.SimpleNamespace(record_bot_reply_to_history=AsyncMock())
        await record_confirmed_history(
            history,
            "target",
            "已发语音",
            "未发图片",
            {
                "audio_sent": True,
                "image_sent": False,
            },
        )
        history.record_bot_reply_to_history.assert_awaited_once_with(
            "target", "已发语音", image_desc=""
        )
        history.record_bot_reply_to_history.reset_mock()
        await record_confirmed_history(
            history,
            "target",
            "未知结果",
            "未知配图",
            {
                "text_sent": True,
                "text_probable_sent": True,
            },
        )
        history.record_bot_reply_to_history.assert_not_awaited()

    def test_unobserved_action_keeps_uncertainty(self):
        parser = ContextLifeParseService(
            types.SimpleNamespace(
                life_memory=types.SimpleNamespace(
                    _compact_life_text=lambda value, limit: str(value)[:limit]
                ),
            )
        )
        text = parser._current_action(
            {
                "current_facts": {
                    "valid": True,
                    "current_action": {
                        "activity": "睡觉",
                        "status": "running",
                        "observation_state": "pending",
                        "observed_at": "2026-10-22 01:00",
                    },
                }
            }
        )
        self.assertIn("当前进展待确认", text)
        self.assertIn("2026-10-22 01:00", text)
        self.assertNotIn("进行中", text)

    async def test_public_album_receipt_retains_thread_and_scope(self):
        receive = AsyncMock(return_value=True)
        owner = types.SimpleNamespace(
            plugin=types.SimpleNamespace(
                daily_life_bridge=types.SimpleNamespace(record_public_activity=receive),
            )
        )
        post = types.SimpleNamespace(
            key="album:batch",
            uin=1,
            name="原作者",
            text="整组照片",
            appid=4,
            photo_comment_scope="batch",
        )
        parent = types.SimpleNamespace(
            tid="root", uin=2, nickname="评论者", content="原评论"
        )
        target = types.SimpleNamespace(
            tid="child",
            uin=3,
            nickname="回复者",
            content="新回复",
            reply_to_tid="bot",
            reply_to_uin=4,
        )
        await record_qzone_interaction(
            owner,
            post,
            "继续回应",
            scene="qzone_reply",
            target_comment=target,
            parent_comment=parent,
        )
        receipt = receive.await_args.args[0]
        self.assertEqual(receipt["scope"], "album_batch")
        self.assertEqual(receipt["post_context"]["content"], "整组照片")
        self.assertEqual(
            [row["id"] for row in receipt["conversation"]], ["root", "child"]
        )
        self.assertEqual(receipt["reply_to_author_id"], "3")

    async def test_automatic_conflict_stops_before_generation_and_manual_bypasses(self):
        coordinate = AsyncMock(return_value={"allowed": False, "reason": "其他任务"})

        class Owner:
            plugin = types.SimpleNamespace(
                daily_life_bridge=types.SimpleNamespace(coordinate_contact=coordinate)
            )
            generated = 0

            @coordinate_share
            async def run(self, *, uid, history_source):
                self.generated += 1
                return True

        owner = Owner()
        self.assertFalse(await owner.run(uid="target", history_source="scheduled"))
        self.assertEqual(owner.generated, 0)
        self.assertTrue(await owner.run(uid="target", history_source="command"))
        self.assertEqual(owner.generated, 1)

    async def test_stale_media_is_not_submitted_and_keeps_existing_asset(self):
        from astrbot_plugin_daily_share.core.integrations.contact import (
            ShareContactReview,
        )

        plugin = types.SimpleNamespace(
            db=_Database(),
            daily_life_bridge=types.SimpleNamespace(
                coordinate_contact=AsyncMock(
                    return_value={"allowed": False, "stale": True, "reason": "新消息"}
                ),
            ),
        )
        service = ShareContinuationService(plugin)
        job = {
            "id": "original",
            "status": "pending",
            "params": {"uid": "target", "history_source": "scheduled"},
            "contact_snapshot": "old",
            "media_assets": {"image": "/original.png"},
        }
        token = current_share_job.set(job)
        try:
            with self.assertRaises(ShareContactReview):
                await service.mark_submitting()
        finally:
            current_share_job.reset(token)
        self.assertEqual(job["status"], "pending")
        self.assertEqual(job["media_assets"]["image"], "/original.png")

    async def test_related_memory_is_cached_and_target_isolated(self):
        lookup = AsyncMock(return_value=[{"text": "摄影记忆", "kind": "memory"}])
        plugin = types.SimpleNamespace(search_share_memories=lookup)
        context = types.SimpleNamespace(get_all_stars=lambda: [_metadata(plugin)])
        bridge = DailyLifeBridge(context)
        for target in (
            "qq:FriendMessage:a",
            "qq:FriendMessage:a",
            "qq:FriendMessage:b",
        ):
            self.assertIn(
                "摄影记忆", await bridge.related_memory_prompt("摄影", target)
            )
        self.assertEqual(lookup.await_count, 2)

    async def test_contact_service_outage_and_malformed_reply_are_retryable(self):
        coordinate = AsyncMock(side_effect=RuntimeError("temporarily unavailable"))
        bridge = DailyLifeBridge(
            types.SimpleNamespace(
                get_all_stars=lambda: [
                    _metadata(
                        types.SimpleNamespace(coordinate_share_contact=coordinate)
                    )
                ]
            )
        )
        for reply in ("exception", None, {}):
            if reply != "exception":
                coordinate.side_effect = None
                coordinate.return_value = reply
            result = await bridge.coordinate_contact(
                "target", owner="share", action="check"
            )
            self.assertFalse(result.get("allowed"))
            self.assertTrue(result.get("retryable"))

    async def test_voice_follow_reuses_one_decision_and_manual_skips_it(self):
        module = importlib.import_module(ContextTtsService.__module__)
        bridge = types.SimpleNamespace(
            plan_voice=AsyncMock(
                return_value={"valid": True, "channel": "voice", "voice_style": "soft"}
            ),
            prepare_expression=AsyncMock(return_value={}),
            _set_media_result=lambda *args: None,
        )
        service = types.SimpleNamespace(
            context=None,
            daily_life_bridge=bridge,
            tts_conf={"enable_tts": True, "follow_daily_life_voice": True},
            is_weixin_platform=lambda _: False,
        )
        tts = ContextTtsService(service)
        with patch.object(
            module,
            "call_default_daily_life_media_tool",
            AsyncMock(return_value="voice.wav"),
        ) as generate:
            self.assertEqual(await tts.text_to_speech("内容", "target"), "voice.wav")
            bridge.plan_voice.assert_awaited_once()
            bridge.prepare_expression.assert_not_awaited()
            self.assertEqual(generate.await_args.kwargs["voice_style"], "soft")
            bridge.plan_voice.return_value = {"valid": True, "channel": "text"}
            self.assertIsNone(await tts.text_to_speech("文字内容", "target"))
            self.assertEqual(generate.await_count, 1)
            token = current_share_job.set({"kind": "command"})
            try:
                await tts.text_to_speech("指定语音", "target")
            finally:
                current_share_job.reset(token)
            self.assertEqual(bridge.plan_voice.await_count, 2)
            bridge.prepare_expression.assert_awaited_once()

    async def test_z_context_builder_is_cancelled_with_plugin_tasks(self):
        from . import testmedia

        module = testmedia._load_main_module()
        plugin = testmedia._new_plugin_with_support(module)
        started = asyncio.Event()

        async def builder(_):
            started.set()
            await asyncio.Future()

        await plugin.support_service.operations.tool_context.cached_context_prompt(
            "qzone", "target", builder, timeout=0.01
        )
        await started.wait()
        self.assertTrue(plugin._bg_tasks)
        tasks = tuple(plugin._bg_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(0)
        self.assertFalse(
            plugin.support_service.operations.tool_context._prompt_inflight
        )

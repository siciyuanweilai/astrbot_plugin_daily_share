import asyncio
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrbot_plugin_daily_share.core.context.daily.continuity import (
    continuity_prompt,
    topic_continuity,
)
from astrbot_plugin_daily_share.core.integrations.dailylife import DailyLifeBridge
from astrbot_plugin_daily_share.core.integrations.delivery import record_confirmed_share
from astrbot_plugin_daily_share.core.integrations.mediajob import current_share_job
from astrbot_plugin_daily_share.core.tasks.interact import sight
from astrbot_plugin_daily_share.core.tasks.taskbase import (
    TaskConfigState,
    TaskSharedState,
)
from astrbot_plugin_daily_share.core.tasks.transmit.chain import (
    TaskDeliveryChainService,
)
from astrbot_plugin_daily_share.core.tasks.transmit.stage import (
    TaskDeliveryStatusService,
)


def _delivery_chain(record):
    runtime = types.SimpleNamespace(
        plugin=types.SimpleNamespace(
            daily_life_bridge=types.SimpleNamespace(record_delivery=record)
        )
    )
    config = TaskConfigState({}, {}, {}, {}, {}, {}, {})
    state = TaskSharedState(asyncio.Lock(), asyncio.Lock())
    status = TaskDeliveryStatusService(runtime, config, state)
    owner = TaskDeliveryChainService(runtime, config, state, status=status)
    owner.send_message_chain = AsyncMock()
    return owner


class ShareUpdateTests(unittest.IsolatedAsyncioTestCase):
    def test_topic_reuses_same_snapshot_without_object_or_relationship_material(self):
        context = continuity_prompt(
            {
                "continuity": {
                    "version": 1,
                    "interests": [{"label": "摄影", "state": "paused"}],
                    "objects": [{"title": "私人日记"}],
                }
            }
        )
        for value in (context, json.dumps({"生活连续性": context}, ensure_ascii=False)):
            result = topic_continuity(value)
            self.assertIn("摄影", result)
            self.assertIn("paused", result)
            self.assertNotIn("私人日记", result)

    async def test_probable_delivery_does_not_become_life_memory_or_time_fallback(self):
        context = types.SimpleNamespace(record_external_share=AsyncMock())
        await record_confirmed_share(
            context,
            "qq:FriendMessage:a",
            "不确定送达的正文",
            "图片内容",
            {
                "text_sent": True,
                "text_probable_sent": True,
                "image_sent": True,
                "image_probable_sent": True,
            },
        )
        context.record_external_share.assert_not_awaited()
        await record_confirmed_share(
            context,
            "qq:FriendMessage:a",
            "已送达正文",
            "未送达图片",
            {
                "text_sent": True,
                "image_sent": True,
                "image_probable_sent": True,
            },
        )
        context.record_external_share.assert_awaited_once_with(
            "qq:FriendMessage:a", "已送达正文", "", image_sent=False, media_kind=""
        )

    async def test_receipt_replay_keeps_original_time_and_target(self):
        class Db:
            def __init__(self):
                self.data = {}

            async def update_context_state(self, key, value):
                target = self.data.setdefault(key, {})
                for name, item in value.items():
                    if item is None:
                        target.pop(name, None)
                    else:
                        target[name] = item

            async def get_context_state(self, key, default):
                return self.data.get(key, default)

            async def set_context_state(self, key, value):
                self.data[key] = value

        plugin = types.SimpleNamespace(
            record_share_delivery=AsyncMock(side_effect=RuntimeError("reload"))
        )
        bridge = DailyLifeBridge(None, Db())
        bridge._plugin = lambda: plugin
        job = {"id": "job", "kind": "chat", "params": {"uid": "qq:FriendMessage:a"}}
        token = current_share_job.set(job)
        try:
            self.assertFalse(
                await bridge.record_delivery(
                    "qq:FriendMessage:a", 1234.5, media_kinds=("image",)
                )
            )
        finally:
            current_share_job.reset(token)
        plugin.record_share_delivery = AsyncMock(return_value=True)
        await bridge.flush_public_receipts()
        receipt = plugin.record_share_delivery.await_args.args[0]
        self.assertEqual(
            receipt,
            {
                "target_umo": "qq:FriendMessage:a",
                "sent_at": 1234.5,
                "media_tasks": {"image": "job:image"},
            },
        )
        self.assertEqual(bridge.db.data["share_delivery_outbox"], {})

    async def test_confirmed_send_records_time_but_probable_timeout_does_not(self):
        record = AsyncMock()
        owner = _delivery_chain(record)
        chain = types.SimpleNamespace(chain=[type("Image", (), {})()])
        media = {}
        self.assertTrue(
            await owner.send_chain_stage(
                "qq:FriendMessage:a", chain, "text", media_result=media
            )
        )
        self.assertEqual(record.await_args.kwargs["media_kinds"], ("image",))
        self.assertGreater(media["text_sent_at"], 0)
        self.assertTrue(media["text_sent"])
        record.reset_mock()
        owner.send_message_chain.side_effect = RuntimeError("sendmsg timeout")
        media = {}
        self.assertTrue(
            await owner.send_chain_stage(
                "qq:FriendMessage:a", chain, "image", media_result=media
            )
        )
        record.assert_not_awaited()
        self.assertNotIn("image_sent_at", media)
        self.assertTrue(media["image_probable_sent"])
        self.assertTrue(media["partial_errors"][0]["probable_sent"])
        self.assertEqual(owner.send_message_chain.await_count, 2)

    async def test_receipt_failure_never_causes_send_retry(self):
        owner = _delivery_chain(
            AsyncMock(side_effect=RuntimeError("database unavailable"))
        )
        self.assertTrue(
            await owner.send_chain_stage(
                "qq:FriendMessage:a", types.SimpleNamespace(chain=[]), "text"
            )
        )
        owner.send_message_chain.assert_awaited_once()

    async def test_gif_preparation_and_per_provider_timeout_fallback(self):
        async def generate(**kwargs):
            if kwargs["chat_provider_id"] == "slow":
                await asyncio.sleep(1)
            return types.SimpleNamespace(completion_text="小猫挥爪")

        context = types.SimpleNamespace(llm_generate=AsyncMock(side_effect=generate))
        owner = types.SimpleNamespace(
            plugin=types.SimpleNamespace(
                context=context,
                daily_life_bridge=types.SimpleNamespace(
                    prepare_image=AsyncMock(
                        return_value={
                            "status": "ok",
                            "source": "data:image/jpeg;base64,frames",
                            "hint": "同一动图三帧",
                        }
                    )
                ),
            )
        )
        with (
            patch.object(
                sight,
                "_qzone_vision_provider_candidates",
                AsyncMock(
                    return_value=[("slow", "qzone_vision"), ("fallback", "session")]
                ),
            ),
            patch.object(sight, "_qzone_provider_label", return_value="model"),
            patch.object(sight, "QZONE_IMAGE_PROVIDER_TIMEOUT_SECONDS", 0.01),
        ):
            result = await sight._describe_qzone_image(
                owner, "https://example.com/a.gif"
            )
        self.assertEqual(result, "小猫挥爪")
        self.assertEqual(context.llm_generate.await_count, 2)
        self.assertEqual(
            context.llm_generate.await_args.kwargs["image_urls"],
            ["data:image/jpeg;base64,frames"],
        )
        self.assertIn("同一动图三帧", context.llm_generate.await_args.kwargs["prompt"])

    async def test_video_failure_reports_evidence_boundary(self):
        describe = AsyncMock(return_value={"status": "unavailable"})
        owner = types.SimpleNamespace(
            plugin=types.SimpleNamespace(
                daily_life_bridge=types.SimpleNamespace(describe_video=describe)
            )
        )
        post = types.SimpleNamespace(
            videos=["https://example.com/1.mp4", "https://example.com/2.mp4"]
        )
        result = await sight._qzone_video_context(owner, post)
        self.assertIn("完整视频尚无可用摘要", result)
        self.assertIn("动作与声音未知", result)
        describe.assert_awaited_once_with("https://example.com/1.mp4")

    def test_continuity_prompt_never_exports_raw_paths_or_private_projection(self):
        result = continuity_prompt(
            {
                "continuity": {
                    "version": 1,
                    "objects": [
                        {
                            "title": "图片",
                            "delivery": "not_confirmed",
                            "resource": "/private/photo.png",
                        }
                    ],
                    "public": {"secret": "不应原样拼接"},
                }
            }
        )
        self.assertIn("not_confirmed", result)
        self.assertNotIn("/private/", result)
        self.assertNotIn("不应原样拼接", result)

"""通过 daily_share 验证已安装 daily_life 的持久化与对外接口。

仅替换 provider 请求和最终消息传输环节。相邻目录中存在 daily_life 源码时，
才运行这些可选集成测试。
"""

import asyncio
import importlib
import json
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
import time
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from tests import testfailure as fixtures

LIFE_ROOT = Path(__file__).resolve().parents[2] / "astrbot_plugin_daily_life"
LIFE_AVAILABLE = (LIFE_ROOT / "tests" / "support.py").is_file()
if LIFE_AVAILABLE:
    sys.path.insert(0, str(LIFE_ROOT / "tests"))
    import support as life_support
    from core.archive import LifeArchive
    from core.life.domain import LifeDomainService
    from core.media.picture.polling import ImageTaskError
    from core.media.video.errors import VideoTaskError
    from core.models import DayRecord, LifeActionIntent, WeatherInfo
    from core.runtime import DailyLifeRuntime
    from astrbot_plugin_daily_life.main import DailyLifePlugin


@unittest.skipUnless(LIFE_AVAILABLE, "requires the sibling daily_life source tree")
class DailyLifeFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # daily_life 的轻量调度器桩不包含 cron 触发器模块。
        for name in list(sys.modules):
            if name == "apscheduler" or name.startswith("apscheduler."):
                sys.modules.pop(name, None)
        self.mod = fixtures._load_tasks_module()
        self.root = fixtures.CORE_PACKAGE_NAME
        self.bridge_class = importlib.import_module(
            f"{self.root}.integrations.dailylife"
        ).DailyLifeBridge
        self.mediajob = importlib.import_module(f"{self.root}.integrations.mediajob")
        self.continuations = importlib.import_module(
            f"{self.root}.tasks.continuation"
        ).ShareContinuationService
        self.db_class = importlib.import_module(f"{self.root}.db").DatabaseManager
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database_path = Path(self.temp.name) / "life.db"
        self.archive = LifeArchive(self.database_path)
        self.addCleanup(lambda: self.archive.close())
        self.sent = []

    def life_plugin(self):
        runtime = DailyLifeRuntime.__new__(DailyLifeRuntime)
        runtime.archive = self.archive
        runtime.config = life_support.make_config()
        runtime.composer, _, _, _ = life_support.make_composer([])
        runtime.composer.archive = self.archive
        runtime._schedule_context_state_refresh = Mock()
        runtime.note_conversation_sent = Mock()
        plugin = DailyLifePlugin(types.SimpleNamespace(), {})
        plugin.runtime = runtime
        plugin.commands = object()
        self.life = plugin
        self.runtime = runtime
        self.stars = [
            types.SimpleNamespace(
                name="astrbot_plugin_daily_life",
                root_dir_name="astrbot_plugin_daily_life",
                activated=True,
                star_cls=plugin,
            )
        ]
        context = types.SimpleNamespace(get_all_stars=lambda: self.stars)
        self.bridge = self.bridge_class(context)
        return context

    async def test_inventory_then_committed_change_controls_actual_share_visuals(self):
        context = self.life_plugin()
        now = datetime(2026, 10, 20, 12)
        items = []
        for seed, kind, description in (
            (1, "outfit", "针织上衣与长裤"),
            (2, "footwear", "拖鞋"),
            (3, "footwear", "板鞋"),
        ):
            item = await self.archive.upsert_style_catalog_item(
                {
                    "kind": kind,
                    "source_image_hash": f"{seed:064x}",
                    "description": description,
                    "confidence": 0.95,
                    "attributes": {},
                }
            )
            items.append(item)
        outfit, old_shoes, new_shoes = items
        await self.archive.mark_style_catalog_used([outfit.id, old_shoes.id])
        day = DayRecord(
            date=now.date().isoformat(),
            outfit="针织上衣与长裤；拖鞋",
            weather_info=WeatherInfo(temp=13),
        )
        day.meta.update(
            style_catalog_reference_ids=f"{outfit.id},{old_shoes.id}",
            outfit_fact_confirmed_at=now.isoformat(sep=" "),
            outfit_scene_category="home",
            outfit_components=json.dumps(
                {
                    "main_clothing": {"state": "worn", "description": "针织上衣与长裤"},
                    "footwear": {"state": "worn", "description": "拖鞋"},
                }
            ),
        )
        await self.archive.save_day(day, require_wearable=True)
        await self.archive.adopt_wardrobe_items(
            [new_shoes.id], event_id="new-shoes", at=str(now), reason="新鞋入库"
        )
        context_service = importlib.import_module(
            f"{self.root}.context"
        ).ContextService(context, {}, self.bridge)
        image_class = importlib.import_module(f"{self.root}.image").ImageService
        model = AsyncMock(return_value=json.dumps({"outfit": "模型猜测的睡衣"}))
        image = image_class(context, {}, model, self.bridge)

        async def visuals(target):
            materials = await context_service.get_chat_share_context(target)
            return await image._agent_extract_visuals(
                "出门走走",
                materials["life_context"],
                involves_self=True,
                target_umo=target,
            )

        with patch("core.runtime.mirror.export.life_now", return_value=now):
            for target in (fixtures.USER_TARGET_1, "aiocqhttp:GroupMessage:group-a"):
                self.assertEqual((await visuals(target))["outfit"], day.outfit)
            action = LifeActionIntent.from_value(
                {
                    "action_id": "change-shoes",
                    "action_type": "change_outfit",
                    "target": "针织上衣与长裤；板鞋",
                    "payload": {
                        "scene_category": "public",
                        "outfit_components": {
                            "footwear": {"state": "worn", "description": "板鞋"}
                        },
                        "catalog_reference_ids": [new_shoes.id],
                    },
                }
            )
            domains = LifeDomainService(self.runtime.config.domains, self.archive)
            self.assertEqual(await domains.validate_action(action, day=day), (True, ""))
            result = await self.runtime.composer.settle_and_persist_life_action(
                day, action, now=now
            )
            self.assertEqual(result.status, "committed")
            self.archive.close()
            self.archive = LifeArchive(self.database_path)
            self.runtime.archive = self.archive
            self.runtime.composer.archive = self.archive
            for target in (fixtures.USER_TARGET_1, "aiocqhttp:GroupMessage:group-a"):
                self.assertEqual(
                    (await visuals(target))["outfit"], "针织上衣与长裤；板鞋"
                )
            replay = await self.runtime.composer.settle_and_persist_life_action(
                day, action, now=now
            )
            self.assertTrue(replay.replayed)
        self.assertEqual(model.await_count, 4)
        state = (await self.archive.get_wardrobe_snapshot())["items"]
        self.assertTrue(state[str(outfit.id)]["currently_worn"])
        self.assertFalse(state[str(old_shoes.id)]["currently_worn"])
        self.assertTrue(state[str(new_shoes.id)]["currently_worn"])

    async def test_browsing_context_keeps_scope_and_receipts_across_plugins(self):
        self.life_plugin()
        now = datetime(2026, 10, 24, 12)
        await self.archive.save_day(DayRecord(date=now.date().isoformat()))
        self.runtime._runtime_now = lambda: now
        self.runtime.mark_page_status_changed = AsyncMock()
        browser = self.runtime.bili_browsing
        shared = dict(status="unfinished", position=60, impression="实验中控制变量的做法值得试试", share_worthy=True,
                      evidence=[{"start": 0, "end": 60, "quote": "真实字幕中的实验过程", "source": "字幕"}])
        own = browser.new_record({"bvid": "BV1xx411c7mD", "page": 1, "title": "有内容依据的实验视频", "url": "https://www.bilibili.com/video/BV1xx411c7mD", "duration": 300})
        private = browser.new_record({"bvid": "BV1yy411c7mD", "page": 1, "title": "仅在私聊里分享的视频", "url": "https://www.bilibili.com/video/BV1yy411c7mD", "duration": 300}, scope=fixtures.USER_TARGET_1)
        await browser._save(own, **shared)
        await browser._save(private, **shared)
        parser = importlib.import_module(f"{self.root}.context.daily.parser").ContextLifeParseService
        with patch("core.runtime.mirror.export.life_now", return_value=now):
            public = await self.bridge.get_share_context("")
            self.assertEqual([item["bvid"] for item in public["bili_experiences"]], [own["bvid"]])
            group = await self.bridge.get_share_context(fixtures.GROUP_TARGET_1)
            self.assertEqual([item["bvid"] for item in group["bili_experiences"]], [own["bvid"]])
            private_context = await self.bridge.get_share_context(fixtures.USER_TARGET_1)
            self.assertEqual(len(private_context["bili_experiences"]), 2)
            self.assertIn("真实字幕中的实验过程", parser.browsing_prompt(public))
            self.runtime.external_activity = types.SimpleNamespace(record_external_activity_receipt=AsyncMock(return_value=True))
            delivered = await self.bridge._send_external_receipt({"event_id": "share-video-once", "target_umo": fixtures.USER_TARGET_1, "content": own["url"], "occurred_at": now.isoformat()})
            self.assertTrue(delivered)
            after = await self.bridge.get_share_context(fixtures.USER_TARGET_1)
            self.assertEqual([item["bvid"] for item in after["bili_experiences"]], [private["bvid"]])
            # 私聊发送回执不会让另一个群失去自己的分享机会。
            self.assertEqual(len((await self.bridge.get_share_context(fixtures.GROUP_TARGET_1))["bili_experiences"]), 1)
        await browser.close()

    def install_media_provider(self, kind, artifact):
        listeners = {}

        @contextmanager
        def track(listener, **_kwargs):
            listeners[kind] = listener
            try:
                yield
            finally:
                listeners.pop(kind, None)

        async def submit(*_args, **_kwargs):
            route = (
                types.SimpleNamespace(
                    api_url="https://image.example/v1",
                    model="image-test",
                    protocol="openai",
                    api_key="DO_NOT_PERSIST_CREDENTIAL",
                )
                if kind == "image"
                else {
                    "endpoint": "https://video.example/v1/videos",
                    "model": "video-test",
                }
            )
            await listeners[kind](f"{kind}-original", route)
            error = ImageTaskError if kind == "image" else VideoTaskError
            raise error("original task is still running")

        provider = types.SimpleNamespace(
            track_async_tasks=track,
            **{f"resume_async_{kind}": AsyncMock(return_value=artifact)},
        )
        self.runtime.media = types.SimpleNamespace(**{kind: provider})
        self.runtime.stage_durable_media_delivery = AsyncMock()
        submit_mock = AsyncMock(side_effect=submit)
        setattr(self.runtime, f"generate_life_{kind}_asset", submit_mock)
        return provider, submit_mock

    def share_plugin(self, kind):
        plugin = fixtures._Plugin()
        plugin.db = self.db_class(Path(self.temp.name) / "share")
        self.addAsyncCleanup(plugin.db.close)
        plugin.services = replace(plugin.services, db=plugin.db)
        manager = fixtures._new_manager(self.mod, plugin)
        plugin.task_manager = manager
        plugin.daily_life_bridge = self.bridge
        self.bridge.db = plugin.db
        plugin.runtime_service = types.SimpleNamespace(
            is_share_busy=plugin.is_share_busy,
            get_share_lock=plugin.get_share_lock,
        )
        service = self.continuations(plugin)
        plugin.share_continuations = service

        async def send_chain(uid, chain, event=None):
            self.sent.append((uid, list(chain.items)))

        async def image(*_args, **_kwargs):
            job = self.mediajob.current_share_job.get()
            if kind == "video":
                return str(Path(self.temp.name) / "reference.png")
            if job.get("image_path"):
                return job["image_path"]
            return await self.bridge.generate_image(None, "原配图提示词")

        async def video(reference, *_args, **_kwargs):
            return await self.bridge.generate_video(
                None, "原视频提示词", reference_image=reference
            )

        manager.delivery.chains.send_message_chain = send_chain
        manager.delivery.random_sleep = lambda: asyncio.sleep(0)
        plugin.image_service.generate_image = image
        plugin.image_service.generate_video_from_image = video
        manager.update_configs(
            image={
                "enable_ai_image": True,
                "image_enabled_types": ["心情"],
                "separate_send": True,
                "enable_ai_video": kind == "video",
                "video_enabled_types": ["心情"],
            }
        )
        return plugin, manager, service

    async def check_reload(self, kind):
        self.life_plugin()
        path = Path(self.temp.name) / (
            "original.png" if kind == "image" else "original.mp4"
        )
        path.write_bytes(b"provider artifact")
        artifact = types.SimpleNamespace(
            **{"path" if kind == "image" else "url": str(path)}
        )
        _, submit = self.install_media_provider(kind, artifact)
        plugin, manager, _ = self.share_plugin(kind)
        progress_id = manager.progress.start_share_progress(
            source_type="command", target_id=fixtures.USER_TARGET_1
        )
        self.assertFalse(
            await manager.share.send_prepared_chat_share(
                uid=fixtures.USER_TARGET_1,
                stype=self.mod.ShareType.MOOD,
                content="保留原文案",
                news_data=None,
                life_ctx="原生活快照",
                period=self.mod.TimePeriod.NIGHT,
                progress_id=progress_id,
                history_source="command",
            )
        )
        self.assertEqual(self.sent, [])
        submit.assert_awaited_once()
        jobs = await plugin.db.get_share_state("share_media_continuations", {})
        key = next(iter(jobs))
        tasks = await self.archive.get_durable_tasks(kind=f"share_{kind}_generation")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].payload["scope"], fixtures.USER_TARGET_1)
        self.assertEqual(tasks[0].result["progress"]["task_id"], f"{kind}-original")
        self.assertNotIn("DO_NOT_PERSIST_CREDENTIAL", json.dumps(tasks[0].as_dict()))
        await plugin.db.close()

        # 丢弃两个插件实例，并重新打开 daily_life 的真实 SQLite 数据库。
        self.archive.close()
        self.archive = LifeArchive(self.database_path)
        self.life_plugin()
        provider, fresh_submit = self.install_media_provider(kind, artifact)
        fresh_plugin, _, service = self.share_plugin(kind)
        await service.recover_once()
        self.assertEqual(self.sent, [])
        task = (
            await self.archive.lease_durable_tasks(
                "flow-worker", include_kinds=[f"share_{kind}_generation"]
            )
        )[0]
        result = await getattr(self.runtime, f"resume_share_{kind}_generation")(task)
        await self.archive.complete_durable_task(task.id, result, owner="flow-worker")
        await service.recover_once()
        await service.recover_once()

        fresh_submit.assert_not_awaited()
        resume = getattr(provider, f"resume_async_{kind}")
        resume.assert_awaited_once()
        self.assertEqual(resume.await_args.args[0], f"{kind}-original")
        expected_media = ("file_image", str(path)) if kind == "image" else None
        self.assertEqual(self.sent[0], (fixtures.USER_TARGET_1, ["保留原文案"]))
        self.assertEqual(len(self.sent), 2)
        if expected_media:
            self.assertEqual(self.sent[1], (fixtures.USER_TARGET_1, [expected_media]))
        else:
            self.assertEqual(self.sent[1][0], fixtures.USER_TARGET_1)
            self.assertEqual(self.sent[1][1][0].source, ("file_video", str(path)))
        self.runtime.stage_durable_media_delivery.assert_not_awaited()
        self.assertEqual(
            (await fresh_plugin.db.get_share_state("share_media_continuations", {}))[
                key
            ]["status"],
            "completed",
        )
        self.assertGreater(
            await self.archive.get_conversation_receipt_before(
                fixtures.USER_TARGET_1, time.time()
            ),
            0,
        )
        media_object = await self.archive.record_share_media_object(task.id)
        self.assertEqual(media_object["delivery"], "sent")
        self.assertEqual(media_object["scope"], fixtures.USER_TARGET_1)
        self.assertEqual(
            (await self.life.get_share_image_task(f"{key}:image"))["status"],
            "ready" if kind == "image" else "missing",
        )

    async def test_image_pending_reloads_both_plugins_and_sends_original_once(self):
        await self.check_reload("image")

    async def test_video_pending_reloads_both_plugins_and_sends_original_once(self):
        await self.check_reload("video")

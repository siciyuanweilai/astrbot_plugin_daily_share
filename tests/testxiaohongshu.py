import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from aiohttp import web

from astrbot_plugin_daily_share.core.config import ShareType, TimePeriod
from astrbot_plugin_daily_share.core.database.keys import XIAOHONGSHU_TARGET_ID
from astrbot_plugin_daily_share.core.panel.meta import DashboardConfigMetaService
from astrbot_plugin_daily_share.core.schedule import normalize_schedule_mode
from astrbot_plugin_daily_share.core.tasks.redbook import TaskXiaohongshuService
from astrbot_plugin_daily_share.core.tasks.selector import TaskTypeSelectorService
from astrbot_plugin_daily_share.core.xhs import (
    XiaohongshuClient,
    XiaohongshuPublishError,
    normalize_xiaohongshu_visibility,
)

ROOT = Path(__file__).resolve().parents[1]


class XiaohongshuClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.received = []
        app = web.Application()

        async def publish(request):
            self.received.append((dict(request.headers), await request.json()))
            return web.json_response({"code": 0, "data": {"id": "note-1"}})

        async def failure(_request):
            return web.json_response(
                {"code": 1, "data": {"error": "登录状态已失效"}}, status=200
            )

        app.router.add_post("/api/publish", publish)
        app.router.add_post("/api/check-login", failure)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await self.site.start()
        port = self.site._server.sockets[0].getsockname()[1]
        self.config = {
            "server_url": f"http://127.0.0.1:{port}/api",
            "cookie": "session=secret",
            "media_path_source": "/srv/astrbot",
            "media_path_target": "/mnt/share",
        }

    async def asyncTearDown(self):
        await self.runner.cleanup()

    async def test_publish_sends_expected_payload_and_maps_media_path(self):
        client = XiaohongshuClient(self.config)
        result = await client.publish(
            title="今日记录",
            content="今天也要好好生活。",
            images=["/srv/astrbot/temp/image.png", "https://example.test/a.png"],
            tags=["日常", "#生活"],
        )

        self.assertEqual(result["data"]["id"], "note-1")
        headers, payload = self.received[0]
        self.assertEqual(headers["X-Xhs-Cookie"], "session=secret")
        self.assertEqual(
            payload["images"],
            ["/mnt/share/temp/image.png", "https://example.test/a.png"],
        )
        self.assertEqual(payload["tags"], ["日常", "#生活"])
        self.assertEqual(payload["visibility"], "公开可见")

    def test_visibility_values_are_normalized(self):
        self.assertEqual(normalize_xiaohongshu_visibility(""), "公开可见")
        self.assertEqual(
            normalize_xiaohongshu_visibility("仅互关好友可见"), "仅互关好友可见"
        )

    async def test_nested_service_error_is_reported(self):
        client = XiaohongshuClient(self.config)
        with self.assertRaisesRegex(XiaohongshuPublishError, "登录状态已失效"):
            await client.check_login()

    def test_media_prefix_requires_directory_boundary(self):
        client = XiaohongshuClient(self.config)
        self.assertEqual(
            client._media_path("/srv/astrbot-old/image.png"),
            "/srv/astrbot-old/image.png",
        )

    def test_media_mapping_accepts_windows_absolute_target(self):
        config = {
            **self.config,
            "media_path_target": "D:\\xiaohongshu-media",
        }
        client = XiaohongshuClient(config)

        self.assertEqual(
            client._media_values(["/srv/astrbot/temp/image.png"]),
            ["D:\\xiaohongshu-media\\temp\\image.png"],
        )


class XiaohongshuSchemaTests(unittest.TestCase):
    def test_publish_settings_are_exposed_with_neutral_configuration(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        settings = schema["xiaohongshu_conf"]
        self.assertFalse(settings["items"]["enable_xiaohongshu"]["default"])
        self.assertEqual(settings["items"]["server_url"]["default"], "")
        self.assertEqual(
            settings["items"]["visibility"]["options"],
            ["公开可见", "仅自己可见", "仅互关好友可见"],
        )
        self.assertNotIn("_advanced", settings["items"]["media_path_source"])
        self.assertNotIn("_advanced", settings["items"]["media_path_target"])
        self.assertEqual(
            settings["items"]["trigger_mode"]["options"],
            ["固定时间", "随机时段", "高级定时"],
        )
        self.assertEqual(
            settings["items"]["share_output_format"]["description"],
            "小红书输出格式",
        )
        self.assertEqual(settings["items"]["share_output_format"]["type"], "text")
        self.assertTrue(settings["items"]["enable_smart_tags"]["default"])
        for period in (
            "dawn",
            "morning",
            "forenoon",
            "noon",
            "afternoon",
            "evening",
            "night",
            "late_night",
        ):
            self.assertIn(f"xiaohongshu_{period}_sequence", settings["items"])

    def test_dashboard_has_dedicated_xiaohongshu_sequence_section(self):
        page = (ROOT / "pages" / "dashboard" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('data-settings-section="xiaohongshuSequence"', page)
        self.assertIn('id="cfgXiaohongshuNightSequence"', page)
        self.assertIn(
            'data-schema-field="xiaohongshu_night_sequence"',
            page,
        )

    def test_text_schema_fields_use_long_text_inputs(self):
        schema_source = (ROOT / "pages" / "dashboard" / "ui" / "schema.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('if (type === "text")', schema_source)
        self.assertIn("input.rows = 3", schema_source)

    def test_schedule_mode_labels_keep_internal_values_compatible(self):
        self.assertEqual(normalize_schedule_mode("固定时间", "cron"), "fixed_time")
        self.assertEqual(normalize_schedule_mode("随机时段", "cron"), "random_period")
        self.assertEqual(normalize_schedule_mode("高级定时", "fixed_time"), "cron")

    def test_dashboard_hides_xiaohongshu_schedule_fields_by_mode(self):
        schema_source = (ROOT / "pages" / "dashboard" / "ui" / "schema.js").read_text(
            encoding="utf-8"
        )
        prefs_source = (ROOT / "pages" / "dashboard" / "ui" / "prefs.js").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "label.dataset.schedule = `xiaohongshu-${scheduleKind}`", schema_source
        )
        self.assertIn("syncXiaohongshuScheduleVisibility", prefs_source)
        self.assertIn('固定时间: "fixed_time"', prefs_source)
        self.assertIn('随机时段: "random_period"', prefs_source)
        self.assertIn('高级定时: "cron"', prefs_source)

    def test_advanced_metadata_survives_dashboard_projection(self):
        projected = DashboardConfigMetaService._page_schema_meta_item(
            {"description": "路径", "type": "string", "_advanced": True}
        )
        self.assertTrue(projected["_advanced"])


class XiaohongshuSelectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_automatic_type_uses_xiaohongshu_period_sequence(self):
        class _StateDb:
            def __init__(self):
                self.states = {}

            async def get_share_state(self, key, default):
                return dict(self.states.get(key, default))

            async def update_share_state(self, key, values):
                self.states.setdefault(key, {}).update(values)

        runtime = SimpleNamespace(db=_StateDb())
        config = SimpleNamespace(
            basic={},
            extra_shares={},
            qzone={},
            image={},
            tts={},
            context={},
            receiver={},
            xiaohongshu={"xiaohongshu_night_sequence": ["新闻", "推荐"]},
        )
        service = TaskTypeSelectorService(runtime, config, SimpleNamespace())

        first = await service.decide_type_with_state(
            TimePeriod.NIGHT,
            target_id=XIAOHONGSHU_TARGET_ID,
            specific_type="自动",
        )
        second = await service.decide_type_with_state(
            TimePeriod.NIGHT,
            target_id=XIAOHONGSHU_TARGET_ID,
            specific_type="自动",
        )

        self.assertEqual(first, ShareType.NEWS)
        self.assertEqual(second, ShareType.RECOMMENDATION)

    async def test_explicit_type_still_overrides_period_sequence(self):
        class _StateDb:
            async def get_share_state(self, _key, default):
                return dict(default)

            async def update_share_state(self, _key, _values):
                return None

        runtime = SimpleNamespace(db=_StateDb())
        config = SimpleNamespace(
            basic={},
            extra_shares={},
            qzone={},
            image={},
            tts={},
            context={},
            receiver={},
            xiaohongshu={"xiaohongshu_night_sequence": ["新闻"]},
        )
        service = TaskTypeSelectorService(runtime, config, SimpleNamespace())

        selected = await service.decide_type_with_state(
            TimePeriod.NIGHT,
            target_id=XIAOHONGSHU_TARGET_ID,
            specific_type="心情",
        )

        self.assertEqual(selected, ShareType.MOOD)


class XiaohongshuTagTests(unittest.IsolatedAsyncioTestCase):
    def _service(self, config):
        async def call_llm(**_kwargs):
            return '["咖啡日常", "学习分享", "生活记录"]'

        return TaskXiaohongshuService(
            SimpleNamespace(plugin=SimpleNamespace(call_llm=call_llm)),
            SimpleNamespace(xiaohongshu=config),
            SimpleNamespace(),
        )

    async def test_smart_tags_keep_defaults_and_use_llm_result(self):
        service = self._service(
            {
                "default_tags": ["我的日常", "#生活"],
                "enable_smart_tags": True,
                "smart_tag_count": 3,
            }
        )

        tags = await service._tags("今天喝咖啡，学习也有了新的收获。", ShareType.MOOD)

        self.assertEqual(tags[:2], ["我的日常", "生活"])
        self.assertIn("咖啡日常", tags)
        self.assertIn("学习分享", tags)
        self.assertLessEqual(len(tags), 5)

    async def test_smart_tags_can_be_disabled(self):
        service = self._service(
            {"default_tags": ["日常"], "enable_smart_tags": False}
        )

        self.assertEqual(await service._tags("今天喝咖啡", ShareType.MOOD), ["日常"])


if __name__ == "__main__":
    unittest.main()

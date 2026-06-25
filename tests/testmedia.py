import asyncio
import base64
import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT.parent

PNG_1X1 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB"
    "/6X4n8cAAAAASUVORK5CYII="
)


class _Logger:
    def debug(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None

    def exception(self, *args, **kwargs):
        return None


def _install_stub_modules():
    for name in list(sys.modules):
        if name.startswith("astrbot") or name.startswith("apscheduler") or name in {"aiohttp", "aiofiles"}:
            sys.modules.pop(name, None)

    apscheduler = types.ModuleType("apscheduler")
    apscheduler_schedulers = types.ModuleType("apscheduler.schedulers")
    apscheduler_asyncio = types.ModuleType("apscheduler.schedulers.asyncio")

    class AsyncIOScheduler:
        pass

    apscheduler_asyncio.AsyncIOScheduler = AsyncIOScheduler
    sys.modules["apscheduler"] = apscheduler
    sys.modules["apscheduler.schedulers"] = apscheduler_schedulers
    sys.modules["apscheduler.schedulers.asyncio"] = apscheduler_asyncio

    astrbot = types.ModuleType("astrbot")
    astrbot.__path__ = []
    astrbot_api = types.ModuleType("astrbot.api")
    astrbot_api.__path__ = []
    astrbot_api.logger = _Logger()
    astrbot_api.AstrBotConfig = dict

    star = types.ModuleType("astrbot.api.star")

    class Star:
        pass

    class Context:
        pass

    class StarTools:
        @staticmethod
        def get_data_dir(name):
            return Path(".")

    star.Star = Star
    star.Context = Context
    star.StarTools = StarTools

    event = types.ModuleType("astrbot.api.event")

    class Filter:
        def __getattr__(self, _name):
            return lambda *args, **kwargs: (lambda func: func)

    class AstrMessageEvent:
        pass

    class MessageChain:
        @classmethod
        def chain(cls):
            return cls()

        def file_image(self, _item):
            return self

        def url_image(self, _item):
            return self

    event.filter = Filter()
    event.AstrMessageEvent = AstrMessageEvent
    event.MessageChain = MessageChain

    components = types.ModuleType("astrbot.api.message_components")

    class Record:
        pass

    class Video:
        pass

    components.Record = Record
    components.Video = Video

    sys.modules["astrbot"] = astrbot
    sys.modules["astrbot.api"] = astrbot_api
    sys.modules["astrbot.api.star"] = star
    sys.modules["astrbot.api.event"] = event
    sys.modules["astrbot.api.message_components"] = components
    aiohttp = types.ModuleType("aiohttp")
    aiohttp.ClientError = Exception
    aiohttp.ClientSession = object
    sys.modules["aiohttp"] = aiohttp
    sys.modules["aiofiles"] = types.ModuleType("aiofiles")


def _load_main_module():
    _install_stub_modules()
    if str(PACKAGE_ROOT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_ROOT))
    for name in list(sys.modules):
        if name.startswith("astrbot_plugin_daily_share"):
            sys.modules.pop(name, None)
    return importlib.import_module("astrbot_plugin_daily_share.main")


class DashboardMediaPreviewTests(unittest.TestCase):
    def test_news_link_context_is_injected_for_news_tool_requests(self):
        mod = _load_main_module()

        class Db:
            def __init__(self):
                self.state = {
                    "news_snapshot:session-1": {
                        "source_key": "thepaper",
                        "source_name": "澎湃热搜",
                        "items": [
                            {"title": "第一条新闻", "url": "https://example.com/1"},
                            {"title": "第二条新闻", "url": "https://example.com/2"},
                        ],
                    },
                    "news_snapshot:session-1:focus": {
                        "source_key": "thepaper",
                        "index": 2,
                    },
                }

            async def get_state(self, key, default=None):
                return self.state.get(key, default if default is not None else {})

        class Manager:
            def _news_snapshot_key(self, target_uid):
                return f"news_snapshot:{target_uid}"

            def _news_snapshot_focus_key(self, target_uid):
                return f"{self._news_snapshot_key(target_uid)}:focus"

            def _is_news_snapshot(self, snapshot):
                return isinstance(snapshot, dict) and bool(snapshot.get("items"))

            def _coerce_news_tool_index(self, index):
                text = str(index or "").strip()
                return int(text) if text.isdigit() else None

        class Tools:
            def names(self):
                return ["news_link"]

        plugin = object.__new__(mod.DailySharePlugin)
        plugin.db = Db()
        plugin.task_manager = Manager()
        event = types.SimpleNamespace(unified_msg_origin="session-1")
        req = types.SimpleNamespace(system_prompt="基础提示", func_tool=Tools())

        asyncio.run(plugin.inject_news_link_context(event, req))

        self.assertIn("基础提示", req.system_prompt)
        self.assertIn("每日分享新闻缓存上下文", req.system_prompt)
        self.assertIn("最近新闻源：澎湃热搜", req.system_prompt)
        self.assertIn("可查条目数：2", req.system_prompt)
        self.assertIn("最近关注：第 2 条《第二条新闻》", req.system_prompt)
        self.assertIn("1. 第一条新闻", req.system_prompt)

    def test_news_link_context_skips_requests_without_news_tool(self):
        mod = _load_main_module()

        class Tools:
            def names(self):
                return ["daily_share"]

        plugin = object.__new__(mod.DailySharePlugin)
        event = types.SimpleNamespace(unified_msg_origin="session-1")
        req = types.SimpleNamespace(system_prompt="基础提示", func_tool=Tools())

        asyncio.run(plugin.inject_news_link_context(event, req))

        self.assertEqual(req.system_prompt, "基础提示")

    def test_news_link_reply_keeps_tool_returned_urls(self):
        mod = _load_main_module()
        plugin = object.__new__(mod.DailySharePlugin)

        urls = plugin._extract_news_link_urls(
            "标题：目标新闻\n短链接：http://qdls.top/?c=abc123\n摘要：内容"
        )
        reply = plugin._ensure_news_link_urls_in_reply("这条新闻是这样。", urls)

        self.assertEqual(urls, ["http://qdls.top/?c=abc123"])
        self.assertIn("这条新闻是这样。", reply)
        self.assertIn("http://qdls.top/?c=abc123", reply)

    def test_history_items_include_contact_alias_label(self):
        mod = _load_main_module()

        class CtxService:
            def _parse_umo(self, target):
                parts = str(target or "").split(":")
                if len(parts) >= 3:
                    return parts[0], ":".join(parts[2:])
                return None, None

        plugin = object.__new__(mod.DailySharePlugin)
        plugin.contact_aliases = ["123456:新闻群"]
        plugin.ctx_service = CtxService()

        items = asyncio.run(
            plugin._page_prepare_history_items(
                [
                    {
                        "target_id": "aiocqhttp:GroupMessage:123456",
                        "type": "news",
                    }
                ]
            )
        )

        self.assertEqual(items[0]["target_label"], "新闻群")

    def test_history_items_fetch_group_and_user_labels(self):
        mod = _load_main_module()
        calls = []

        class CtxService:
            def _parse_umo(self, target):
                parts = str(target or "").split(":")
                if len(parts) >= 3:
                    return parts[0], ":".join(parts[2:])
                return "", str(target or "")

            def _get_onebot_bot(self, target, adapter_id=""):
                return object()

            async def _bot_call_action(self, _bot, action, **params):
                calls.append((action, params))
                if action == "get_group_info":
                    return {"data": {"group_name": "新闻群"}}
                if action == "get_stranger_info":
                    return {"nickname": "小明"}
                raise AssertionError(action)

        plugin = object.__new__(mod.DailySharePlugin)
        plugin.contact_aliases = []
        plugin.ctx_service = CtxService()

        items = asyncio.run(
            plugin._page_prepare_history_items(
                [
                    {
                        "target_id": "aiocqhttp:GroupMessage:123456",
                        "type": "news",
                    },
                    {
                        "target_id": "aiocqhttp:FriendMessage:89761500",
                        "type": "mood",
                    },
                ]
            )
        )

        self.assertEqual(items[0]["target_label"], "新闻群")
        self.assertEqual(items[1]["target_label"], "小明")
        self.assertEqual(
            calls,
            [
                ("get_group_info", {"group_id": 123456}),
                ("get_stranger_info", {"user_id": 89761500}),
            ],
        )

    def test_local_image_path_gets_preview_when_media_type_is_missing(self):
        mod = _load_main_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            image_path = data_dir / "Temp" / "share.png"
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(base64.b64decode(PNG_1X1))

            plugin = object.__new__(mod.DailySharePlugin)
            plugin.data_dir = data_dir

            items = asyncio.run(
                plugin._page_prepare_media_items(
                    [
                        {
                            "media_type": "",
                            "media_url": "",
                            "media_path": "Temp/share.png",
                        }
                    ]
                )
            )

            self.assertEqual(items[0]["media_type"], "image")
            self.assertTrue(items[0]["preview_url"].startswith("data:image/"))

    def test_remote_image_url_gets_image_kind_when_media_type_is_missing(self):
        mod = _load_main_module()
        plugin = object.__new__(mod.DailySharePlugin)
        plugin.data_dir = Path(".")

        items = asyncio.run(
            plugin._page_prepare_media_items(
                [
                    {
                        "media_type": "",
                        "media_url": "https://example.com/share.webp?token=1",
                        "media_path": "",
                    }
                ]
            )
        )

        self.assertEqual(items[0]["media_type"], "image")
        self.assertEqual(items[0]["preview_url"], "https://example.com/share.webp?token=1")

    def test_local_media_path_is_preferred_over_remote_preview_url(self):
        mod = _load_main_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            image_path = data_dir / "Temp" / "share.png"
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(base64.b64decode(PNG_1X1))

            plugin = object.__new__(mod.DailySharePlugin)
            plugin.data_dir = data_dir

            items = asyncio.run(
                plugin._page_prepare_media_items(
                    [
                        {
                            "media_type": "image",
                            "media_url": "https://example.com/share.webp?token=1",
                            "media_path": "Temp/share.png",
                        }
                    ]
                )
            )

            self.assertTrue(items[0]["preview_url"].startswith("data:image/"))

    def test_view_image_payload_returns_downscaled_local_image(self):
        mod = _load_main_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            image_path = data_dir / "Temp" / "share.png"
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(base64.b64decode(PNG_1X1))

            plugin = object.__new__(mod.DailySharePlugin)
            plugin.data_dir = data_dir

            payload = asyncio.run(
                plugin._page_view_image_payload(
                    {"media_type": "image", "media_path": "Temp/share.png"},
                    7,
                )
            )

            self.assertEqual(payload["delivery"], "data")
            self.assertTrue(payload["view_url"].startswith("data:image/"))
            self.assertTrue(payload["version"])

    def test_page_media_view_returns_downscaled_local_image(self):
        mod = _load_main_module()

        class Db:
            async def get_history_by_id(self, history_id):
                return {
                    "id": history_id,
                    "media_type": "image",
                    "media_url": "",
                    "media_path": "Temp/share.png",
                }

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            image_path = data_dir / "Temp" / "share.png"
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(base64.b64decode(PNG_1X1))

            plugin = object.__new__(mod.DailySharePlugin)
            plugin.data_dir = data_dir
            plugin.db = Db()

            captured_headers = {}

            async def page_json(callback, headers=None):
                captured_headers.update(headers or {})
                return await callback()

            async def page_json_body():
                return {"history_id": 7}

            plugin._page_json = page_json
            plugin._page_json_body = page_json_body

            result = asyncio.run(plugin.page_media_view())

            self.assertEqual(result["data"]["id"], 7)
            self.assertEqual(result["data"]["delivery"], "data")
            self.assertTrue(result["data"]["view_url"].startswith("data:image/"))
            self.assertTrue(result["data"]["version"])
            self.assertEqual(
                captured_headers["Cache-Control"],
                f"private, max-age={mod._PAGE_MEDIA_CACHE_SECONDS}",
            )

    def test_view_image_payload_uses_remote_image_url(self):
        mod = _load_main_module()
        plugin = object.__new__(mod.DailySharePlugin)
        plugin.data_dir = Path(".")

        payload = asyncio.run(
            plugin._page_view_image_payload(
                {
                    "media_type": "image",
                    "media_url": "https://example.com/share.webp?token=1",
                    "media_path": "",
                },
                7,
            )
        )

        self.assertEqual(payload["delivery"], "url")
        self.assertEqual(payload["view_url"], "https://example.com/share.webp?token=1")

    def test_view_image_payload_prefers_local_path_over_remote_url(self):
        mod = _load_main_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            image_path = data_dir / "Temp" / "share.png"
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(base64.b64decode(PNG_1X1))

            plugin = object.__new__(mod.DailySharePlugin)
            plugin.data_dir = data_dir

            payload = asyncio.run(
                plugin._page_view_image_payload(
                    {
                        "media_type": "image",
                        "media_url": "https://example.com/share.webp?token=1",
                        "media_path": "Temp/share.png",
                    },
                    7,
                )
            )

            self.assertEqual(payload["delivery"], "data")
            self.assertTrue(payload["view_url"].startswith("data:image/"))

    def test_delete_local_media_file_removes_plugin_data_file(self):
        mod = _load_main_module()

        class Db:
            async def count_history_media_path_refs(self, _media_path):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            image_path = data_dir / "Temp" / "share.png"
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(base64.b64decode(PNG_1X1))

            plugin = object.__new__(mod.DailySharePlugin)
            plugin.data_dir = data_dir
            plugin.db = Db()

            result = asyncio.run(
                plugin._page_delete_local_media_files(
                    [{"media_path": "Temp/share.png"}]
                )
            )

            self.assertFalse(image_path.exists())
            self.assertEqual(result["deleted"], 1)
            self.assertGreater(result["bytes"], 0)

    def test_delete_local_media_file_skips_outside_plugin_data_dir(self):
        mod = _load_main_module()

        class Db:
            async def count_history_media_path_refs(self, _media_path):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            outside_path = root / "outside.png"
            outside_path.write_bytes(base64.b64decode(PNG_1X1))

            plugin = object.__new__(mod.DailySharePlugin)
            plugin.data_dir = data_dir
            plugin.db = Db()

            result = asyncio.run(
                plugin._page_delete_local_media_files(
                    [{"media_path": str(outside_path)}]
                )
            )

            self.assertTrue(outside_path.exists())
            self.assertEqual(result["deleted"], 0)
            self.assertEqual(result["skipped"], 1)

    def test_delete_local_media_file_skips_still_referenced_file(self):
        mod = _load_main_module()

        class Db:
            async def count_history_media_path_refs(self, _media_path):
                return 1

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            image_path = data_dir / "Temp" / "share.png"
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(base64.b64decode(PNG_1X1))

            plugin = object.__new__(mod.DailySharePlugin)
            plugin.data_dir = data_dir
            plugin.db = Db()

            result = asyncio.run(
                plugin._page_delete_local_media_files(
                    [{"media_path": "Temp/share.png"}]
                )
            )

            self.assertTrue(image_path.exists())
            self.assertEqual(result["deleted"], 0)
            self.assertEqual(result["skipped"], 1)

    def test_delete_daily_life_generated_media_file(self):
        mod = _load_main_module()

        class Db:
            async def count_history_media_refs(self, _media_refs):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "astrbot_plugin_daily_share"
            daily_life_file = (
                root
                / "astrbot_plugin_daily_life"
                / "generated_media"
                / "images"
                / "share.png"
            )
            daily_life_file.parent.mkdir(parents=True)
            daily_life_file.write_bytes(base64.b64decode(PNG_1X1))

            plugin = object.__new__(mod.DailySharePlugin)
            plugin.data_dir = data_dir
            plugin.db = Db()

            result = asyncio.run(
                plugin._page_delete_local_media_files(
                    [{"media_path": str(daily_life_file)}]
                )
            )

            self.assertFalse(daily_life_file.exists())
            self.assertEqual(result["deleted"], 1)
            self.assertEqual(result["skipped"], 0)

    def test_delete_daily_life_generated_media_file_skips_remaining_reference(self):
        mod = _load_main_module()

        class Db:
            def __init__(self):
                self.refs_seen = None

            async def count_history_media_refs(self, media_refs):
                self.refs_seen = set(media_refs)
                return 1

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "astrbot_plugin_daily_share"
            daily_life_file = (
                root
                / "astrbot_plugin_daily_life"
                / "generated_media"
                / "videos"
                / "share.mp4"
            )
            daily_life_file.parent.mkdir(parents=True)
            daily_life_file.write_bytes(b"video")

            db = Db()
            plugin = object.__new__(mod.DailySharePlugin)
            plugin.data_dir = data_dir
            plugin.db = db

            result = asyncio.run(
                plugin._page_delete_local_media_files(
                    [{"media_path": str(daily_life_file)}]
                )
            )

            self.assertTrue(daily_life_file.exists())
            self.assertEqual(result["deleted"], 0)
            self.assertEqual(result["skipped"], 1)
            self.assertIn("generated_media/videos/share.mp4", db.refs_seen)
            self.assertIn("videos/share.mp4", db.refs_seen)

    def test_delete_local_media_file_ignores_local_media_url(self):
        mod = _load_main_module()

        class Db:
            async def count_history_media_refs(self, _media_refs):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "astrbot_plugin_daily_share"
            daily_life_file = (
                root
                / "astrbot_plugin_daily_life"
                / "generated_media"
                / "images"
                / "share.png"
            )
            daily_life_file.parent.mkdir(parents=True)
            daily_life_file.write_bytes(base64.b64decode(PNG_1X1))

            plugin = object.__new__(mod.DailySharePlugin)
            plugin.data_dir = data_dir
            plugin.db = Db()

            result = asyncio.run(
                plugin._page_delete_local_media_files(
                    [{"media_url": str(daily_life_file)}]
                )
            )

            self.assertTrue(daily_life_file.exists())
            self.assertEqual(result["deleted"], 0)
            self.assertEqual(result["skipped"], 0)

if __name__ == "__main__":
    unittest.main()

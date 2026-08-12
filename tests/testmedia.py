import asyncio
import base64
import importlib
import sys
import tempfile
import time
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


class _DomainStateDb:
    async def _get_domain_state(self, key, default=None):
        return self.state.get(key, default if default is not None else {})

    async def _set_domain_state(self, key, value):
        self.state[key] = value

    async def _update_domain_state(self, key, updates):
        current = self.state.setdefault(key, {})
        current.update(updates)
        return current

    get_share_state = _get_domain_state
    get_qzone_state = _get_domain_state
    get_context_state = _get_domain_state
    get_cache_state = _get_domain_state
    set_share_state = _set_domain_state
    set_qzone_state = _set_domain_state
    set_context_state = _set_domain_state
    set_cache_state = _set_domain_state
    update_share_state = _update_domain_state
    update_qzone_state = _update_domain_state
    update_context_state = _update_domain_state
    update_cache_state = _update_domain_state


def _install_stub_modules():
    for name in list(sys.modules):
        if (
            name.startswith("astrbot")
            or name.startswith("apscheduler")
            or name == "aiohttp"
            or name == "aiofiles"
        ):
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
        def __init__(self, context):
            self.context = context

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
        PermissionType = types.SimpleNamespace(MEMBER="member")

        def __getattr__(self, _name):
            return lambda *args, **kwargs: lambda func: func

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


def _load_main_module():
    _install_stub_modules()
    if str(PACKAGE_ROOT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_ROOT))
    for name in list(sys.modules):
        if name.startswith("astrbot_plugin_daily_share"):
            sys.modules.pop(name, None)
    return importlib.import_module("astrbot_plugin_daily_share.main")


def _new_dashboard_service(mod):
    plugin = object.__new__(mod.DailySharePlugin)
    plugin.support_service = mod.SupportService(plugin)
    return mod.DashboardService(plugin).operations


def _new_plugin_with_support(mod):
    plugin = object.__new__(mod.DailySharePlugin)
    plugin.support_service = mod.SupportService(plugin)
    return plugin


class DashboardMediaPreviewTests(unittest.TestCase):
    def test_dashboard_exposes_runtime_health_state(self):
        status_source = (
            ROOT / "core" / "panel" / "routes" / "statusview.py"
        ).read_text(encoding="utf-8")
        view_source = (ROOT / "pages" / "dashboard" / "ui" / "status.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('"runtime": runtime_status', status_source)
        self.assertIn('configRow("运行状态", runtimeText, "is-runtime")', view_source)
        self.assertIn('failed: "初始化失败"', view_source)

    def test_degraded_stat_is_a_filterable_media_kind(self):
        status_source = (ROOT / "pages" / "dashboard" / "ui" / "status.js").read_text(
            encoding="utf-8"
        )
        kind_source = (ROOT / "core" / "panel" / "gallery" / "kind.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('mediaKind: "degraded"', status_source)
        self.assertIn('"degraded"', kind_source)

    def test_qzone_auto_interaction_delayed_job_uses_readable_dashboard_name(self):
        mod = _load_main_module()
        plugin = _new_dashboard_service(mod)

        display_name = plugin.jobs._page_job_display_name(
            "delayed_qzone_auto_interaction",
            "TaskSchedulerTriggerService._task_wrapper_qzone_auto_interaction.<locals>.execute_delayed_qzone_auto_interaction",
        )

        self.assertEqual(display_name, "QQ 空间自动互动延迟")
        self.assertNotIn("execute_delayed_qzone_auto_interaction", display_name)

    def test_calendar_hides_qzone_auto_source_when_pending_delay_exists(self):
        mod = _load_main_module()
        plugin = _new_dashboard_service(mod)

        calendar = plugin.jobs._page_calendar(
            [
                {
                    "id": "qzone_auto_interaction",
                    "display_name": "QQ 空间自动互动",
                    "next_run_time": "2026-07-05T16:30:00",
                    "trigger": "cron",
                },
                {
                    "id": "delayed_qzone_auto_interaction",
                    "display_name": "QQ 空间自动互动延迟",
                    "next_run_time": "2026-07-05T16:45:00",
                    "trigger": "date",
                },
            ]
        )

        items = calendar[0]["items"]
        self.assertEqual(
            [item["id"] for item in items], ["delayed_qzone_auto_interaction"]
        )
        self.assertEqual(items[0]["name"], "QQ 空间自动互动延迟")

    def test_calendar_keeps_next_qzone_auto_source_after_pending_delay(self):
        mod = _load_main_module()
        plugin = _new_dashboard_service(mod)

        calendar = plugin.jobs._page_calendar(
            [
                {
                    "id": "delayed_qzone_auto_interaction",
                    "display_name": "QQ 空间自动互动延迟",
                    "next_run_time": "2026-07-05T16:45:00",
                    "trigger": "date",
                },
                {
                    "id": "qzone_auto_interaction",
                    "display_name": "QQ 空间自动互动",
                    "next_run_time": "2026-07-05T18:30:00",
                    "trigger": "cron",
                },
            ]
        )

        items = calendar[0]["items"]
        self.assertEqual(
            [item["id"] for item in items],
            ["delayed_qzone_auto_interaction", "qzone_auto_interaction"],
        )

    def test_news_link_context_is_injected_for_news_tool_requests(self):
        mod = _load_main_module()

        class Db(_DomainStateDb):
            def __init__(self):
                self.state = {
                    "news_snapshot:session-1:focus": {
                        "source_key": "thepaper",
                        "index": 2,
                    },
                }

            async def get_latest_news_snapshot_with_focus(self, target_id, focus_key):
                if target_id != "session-1":
                    return None, {}
                snapshot = {
                    "source_key": "thepaper",
                    "source_name": "澎湃热搜",
                    "items": [
                        {"title": "第一条新闻", "url": "https://example.com/1"},
                        {"title": "第二条新闻", "url": "https://example.com/2"},
                    ],
                }
                return snapshot, self.state.get(focus_key, {})

        class Manager:
            snapshot_store = None

            def __init__(self):
                self.snapshot_store = self

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

        plugin = _new_plugin_with_support(mod)
        plugin.db = Db()
        plugin.task_manager = Manager()
        event = types.SimpleNamespace(unified_msg_origin="session-1")
        req = types.SimpleNamespace(
            system_prompt="基础提示",
            func_tool=Tools(),
            extra_user_content_parts=[],
        )

        asyncio.run(plugin.inject_tool_context(event, req))

        self.assertEqual(req.extra_user_content_parts, [])
        self.assertTrue(req.system_prompt.startswith("基础提示\n\n"))
        context_text = req.system_prompt
        self.assertIn("每日分享新闻缓存上下文", context_text)
        self.assertIn("最近新闻源：澎湃热搜", context_text)
        self.assertIn("可查条目数：2", context_text)
        self.assertIn("最近关注序号：2", context_text)
        self.assertNotIn("第一条新闻", context_text)
        self.assertNotIn("第二条新闻", context_text)
        self.assertNotIn("参数契约", context_text)

    def test_news_link_context_skips_requests_without_news_tool(self):
        mod = _load_main_module()

        class Tools:
            def names(self):
                return ["daily_share"]

        plugin = _new_plugin_with_support(mod)
        event = types.SimpleNamespace(unified_msg_origin="session-1")
        req = types.SimpleNamespace(
            system_prompt="基础提示",
            func_tool=Tools(),
            extra_user_content_parts=[],
        )

        asyncio.run(plugin.inject_tool_context(event, req))

        self.assertEqual(req.system_prompt, "基础提示")
        self.assertEqual(req.extra_user_content_parts, [])

    def test_qzone_context_is_injected_for_qzone_tool_requests(self):
        mod = _load_main_module()

        class Db(_DomainStateDb):
            def __init__(self):
                self.state = {
                    "qzone_context:session-1": {
                        "timestamp": time.time(),
                        "target_id": "100000001",
                        "target_label": "我的说说",
                        "focus_post_id": "100000001:tid-2",
                        "items": [
                            {
                                "index": 1,
                                "post_id": "100000001:tid-1",
                                "is_self": True,
                                "author": "好友甲",
                                "text": "第一条说说",
                                "created_at": 1700000000,
                                "images": 1,
                                "videos": 0,
                            },
                            {
                                "index": 2,
                                "post_id": "100000001:tid-2",
                                "author": "好友乙",
                                "text": "第二条说说",
                                "images": 0,
                                "videos": 0,
                            },
                        ],
                    }
                }

        class Tools:
            def names(self):
                return ["qzone"]

        plugin = _new_plugin_with_support(mod)
        plugin.db = Db()
        event = types.SimpleNamespace(unified_msg_origin="session-1")
        req = types.SimpleNamespace(
            system_prompt="基础提示",
            func_tool=Tools(),
            extra_user_content_parts=[],
        )

        asyncio.run(plugin.inject_tool_context(event, req))

        self.assertEqual(req.extra_user_content_parts, [])
        self.assertTrue(req.system_prompt.startswith("基础提示\n\n"))
        context_text = req.system_prompt
        self.assertIn("每日分享 QQ 空间上下文", context_text)
        self.assertIn("列表来源：我的说说", context_text)
        self.assertIn("需要列表、详情或操作时调用 qzone 工具", context_text)
        self.assertIn("最近关注 post_id：100000001:tid-2", context_text)
        self.assertIn("最近列表条数：2", context_text)
        self.assertNotIn("第一条说说", context_text)
        self.assertNotIn("第二条说说", context_text)
        self.assertNotIn("参数契约", context_text)
        self.assertNotIn("权限：", context_text)

    def test_qzone_context_is_injected_for_auto_interact_tool_requests(self):
        mod = _load_main_module()

        class Db(_DomainStateDb):
            def __init__(self):
                self.state = {
                    "qzone_context:session-1": {
                        "timestamp": time.time(),
                        "target_id": "100000001",
                        "target_label": "我的说说",
                        "focus_post_id": "100000001:tid-1",
                        "items": [
                            {
                                "index": 1,
                                "post_id": "100000001:tid-1",
                                "author": "好友甲",
                                "text": "第一条说说",
                                "images": 0,
                                "videos": 0,
                            }
                        ],
                    }
                }

        class Tools:
            def names(self):
                return ["qzone_auto_interact"]

        plugin = _new_plugin_with_support(mod)
        plugin.db = Db()
        event = types.SimpleNamespace(unified_msg_origin="session-1")
        req = types.SimpleNamespace(
            system_prompt="基础提示",
            func_tool=Tools(),
            extra_user_content_parts=[],
        )

        asyncio.run(plugin.inject_tool_context(event, req))

        self.assertEqual(req.extra_user_content_parts, [])
        self.assertIn("每日分享 QQ 空间上下文", req.system_prompt)

    def test_qzone_list_stores_recent_context_snapshot(self):
        mod = _load_main_module()

        class Post:
            def __init__(self, key, name, text, images=None):
                self.key = key
                self.name = name
                self.text = text
                self.rt_con = ""
                self.uin = 100000001
                self.create_time = 1700000000
                self.images = images or []
                self.videos = []
                self.comments = []

        class QzoneService:
            async def context(self):
                return types.SimpleNamespace(uin=100000001)

            async def query_posts(self, **kwargs):
                self.kwargs = kwargs
                return [Post("100000001:tid-1", "测试用户A", "第一条说说", ["pic.jpg"])]

        class Db(_DomainStateDb):
            def __init__(self):
                self.state = {}

        plugin = _new_plugin_with_support(mod)
        plugin._is_terminated = False
        plugin.support_service.operations.permissions._remember_event_adapter = (
            lambda event: None
        )
        plugin.support_service.operations.permissions._is_admin_event = lambda event: (
            True
        )
        plugin.qzone_service = QzoneService()
        plugin.db = Db()

        event = types.SimpleNamespace(unified_msg_origin="session-1")
        result = asyncio.run(
            plugin.support_service.run_qzone_tool(
                event, action="list", target_id="100000001"
            )
        )

        self.assertIn("当前查看：我的说说", result)
        self.assertIn("测试用户A（我的说说）", result)
        self.assertIn("ID: 100000001:tid-1", result)
        self.assertIn("发布时间:", result)
        snapshot = plugin.db.state["qzone_context:session-1"]
        self.assertEqual(snapshot["target_id"], "100000001")
        self.assertEqual(snapshot["target_label"], "我的说说")
        self.assertEqual(snapshot["focus_post_id"], "100000001:tid-1")
        self.assertEqual(snapshot["items"][0]["post_id"], "100000001:tid-1")
        self.assertEqual(snapshot["items"][0]["created_at"], 1700000000)
        self.assertEqual(snapshot["items"][0]["images"], 1)
        self.assertTrue(snapshot["items"][0]["is_self"])

    def test_qzone_detail_unavailable_clears_recent_focus(self):
        mod = _load_main_module()

        class QzoneService:
            async def context(self):
                return types.SimpleNamespace(uin=100000001)

            async def detail(self, post_id):
                raise RuntimeError("对不起，原文已经被删除，无法查看")

        class Db(_DomainStateDb):
            def __init__(self):
                self.state = {
                    "qzone_context:session-1": {
                        "timestamp": time.time(),
                        "focus_post_id": "100000001:stale",
                        "items": [{"post_id": "100000001:stale"}],
                    }
                }

        plugin = _new_plugin_with_support(mod)
        plugin._is_terminated = False
        plugin.support_service.operations.permissions._remember_event_adapter = (
            lambda event: None
        )
        plugin.support_service.operations.permissions._is_admin_event = lambda event: (
            True
        )
        plugin.qzone_service = QzoneService()
        plugin.db = Db()

        event = types.SimpleNamespace(unified_msg_origin="session-1")
        result = asyncio.run(
            plugin.support_service.run_qzone_tool(
                event, action="detail", post_id="100000001:stale"
            )
        )

        self.assertIn("已删除或暂时无法查看", result)
        self.assertIn("重新调用 qzone.list 获取最新说说列表", result)
        self.assertEqual(
            plugin.db.state["qzone_context:session-1"]["focus_post_id"], ""
        )

    def test_news_link_reply_keeps_tool_returned_urls(self):
        mod = _load_main_module()
        plugin = _new_plugin_with_support(mod)

        urls = plugin.support_service.extract_news_link_urls(
            "标题：目标新闻\n短链接：http://qdls.top/?c=abc123\n摘要：内容"
        )
        reply = plugin.support_service.ensure_news_link_urls_in_reply(
            "这条新闻是这样。", urls
        )

        self.assertEqual(urls, ["http://qdls.top/?c=abc123"])
        self.assertIn("这条新闻是这样。", reply)
        self.assertIn("http://qdls.top/?c=abc123", reply)

    def test_history_items_include_contact_alias_label(self):
        mod = _load_main_module()

        class CtxService:
            def parse_umo(self, target):
                parts = str(target or "").split(":")
                if len(parts) >= 3:
                    return parts[0], ":".join(parts[2:])
                return None, None

        plugin = _new_dashboard_service(mod)
        plugin.contact_aliases = ["123456:新闻群"]
        plugin.ctx_service = CtxService()

        items = asyncio.run(
            plugin.labels._page_prepare_history_items(
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
            def parse_umo(self, target):
                parts = str(target or "").split(":")
                if len(parts) >= 3:
                    return parts[0], ":".join(parts[2:])
                return "", str(target or "")

            def get_onebot_bot(self, target, adapter_id=""):
                return object()

            async def call_onebot_action(self, _bot, action, **params):
                calls.append((action, params))
                if action == "get_group_info":
                    return {"data": {"group_name": "新闻群"}}
                if action == "get_stranger_info":
                    return {"nickname": "小明"}
                raise AssertionError(action)

        plugin = _new_dashboard_service(mod)
        plugin.contact_aliases = []
        plugin.ctx_service = CtxService()

        items = asyncio.run(
            plugin.labels._page_prepare_history_items(
                [
                    {
                        "target_id": "aiocqhttp:GroupMessage:123456",
                        "type": "news",
                    },
                    {
                        "target_id": "aiocqhttp:FriendMessage:100000002",
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
                ("get_stranger_info", {"user_id": 100000002}),
            ],
        )

    def test_local_image_path_gets_preview_when_media_type_is_missing(self):
        mod = _load_main_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            image_path = data_dir / "Temp" / "share.png"
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(base64.b64decode(PNG_1X1))

            plugin = _new_dashboard_service(mod)
            plugin.data_dir = data_dir

            items = asyncio.run(
                plugin.media_preview._page_prepare_media_items(
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
        plugin = _new_dashboard_service(mod)
        plugin.data_dir = Path(".")

        items = asyncio.run(
            plugin.media_preview._page_prepare_media_items(
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
        self.assertEqual(
            items[0]["preview_url"], "https://example.com/share.webp?token=1"
        )

    def test_local_media_path_is_preferred_over_remote_preview_url(self):
        mod = _load_main_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            image_path = data_dir / "Temp" / "share.png"
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(base64.b64decode(PNG_1X1))

            plugin = _new_dashboard_service(mod)
            plugin.data_dir = data_dir

            items = asyncio.run(
                plugin.media_preview._page_prepare_media_items(
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

            plugin = _new_dashboard_service(mod)
            plugin.data_dir = data_dir

            payload = asyncio.run(
                plugin.media_preview._page_view_image_payload(
                    {"media_type": "image", "media_path": "Temp/share.png"},
                    7,
                )
            )

            self.assertEqual(payload["delivery"], "data")
            self.assertTrue(payload["view_url"].startswith("data:image/"))
            self.assertNotIn("version", payload)

    def test_page_media_view_returns_downscaled_local_image(self):
        mod = _load_main_module()

        class Db(_DomainStateDb):
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

            plugin = _new_dashboard_service(mod)
            plugin.data_dir = data_dir
            plugin.db = Db()

            captured_headers = {}

            async def page_json(callback, headers=None):
                captured_headers.update(headers or {})
                return await callback()

            async def page_json_body():
                return {"history_id": 7}

            plugin.server._page_json = page_json
            plugin.server._page_json_body = page_json_body

            result = asyncio.run(plugin.media_page.page_media_view())

            self.assertEqual(result["data"]["id"], 7)
            self.assertEqual(result["data"]["delivery"], "data")
            self.assertTrue(result["data"]["view_url"].startswith("data:image/"))
            self.assertNotIn("version", result["data"])
            self.assertEqual(
                captured_headers["Cache-Control"],
                f"private, max-age={mod._PAGE_MEDIA_CACHE_SECONDS}",
            )

    def test_view_image_payload_uses_remote_image_url(self):
        mod = _load_main_module()
        plugin = _new_dashboard_service(mod)
        plugin.data_dir = Path(".")

        payload = asyncio.run(
            plugin.media_preview._page_view_image_payload(
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

            plugin = _new_dashboard_service(mod)
            plugin.data_dir = data_dir

            payload = asyncio.run(
                plugin.media_preview._page_view_image_payload(
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

        class Db(_DomainStateDb):
            async def count_history_media_refs(self, _media_refs):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            image_path = data_dir / "Temp" / "share.png"
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(base64.b64decode(PNG_1X1))

            plugin = _new_dashboard_service(mod)
            plugin.data_dir = data_dir
            plugin.db = Db()

            result = asyncio.run(
                plugin.media_files._page_delete_local_media_files(
                    [{"media_path": "Temp/share.png"}]
                )
            )

            self.assertFalse(image_path.exists())
            self.assertEqual(result["deleted"], 1)
            self.assertGreater(result["bytes"], 0)

    def test_delete_local_media_file_skips_outside_managed_directories(self):
        mod = _load_main_module()

        class Db(_DomainStateDb):
            async def count_history_media_refs(self, _media_refs):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            outside_path = root / "outside.png"
            outside_path.write_bytes(base64.b64decode(PNG_1X1))

            plugin = _new_dashboard_service(mod)
            plugin.data_dir = data_dir
            plugin.db = Db()

            result = asyncio.run(
                plugin.media_files._page_delete_local_media_files(
                    [{"media_path": str(outside_path)}]
                )
            )

            self.assertTrue(outside_path.exists())
            self.assertEqual(result["deleted"], 0)
            self.assertEqual(result["skipped"], 1)

    def test_delete_local_media_file_skips_symlink_escape(self):
        mod = _load_main_module()

        class Db(_DomainStateDb):
            async def count_history_media_refs(self, _media_refs):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "astrbot_plugin_daily_share"
            temp_dir = data_dir / "Temp"
            temp_dir.mkdir(parents=True)
            outside_path = root / "outside.png"
            outside_path.write_bytes(base64.b64decode(PNG_1X1))
            symlink_path = temp_dir / "share.png"
            try:
                symlink_path.symlink_to(outside_path)
            except OSError as exc:
                self.skipTest(f"当前环境不支持符号链接测试: {exc}")

            plugin = _new_dashboard_service(mod)
            plugin.data_dir = data_dir
            plugin.db = Db()

            result = asyncio.run(
                plugin.media_files._page_delete_local_media_files(
                    [{"media_path": str(symlink_path)}]
                )
            )

            self.assertTrue(symlink_path.exists())
            self.assertTrue(outside_path.exists())
            self.assertEqual(result["deleted"], 0)
            self.assertEqual(result["skipped"], 1)

    def test_delete_local_media_file_skips_still_referenced_file(self):
        mod = _load_main_module()

        class Db(_DomainStateDb):
            async def count_history_media_refs(self, _media_refs):
                return 1

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            image_path = data_dir / "Temp" / "share.png"
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(base64.b64decode(PNG_1X1))

            plugin = _new_dashboard_service(mod)
            plugin.data_dir = data_dir
            plugin.db = Db()

            result = asyncio.run(
                plugin.media_files._page_delete_local_media_files(
                    [{"media_path": "Temp/share.png"}]
                )
            )

            self.assertTrue(image_path.exists())
            self.assertEqual(result["deleted"], 0)
            self.assertEqual(result["skipped"], 1)

    def test_delete_daily_life_generated_file_used_by_share(self):
        mod = _load_main_module()

        class Db(_DomainStateDb):
            async def count_history_media_refs(self, _media_refs):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "astrbot_plugin_daily_share"
            daily_life_file = (
                root
                / "astrbot_plugin_daily_life"
                / "generated"
                / "images"
                / "share.png"
            )
            daily_life_file.parent.mkdir(parents=True)
            daily_life_file.write_bytes(base64.b64decode(PNG_1X1))

            plugin = _new_dashboard_service(mod)
            plugin.data_dir = data_dir
            plugin.db = Db()

            result = asyncio.run(
                plugin.media_files._page_delete_local_media_files(
                    [{"media_path": str(daily_life_file)}]
                )
            )

            self.assertFalse(daily_life_file.exists())
            self.assertEqual(result["deleted"], 1)
            self.assertEqual(result["skipped"], 0)

    def test_delete_local_media_file_ignores_local_media_url(self):
        mod = _load_main_module()

        class Db(_DomainStateDb):
            async def count_history_media_refs(self, _media_refs):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "astrbot_plugin_daily_share"
            daily_life_file = (
                root
                / "astrbot_plugin_daily_life"
                / "generated"
                / "images"
                / "share.png"
            )
            daily_life_file.parent.mkdir(parents=True)
            daily_life_file.write_bytes(base64.b64decode(PNG_1X1))

            plugin = _new_dashboard_service(mod)
            plugin.data_dir = data_dir
            plugin.db = Db()

            result = asyncio.run(
                plugin.media_files._page_delete_local_media_files(
                    [{"media_url": str(daily_life_file)}]
                )
            )

            self.assertTrue(daily_life_file.exists())
            self.assertEqual(result["deleted"], 0)
            self.assertEqual(result["skipped"], 0)


if __name__ == "__main__":
    unittest.main()

import asyncio
import importlib
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "daily_share_tasks_testpkg"
CORE_PACKAGE_NAME = f"{PACKAGE_NAME}.core"
CONFIG_MODULE_NAME = f"{CORE_PACKAGE_NAME}.config"
CONSTANTS_MODULE_NAME = f"{CORE_PACKAGE_NAME}.constants"
DATABASE_PACKAGE_NAME = f"{CORE_PACKAGE_NAME}.database"
KEYS_MODULE_NAME = f"{DATABASE_PACKAGE_NAME}.keys"
TASKS_MODULE_NAME = f"{CORE_PACKAGE_NAME}.tasks"

YICAI_NAME = "\u7b2c\u4e00\u8d22\u7ecf\u70ed\u641c"


class _Logger:
    def debug(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None


class _MessageChain:
    def __init__(self, *items):
        self.items = list(items)
        self.chain = self.items

    @classmethod
    def chain(cls):
        return cls()

    def message(self, *items):
        self.items.extend(items)
        return self

    def file_image(self, item):
        self.items.append(("file_image", item))
        return self

    def url_image(self, item):
        self.items.append(("url_image", item))
        return self


class _Record:
    def __init__(self, file=None, **kwargs):
        self.file = file
        self.kwargs = kwargs


class _Video:
    def __init__(self, source):
        self.source = source

    @classmethod
    def fromURL(cls, url):
        return cls(("url_video", url))

    @classmethod
    def fromFileSystem(cls, path):
        return cls(("file_video", path))


class _MessageType(Enum):
    GROUP_MESSAGE = "GroupMessage"
    FRIEND_MESSAGE = "FriendMessage"


class _MessageSession:
    def __init__(self, platform_name, message_type, session_id):
        self.platform_name = platform_name
        self.platform_id = platform_name
        self.message_type = message_type
        self.session_id = session_id

    def __str__(self):
        return f"{self.platform_id}:{self.message_type.value}:{self.session_id}"


class _EmojiBot:
    def __init__(self):
        self.calls = []

    async def set_msg_emoji_like(self, **kwargs):
        self.calls.append(kwargs)


class _Event:
    def __init__(
        self,
        sender_id="123",
        unified_msg_origin="aiocqhttp:GroupMessage:123",
        bot=None,
        message_id=None,
    ):
        self.sent = []
        self._sender_id = sender_id
        self.unified_msg_origin = unified_msg_origin
        if bot is not None:
            self.bot = bot
        if message_id is not None:
            self.message_obj = types.SimpleNamespace(
                message_id=message_id,
                raw_message={"message_id": message_id},
            )

    def plain_result(self, text):
        return text

    def image_result(self, image):
        return ("image", image)

    def get_sender_id(self):
        return self._sender_id

    def get_sender_name(self):
        return "sender"

    async def send(self, message):
        self.sent.append(message)


class _Db:
    def __init__(self):
        self.history = []
        self.state = {}

    async def get_state(self, key, default=None):
        return self.state.get(key, default if default is not None else {})

    async def update_state_dict(self, key, updates):
        current = self.state.setdefault(key, {})
        current.update(updates)
        return None

    async def set_state(self, key, value):
        self.state[key] = value
        return None

    async def add_sent_history(self, *args, **kwargs):
        self.history.append((args, kwargs))

    async def get_recent_history_by_target(self, target_id, limit=3):
        return []


class _CtxService:
    async def get_life_context(self):
        return {}

    def _parse_umo(self, target):
        return "aiocqhttp", str(target).split(":")[-1]

    def _is_group_chat(self, target):
        return "group" in str(target).lower()

    def _is_weixin_platform(self, target):
        return str(target).endswith("@im.wechat")

    def _is_onebot_event(self, event):
        return False

    def _find_plugin(self, name):
        return types.SimpleNamespace(service=object())

    async def get_history_data(self, *args, **kwargs):
        return {}

    def check_group_strategy(self, *args, **kwargs):
        return True

    def format_history_prompt(self, *args, **kwargs):
        return ""

    def format_life_context(self, *args, **kwargs):
        return ""

    async def record_bot_reply_to_history(self, *args, **kwargs):
        return None

    async def record_to_memos(self, *args, **kwargs):
        return None


class _NewsService:
    def select_news_source(self, excluded_source=None):
        return "yicai"

    async def get_hot_news(self, source=None, limit=None, allow_fallback=True):
        return None


class _ImageService:
    def __init__(self):
        self.generated = []

    def reset_last_description(self):
        return None

    def get_last_description(self):
        return ""

    async def generate_image(self, content, share_type, life_context=None, target_umo=None, event=None):
        if share_type is None:
            raise AssertionError("share_type should be resolved before image generation")
        self.generated.append(
            {
                "content": content,
                "share_type": share_type,
                "life_context": life_context,
                "target_umo": target_umo,
            }
        )
        return "generated.png"

    async def generate_video_from_image(self, image_path, content, target_umo=None, event=None):
        return "generated.mp4"


class _ContentService:
    def __init__(self):
        self.calls = []

    async def generate(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return "content"


class _Scheduler:
    def __init__(self):
        self.jobs = []

    def add_job(self, func, trigger, **kwargs):
        self.jobs.append({"func": func, "trigger": trigger, "kwargs": kwargs})

    def get_job(self, job_id):
        for job in self.jobs:
            if job["kwargs"].get("id") == job_id:
                return job
        return None

    def get_jobs(self):
        return list(self.jobs)

    def remove_job(self, job_id):
        self.jobs = [job for job in self.jobs if job["kwargs"].get("id") != job_id]


class _Plugin:
    def __init__(self):
        self.scheduler = _Scheduler()
        self.db = _Db()
        self.ctx_service = _CtxService()
        self.news_service = _NewsService()
        self.image_service = _ImageService()
        self.content_service = _ContentService()
        self._lock = asyncio.Lock()
        self.basic_conf = {"share_type": "auto"}
        self.extra_shares_conf = {}
        self.qzone_conf = {}
        self.image_conf = {}
        self.tts_conf = {}
        self.context_conf = {}
        self.receiver_conf = {"groups": [], "users": []}
        self.config = {}
        self.data_dir = ROOT
        self.context = types.SimpleNamespace()
        self._cached_adapter_id = "aiocqhttp"
        self._is_terminated = False
        self._bg_tasks = set()
        self._last_share_time = None

    def _track_task(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            coro.close()
            return None
        task = loop.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task


def _clear_modules():
    for name in list(sys.modules):
        if name.startswith(PACKAGE_NAME) or name in {
            "astrbot",
            "astrbot.api",
            "astrbot.api.event",
            "astrbot.api.message_components",
            "astrbot.core",
            "astrbot.core.cron",
            "astrbot.core.cron.events",
            "astrbot.core.platform",
            "astrbot.core.platform.message_session",
            "astrbot.core.platform.message_type",
            "aiofiles",
            "aiohttp",
        }:
            sys.modules.pop(name, None)


def _install_stub_module(name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _load_tasks_module():
    _clear_modules()

    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(ROOT)]
    sys.modules[PACKAGE_NAME] = package

    core_package = types.ModuleType(CORE_PACKAGE_NAME)
    core_package.__path__ = [str(ROOT / "core")]
    sys.modules[CORE_PACKAGE_NAME] = core_package

    database_package = types.ModuleType(DATABASE_PACKAGE_NAME)
    database_package.__path__ = [str(ROOT / "core" / "database")]
    sys.modules[DATABASE_PACKAGE_NAME] = database_package

    _install_stub_module("astrbot")
    _install_stub_module("astrbot.api", logger=_Logger())
    _install_stub_module(
        "astrbot.api.event",
        AstrMessageEvent=type("AstrMessageEvent", (), {}),
        MessageChain=_MessageChain,
    )
    _install_stub_module(
        "astrbot.api.message_components",
        Record=_Record,
        Video=_Video,
    )
    _install_stub_module("astrbot.core")
    _install_stub_module("astrbot.core.platform")
    _install_stub_module(
        "astrbot.core.platform.message_session",
        MessageSesion=_MessageSession,
    )
    _install_stub_module(
        "astrbot.core.platform.message_type",
        MessageType=_MessageType,
    )
    _install_stub_module("aiofiles")
    _install_stub_module("aiohttp")

    _load_module(CONFIG_MODULE_NAME, ROOT / "core" / "config.py")
    _load_module(CONSTANTS_MODULE_NAME, ROOT / "core" / "constants.py")
    _load_module(KEYS_MODULE_NAME, ROOT / "core" / "database" / "keys.py")
    return importlib.import_module(TASKS_MODULE_NAME)


def _manager(mod):
    manager = mod.TaskManager(_Plugin())
    manager.get_curr_period = lambda: mod.TimePeriod.NIGHT
    return manager


class TaskFailureMessageTests(unittest.IsolatedAsyncioTestCase):
    def test_log_exception_includes_exception_type_when_message_empty(self):
        _clear_modules()

        logger = _Logger()
        _install_stub_module("astrbot")
        _install_stub_module("astrbot.api", logger=logger)

        toolkit = _load_module(
            f"{PACKAGE_NAME}.core.toolkit",
            ROOT / "core" / "toolkit.py",
        )

        errors = []

        def capture_error(*args, **kwargs):
            errors.append((args, kwargs))

        logger.error = capture_error

        toolkit.log_exception("[每日分享] 测试异常日志", RuntimeError())

        self.assertEqual(len(errors), 1)
        message = errors[0][0][0]
        self.assertEqual(message, "[每日分享] 测试异常日志: RuntimeError")
        self.assertIn("exc_info", errors[0][1])

    async def test_daily_life_media_tool_logs_exception_type_when_message_empty(self):
        _clear_modules()

        logger = _Logger()
        _install_stub_module("astrbot")
        _install_stub_module("astrbot.api", logger=logger)

        toolkit = _load_module(
            f"{PACKAGE_NAME}.core.toolkit",
            ROOT / "core" / "toolkit.py",
        )

        errors = []

        def capture_error(*args, **kwargs):
            errors.append((args, kwargs))

        logger.error = capture_error

        class DailyLifeImage:
            async def generate_image(self, prompt):
                raise RuntimeError()

        class Context:
            def get_all_stars(self):
                runtime = types.SimpleNamespace(
                    media=types.SimpleNamespace(image=DailyLifeImage())
                )
                plugin = types.SimpleNamespace(runtime=runtime)
                return [
                    types.SimpleNamespace(
                        name="astrbot_plugin_daily_life",
                        root_dir_name="astrbot_plugin_daily_life",
                        display_name="daily_life",
                        star_cls=plugin,
                    )
                ]

        result = await toolkit.call_default_daily_life_media_tool(
            Context(),
            media_kind="image",
            prompt="图片提示词",
        )

        self.assertIsNone(result)
        self.assertEqual(len(errors), 1)
        message = errors[0][0][0]
        self.assertIn("默认配图工具调用失败", message)
        self.assertTrue(message.endswith("RuntimeError"))
        self.assertNotIn("exc_info", errors[0][1])

    async def test_daily_life_media_tool_logs_missing_result_path(self):
        _clear_modules()

        logger = _Logger()
        _install_stub_module("astrbot")
        _install_stub_module("astrbot.api", logger=logger)

        toolkit = _load_module(
            f"{PACKAGE_NAME}.core.toolkit",
            ROOT / "core" / "toolkit.py",
        )

        warnings = []
        logger.warning = lambda *args, **kwargs: warnings.append((args, kwargs))

        class DailyLifeImage:
            async def generate_image(self, prompt):
                return types.SimpleNamespace(path="")

        class Context:
            def get_all_stars(self):
                runtime = types.SimpleNamespace(
                    media=types.SimpleNamespace(image=DailyLifeImage())
                )
                plugin = types.SimpleNamespace(runtime=runtime)
                return [
                    types.SimpleNamespace(
                        name="astrbot_plugin_daily_life",
                        root_dir_name="astrbot_plugin_daily_life",
                        display_name="daily_life",
                        star_cls=plugin,
                    )
                ]

        result = await toolkit.call_default_daily_life_media_tool(
            Context(),
            media_kind="image",
            prompt="图片提示词",
        )

        self.assertIsNone(result)
        self.assertTrue(any("未返回有效 path" in item[0][0] for item in warnings))

    def test_news_image_filename_uses_source_key_and_long_random_suffix(self):
        mod = _load_tasks_module()
        delivery_mod = sys.modules[f"{TASKS_MODULE_NAME}.delivery"]
        manager = mod.TaskManager(_Plugin())

        old_getrandbits = delivery_mod.random.getrandbits
        delivery_mod.random.getrandbits = lambda bits: 0x8005CE727817
        try:
            url = "https://api.nycnm.cn/api/v2/wb?format=image&apikey=test"
            self.assertEqual(
                manager._build_news_image_filename(url),
                "weibo_8005ce727817.png",
            )
            self.assertEqual(
                manager._build_news_image_filename(url),
                "weibo_8005ce727817.png",
            )

            safe_name = manager._build_news_image_filename(
                "https://example.com/news.jpg?format=image",
                'A/B:C*?<>|"',
            )
            self.assertEqual(safe_name, "A_B_C_8005ce727817.jpg")

            static_name = manager._build_news_image_filename(
                "https://example.com/60s",
                "60s新闻",
            )
            self.assertEqual(static_name, "60s_8005ce727817.png")

            ai_name = manager._build_news_image_filename(
                "https://example.com/ai",
                "AI资讯快报",
            )
            self.assertEqual(ai_name, "ai_8005ce727817.png")
        finally:
            delivery_mod.random.getrandbits = old_getrandbits

    def test_news_source_image_cleanup_keeps_latest_managed_files_only(self):
        mod = _load_tasks_module()
        plugin = _Plugin()

        with tempfile.TemporaryDirectory() as temp_root:
            plugin.data_dir = temp_root
            temp_dir = Path(temp_root) / "Temp"
            temp_dir.mkdir()
            manager = mod.TaskManager(plugin)

            names = [
                "weibo_000000000001.png",
                "zhihu_000000000002.jpg",
                "ai_000000000003.png",
                "weixin_send_000000000004.jpg",
                "generated.png",
                "global_hot_news.png",
                "weibo_notrandom.png",
            ]
            for index, name in enumerate(names):
                path = temp_dir / name
                path.write_bytes(name.encode("utf-8"))
                os.utime(path, (1000 + index, 1000 + index))

            manager._cleanup_news_source_images_sync(2)

            remaining = {path.name for path in temp_dir.iterdir()}
            self.assertNotIn("weibo_000000000001.png", remaining)
            self.assertIn("zhihu_000000000002.jpg", remaining)
            self.assertIn("ai_000000000003.png", remaining)
            self.assertIn("weixin_send_000000000004.jpg", remaining)
            self.assertIn("generated.png", remaining)
            self.assertIn("global_hot_news.png", remaining)
            self.assertIn("weibo_notrandom.png", remaining)

    def test_setup_cleanup_tasks_registers_news_image_cleanup_job(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = mod.TaskManager(plugin)

        manager.setup_cleanup_tasks()

        job_ids = {job["kwargs"].get("id") for job in plugin.scheduler.jobs}
        self.assertIn("weixin_temp_cleanup", job_ids)
        self.assertIn("news_image_cleanup", job_ids)

    async def test_plugin_terminate_cancels_tracked_background_tasks(self):
        _clear_modules()

        package = _install_stub_module(PACKAGE_NAME)
        package.__path__ = [str(ROOT)]
        core_package = _install_stub_module(CORE_PACKAGE_NAME)
        core_package.__path__ = [str(ROOT / "core")]
        host_package = _install_stub_module(f"{CORE_PACKAGE_NAME}.host")
        host_package.__path__ = [str(ROOT / "core" / "host")]
        logger = _Logger()
        _install_stub_module("astrbot")
        _install_stub_module("astrbot.api", logger=logger)
        _load_module(
            f"{CORE_PACKAGE_NAME}.toolkit",
            ROOT / "core" / "toolkit.py",
        )

        lifecycle = _load_module(
            f"{PACKAGE_NAME}.core.host.lifecycle",
            ROOT / "core" / "host" / "lifecycle.py",
        )

        class Scheduler:
            running = False

            def shutdown(self, wait=False):
                return None

        class Host(lifecycle.PluginRuntimeMixin):
            def __init__(self):
                self._is_terminated = False
                self._bg_tasks = set()
                self._lock = asyncio.Lock()
                self._target_locks = {}
                self.scheduler = Scheduler()
                self.qzone_service = types.SimpleNamespace(close=lambda: asyncio.sleep(0))

        started = asyncio.Event()

        async def never_finishes():
            started.set()
            await asyncio.Event().wait()

        host = Host()
        task = host._track_task(never_finishes())
        await asyncio.wait_for(started.wait(), timeout=1)

        await host.terminate()

        self.assertTrue(host._is_terminated)
        self.assertTrue(task.cancelled())
        self.assertEqual(host._bg_tasks, set())

    def test_qzone_auto_interaction_interval_query_jobs_are_registered(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.qzone_conf = {
            "qzone_enable_auto_interaction": True,
            "qzone_enable_auto_comment": True,
            "qzone_enable_auto_reply": True,
            "qzone_auto_interaction_interval_minutes": 45,
        }
        manager = mod.TaskManager(plugin)

        manager.setup_qzone_auto_interaction_cron()

        jobs = {job["kwargs"].get("id"): job for job in plugin.scheduler.jobs}
        self.assertEqual(jobs["qzone_auto_interaction"]["trigger"], "interval")
        self.assertEqual(jobs["qzone_auto_interaction"]["kwargs"]["minutes"], 45)
        self.assertNotIn("qzone_auto_comment", jobs)
        self.assertNotIn("qzone_auto_reply", jobs)

    def test_qzone_auto_interaction_cron_uses_unified_schedule(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.qzone_conf = {
            "qzone_enable_auto_interaction": True,
            "qzone_enable_auto_comment": True,
            "qzone_auto_interaction_interval_minutes": 0,
            "qzone_auto_interaction_cron": "15 */3 * * *",
        }
        manager = mod.TaskManager(plugin)

        manager.setup_qzone_auto_interaction_cron()

        jobs = {job["kwargs"].get("id"): job for job in plugin.scheduler.jobs}
        self.assertEqual(jobs["qzone_auto_interaction"]["trigger"], "cron")
        self.assertEqual(jobs["qzone_auto_interaction"]["kwargs"]["minute"], "15")
        self.assertEqual(jobs["qzone_auto_interaction"]["kwargs"]["hour"], "*/3")

    def test_news_tool_index_only_accepts_structured_number(self):
        mod = _load_tasks_module()
        manager = mod.TaskManager(_Plugin())

        self.assertEqual(manager._coerce_news_tool_index("10"), 10)
        self.assertEqual(manager._coerce_news_tool_index("１２"), 12)
        self.assertIsNone(manager._coerce_news_tool_index("第10条链接"))
        self.assertIsNone(manager._coerce_news_tool_index("刚才第十条原文"))

    async def test_cache_news_snapshot_fetches_complete_source_list(self):
        mod = _load_tasks_module()
        plugin = _Plugin()

        class NewsService(_NewsService):
            def __init__(self):
                self.calls = []

            async def get_hot_news(self, source=None, limit=None, allow_fallback=True):
                self.calls.append((source, limit, allow_fallback))
                return (
                    [
                        {"title": f"新闻{i}", "url": f"https://example.com/{i}"}
                        for i in range(1, 8)
                    ],
                    source,
                )

        plugin.news_service = NewsService()
        manager = mod.TaskManager(plugin)

        ok = await manager.cache_news_snapshot(
            "aiocqhttp:GroupMessage:123",
            news_data=([{"title": "新闻1", "url": "https://example.com/1"}], "zhihu"),
        )

        snapshot = plugin.db.state[manager._news_snapshot_key("aiocqhttp:GroupMessage:123")]
        self.assertTrue(ok)
        self.assertEqual(plugin.news_service.calls, [("zhihu", 50, False)])
        self.assertEqual(len(snapshot["items"]), 7)
        self.assertEqual(snapshot["items"][6]["url"], "https://example.com/7")

    async def test_cached_news_link_keeps_same_target_source_snapshots(self):
        mod = _load_tasks_module()
        plugin = _Plugin()

        class NewsService(_NewsService):
            async def get_hot_news(self, source=None, limit=None, allow_fallback=True):
                return (
                    [
                        {"title": f"{source}新闻{i}", "url": f"https://example.com/{source}/{i}"}
                        for i in range(1, 3)
                    ],
                    source,
                )

        plugin.news_service = NewsService()
        manager = mod.TaskManager(plugin)
        target = "aiocqhttp:GroupMessage:123"

        await manager.cache_news_snapshot(
            target,
            news_data=([{"title": "知乎新闻1", "url": "https://example.com/zhihu/1"}], "zhihu"),
        )
        await manager.cache_news_snapshot(
            target,
            news_data=([{"title": "澎湃新闻1", "url": "https://example.com/thepaper/1"}], "thepaper"),
        )

        result = await manager.get_cached_news_link(
            target,
            index="2",
            source_key="zhihu",
            refresh_source=False,
        )

        self.assertIn("zhihu新闻2", result)
        self.assertIn("https://example.com/zhihu/2", result)
        self.assertNotIn("thepaper", result)

    async def test_get_cached_news_link_uses_short_url(self):
        mod = _load_tasks_module()
        plugin = _Plugin()

        class NewsService(_NewsService):
            def __init__(self):
                self.seen_url = None

            async def shorten_url(self, url):
                self.seen_url = url
                return "http://qdls.top/?c=abc123"

        plugin.news_service = NewsService()
        manager = mod.TaskManager(plugin)
        plugin.db.state[manager._news_snapshot_key("aiocqhttp:GroupMessage:123")] = {
            "source_name": YICAI_NAME,
            "items": [
                {
                    "title": "目标新闻",
                    "url": "https://www.36kr.com/p/3841823029447170",
                    "description": "这是一条摘要",
                }
            ],
        }

        result = await manager.get_cached_news_link(
            "aiocqhttp:GroupMessage:123",
            index="1",
            refresh_source=False,
        )

        self.assertEqual(
            plugin.news_service.seen_url,
            "https://www.36kr.com/p/3841823029447170",
        )
        self.assertIn("http://qdls.top/?c=abc123", result)
        self.assertNotIn("https://www.36kr.com/p/3841823029447170", result)
        self.assertIn("摘要：这是一条摘要", result)

    async def test_get_cached_news_link_keeps_original_url_when_shortener_fails(self):
        mod = _load_tasks_module()
        plugin = _Plugin()

        class NewsService(_NewsService):
            async def shorten_url(self, url):
                raise RuntimeError("shortener unavailable")

        plugin.news_service = NewsService()
        manager = mod.TaskManager(plugin)
        plugin.db.state[manager._news_snapshot_key("aiocqhttp:GroupMessage:123")] = {
            "source_name": YICAI_NAME,
            "items": [
                {
                    "title": "目标新闻",
                    "url": "https://example.com/original",
                }
            ],
        }

        result = await manager.get_cached_news_link(
            "aiocqhttp:GroupMessage:123",
            query="目标",
            refresh_source=False,
        )

        self.assertIn("https://example.com/original", result)

    async def test_get_cached_news_link_reuses_last_focused_item_for_followup(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = mod.TaskManager(plugin)
        target = "aiocqhttp:GroupMessage:123"
        plugin.db.state[manager._news_snapshot_key(target)] = {
            "source_key": "yicai",
            "source_name": YICAI_NAME,
            "items": [
                {
                    "title": "第一条新闻",
                    "url": "https://example.com/1",
                    "description": "第一条摘要",
                },
                {
                    "title": "第二条新闻",
                    "url": "https://example.com/2",
                    "description": "第二条摘要",
                },
            ],
        }

        first = await manager.get_cached_news_link(
            target,
            index="2",
            refresh_source=False,
        )
        followup = await manager.get_cached_news_link(
            target,
            action="summary",
            refresh_source=False,
        )

        self.assertIn("第二条新闻", first)
        self.assertIn("第二条新闻", followup)
        self.assertIn("摘要：第二条摘要", followup)

    async def test_get_cached_news_link_returns_source_detail(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = mod.TaskManager(plugin)
        target = "aiocqhttp:GroupMessage:123"
        plugin.db.state[manager._news_snapshot_key(target)] = {
            "source_key": "yicai",
            "source_name": YICAI_NAME,
            "items": [
                {
                    "title": "目标新闻",
                    "url": "https://example.com/source",
                }
            ],
        }

        result = await manager.get_cached_news_link(
            target,
            action="source",
            index="1",
            refresh_source=False,
        )

        self.assertIn("标题：目标新闻", result)
        self.assertIn(f"来源：{YICAI_NAME}", result)
        self.assertIn("来源标识：yicai", result)

    async def test_get_cached_news_link_does_not_parse_full_sentence_query(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = mod.TaskManager(plugin)
        target = "aiocqhttp:GroupMessage:123"
        plugin.db.state[manager._news_snapshot_key(target)] = {
            "source_name": YICAI_NAME,
            "items": [
                {
                    "title": "目标新闻",
                    "url": "https://example.com/target",
                }
            ],
        }

        result = await manager.get_cached_news_link(
            target,
            query="第1条链接",
            refresh_source=False,
        )

        self.assertIn("新闻列表里没找到", result)
        self.assertNotIn("https://example.com/target", result)

    def test_independent_target_schedule_accepts_clock_time(self):
        mod = _load_tasks_module()
        manager = mod.TaskManager(_Plugin())

        parsed = manager._parse_targets_config(["123:8:30:问候"])

        self.assertEqual(parsed["123"]["cron"], "30 8 * * *")
        self.assertEqual(parsed["123"]["seq"], "问候")

    def test_broadcast_targets_can_be_limited_to_groups_or_users(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.receiver_conf = {
            "groups": ["111", "222"],
            "users": ["333"],
        }
        manager = mod.TaskManager(plugin)

        self.assertEqual(
            manager.get_broadcast_targets(target_scope="all"),
            [
                "aiocqhttp:GroupMessage:111",
                "aiocqhttp:GroupMessage:222",
                "aiocqhttp:FriendMessage:333",
            ],
        )
        self.assertEqual(
            manager.get_broadcast_targets(target_scope="groups"),
            [
                "aiocqhttp:GroupMessage:111",
                "aiocqhttp:GroupMessage:222",
            ],
        )
        self.assertEqual(
            manager.get_broadcast_targets(target_scope="users"),
            ["aiocqhttp:FriendMessage:333"],
        )

    async def test_execute_share_sends_plain_news_failure_message(self):
        mod = _load_tasks_module()
        event = _Event()

        await _manager(mod).execute_share(
            force_type=mod.ShareType.NEWS,
            news_source="yicai",
            specific_target="aiocqhttp:GroupMessage:123",
            event=event,
        )

        self.assertEqual(
            event.sent,
            [
                f"\u83b7\u53d6\u3010{YICAI_NAME}\u3011"
                "\u65b0\u95fb\u5931\u8d25\uff0c\u5206\u4eab\u5df2\u53d6\u6d88\u3002"
            ],
        )

    async def test_execute_share_continues_after_one_target_send_failure(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.receiver_conf = {"groups": ["111", "222"], "users": []}
        manager = mod.TaskManager(plugin)
        calls = []

        async def send(uid, *args, **kwargs):
            calls.append(uid)
            return len(calls) > 1

        manager.send = send

        await manager.execute_share(force_type=mod.ShareType.MOOD)

        self.assertEqual(
            calls,
            [
                "aiocqhttp:GroupMessage:111",
                "aiocqhttp:GroupMessage:222",
            ],
        )
        self.assertTrue(
            any(item[1].get("success") is False for item in plugin.db.history)
        )
        self.assertTrue(
            any(item[1].get("success") is True for item in plugin.db.history)
        )

    async def test_execute_qzone_share_keeps_qzone_news_failure_message(self):
        mod = _load_tasks_module()
        event = _Event()

        await _manager(mod).execute_qzone_share(
            force_type=mod.ShareType.NEWS,
            news_source="yicai",
            event=event,
        )

        self.assertEqual(
            event.sent,
            [
                f"\u83b7\u53d6\u3010{YICAI_NAME}\u3011"
                "\u65b0\u95fb\u5931\u8d25\uff0cQQ\u7a7a\u95f4"
                "\u5206\u4eab\u5df2\u53d6\u6d88\u3002"
            ],
        )

    async def test_execute_qzone_share_syncs_weixin_event_through_delivery_send(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.image_conf = {"enable_ai_image": True}
        plugin.qzone_conf = {"qzone_enable_image": True}
        published = []

        async def safe_publish_qzone(text, images, videos=None):
            published.append({"text": text, "images": images, "videos": list(videos or [])})

        plugin._safe_publish_qzone = safe_publish_qzone
        manager = mod.TaskManager(plugin)
        manager.get_curr_period = lambda: mod.TimePeriod.NIGHT
        sent = []

        async def send(uid, text, img_path=None, audio_path=None, video_url=None, event=None, image_optional=False):
            sent.append(
                {
                    "uid": uid,
                    "text": text,
                    "img_path": img_path,
                    "audio_path": audio_path,
                    "video_url": video_url,
                    "event": event,
                    "image_optional": image_optional,
                }
            )
            return True

        manager.send = send
        event = _Event(unified_msg_origin="weixin_oc:FriendMessage:o9test@im.wechat")

        ok = await manager.execute_qzone_share(force_type=mod.ShareType.MOOD, event=event)

        self.assertTrue(ok)
        self.assertEqual(event.sent, [])
        self.assertEqual(published, [{"text": "content", "images": [], "videos": []}])
        self.assertEqual(
            sent,
            [
                {
                    "uid": "weixin_oc:FriendMessage:o9test@im.wechat",
                    "text": "content",
                    "img_path": "generated.png",
                    "audio_path": None,
                    "video_url": None,
                    "event": event,
                    "image_optional": True,
                }
            ],
        )

    async def test_execute_qzone_share_sends_local_video_to_qzone_publish(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.image_conf = {"enable_ai_image": True, "enable_ai_video": True}
        plugin.qzone_conf = {
            "qzone_enable_image": True,
            "qzone_enable_video": True,
            "qzone_video_enabled_types": ["心情"],
        }
        published = []

        async def safe_publish_qzone(text, images, videos=None):
            published.append({"text": text, "images": list(images or []), "videos": list(videos or [])})

        plugin._safe_publish_qzone = safe_publish_qzone
        manager = mod.TaskManager(plugin)
        manager.get_curr_period = lambda: mod.TimePeriod.NIGHT

        async def prepare_qzone_image(image_ref):
            return b"image-bytes"

        manager._prepare_qzone_image = prepare_qzone_image

        ok = await manager.execute_qzone_share(force_type=mod.ShareType.MOOD)

        self.assertTrue(ok)
        self.assertEqual(
            published,
            [
                {
                    "text": "content",
                    "images": [],
                    "videos": [
                        {
                            "source": "generated.mp4",
                            "cover": "generated.png",
                            "title": "心情",
                            "description": "content",
                            "require_album_dynamic": True,
                        }
                    ],
                }
            ],
        )
        history_args, history_kwargs = plugin.db.history[0]
        self.assertEqual(history_kwargs["target_id"], sys.modules[KEYS_MODULE_NAME].QZONE_TARGET_ID)
        self.assertTrue(history_kwargs["success"])
        self.assertEqual(history_kwargs["media_type"], "video")
        self.assertEqual(history_kwargs["media_path"], "generated.mp4")

    async def test_execute_qzone_share_falls_back_to_image_when_video_publish_fails(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.image_conf = {"enable_ai_image": True, "enable_ai_video": True}
        plugin.qzone_conf = {
            "qzone_enable_image": True,
            "qzone_enable_video": True,
            "qzone_video_enabled_types": ["心情"],
        }
        published = []

        async def safe_publish_qzone(text, images, videos=None):
            payload = {"text": text, "images": list(images or []), "videos": list(videos or [])}
            published.append(payload)
            if payload["videos"]:
                raise RuntimeError("album video dynamic missing")

        plugin._safe_publish_qzone = safe_publish_qzone
        manager = mod.TaskManager(plugin)
        manager.get_curr_period = lambda: mod.TimePeriod.NIGHT

        async def prepare_qzone_image(image_ref):
            return b"image-bytes"

        manager._prepare_qzone_image = prepare_qzone_image

        ok = await manager.execute_qzone_share(force_type=mod.ShareType.MOOD)

        self.assertTrue(ok)
        self.assertEqual(
            published,
            [
                {
                    "text": "content",
                    "images": [],
                    "videos": [
                        {
                            "source": "generated.mp4",
                            "cover": "generated.png",
                            "title": "心情",
                            "description": "content",
                            "require_album_dynamic": True,
                        }
                    ],
                },
                {"text": "content", "images": [b"image-bytes"], "videos": []},
            ],
        )
        _history_args, history_kwargs = plugin.db.history[0]
        self.assertTrue(history_kwargs["success"])
        self.assertEqual(history_kwargs["media_type"], "image")
        self.assertEqual(history_kwargs["media_path"], "generated.png")

    async def test_execute_qzone_share_falls_back_to_text_when_video_and_image_publish_fail(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.image_conf = {"enable_ai_image": True, "enable_ai_video": True}
        plugin.qzone_conf = {
            "qzone_enable_image": True,
            "qzone_enable_video": True,
            "qzone_video_enabled_types": ["心情"],
        }
        published = []

        async def safe_publish_qzone(text, images, videos=None):
            payload = {"text": text, "images": list(images or []), "videos": list(videos or [])}
            published.append(payload)
            if payload["videos"]:
                raise RuntimeError("album video dynamic missing")
            if payload["images"]:
                raise RuntimeError("image upload failed")

        plugin._safe_publish_qzone = safe_publish_qzone
        manager = mod.TaskManager(plugin)
        manager.get_curr_period = lambda: mod.TimePeriod.NIGHT

        async def prepare_qzone_image(image_ref):
            return b"image-bytes"

        manager._prepare_qzone_image = prepare_qzone_image

        ok = await manager.execute_qzone_share(force_type=mod.ShareType.MOOD)

        self.assertTrue(ok)
        self.assertEqual(
            published,
            [
                {
                    "text": "content",
                    "images": [],
                    "videos": [
                        {
                            "source": "generated.mp4",
                            "cover": "generated.png",
                            "title": "心情",
                            "description": "content",
                            "require_album_dynamic": True,
                        }
                    ],
                },
                {"text": "content", "images": [b"image-bytes"], "videos": []},
                {"text": "content", "images": [], "videos": []},
            ],
        )
        _history_args, history_kwargs = plugin.db.history[0]
        self.assertTrue(history_kwargs["success"])
        self.assertNotIn("media_type", history_kwargs)
        self.assertNotIn("media_path", history_kwargs)

    async def test_weixin_image_send_retries_with_smaller_copy(self):
        mod = _load_tasks_module()
        manager = mod.TaskManager(_Plugin())
        calls = []

        async def send_image(uid, img_path, event=None, media_result=None):
            calls.append(img_path)
            if len(calls) == 1:
                raise RuntimeError("upload media to cdn failed: 500")

        async def prepare_retry(img_path):
            return "small.jpg"

        manager._send_image_chain = send_image
        manager._prepare_weixin_retry_image = prepare_retry

        await manager._send_image_chain_with_retry(
            "weixin_oc:FriendMessage:o9test@im.wechat",
            "large.jpg",
        )

        self.assertEqual(calls, ["large.jpg", "small.jpg"])

    async def test_optional_weixin_image_failure_keeps_text_success(self):
        mod = _load_tasks_module()
        manager = mod.TaskManager(_Plugin())
        sent = []

        async def send_chain(uid, chain, event=None):
            sent.append(list(chain.items))
            if chain.items and isinstance(chain.items[0], tuple) and chain.items[0][0] == "file_image":
                raise RuntimeError("upload media to cdn failed: 500")

        async def prepare_image(uid, img_path):
            return "prepared.jpg"

        async def prepare_retry(img_path):
            return "retry.jpg"

        manager._send_message_chain = send_chain
        manager._prepare_image_for_target = prepare_image
        manager._prepare_weixin_retry_image = prepare_retry
        manager.random_sleep = lambda: asyncio.sleep(0)

        ok = await manager.send(
            "weixin_oc:FriendMessage:o9test@im.wechat",
            "content",
            "large.jpg",
            event=_Event(),
            image_optional=True,
        )

        self.assertTrue(ok)
        self.assertEqual(
            sent,
            [
                ["content"],
                [("file_image", "retry.jpg")],
            ],
        )

    async def test_send_reports_downloaded_remote_image_path(self):
        mod = _load_tasks_module()
        manager = mod.TaskManager(_Plugin())
        sent = []

        async def download_image(url, filename=None):
            self.assertEqual(url, "https://example.com/news.png")
            self.assertEqual(filename, "weibo_8005ce727817.png")
            return "Temp/weibo_8005ce727817.png"

        async def prepare_image(target, image_path):
            return image_path

        async def send_chain(uid, chain, event=None):
            sent.append(list(chain.items))

        manager._build_news_image_filename = lambda url: "weibo_8005ce727817.png"
        manager._download_image_to_local = download_image
        manager._prepare_image_for_target = prepare_image
        manager._send_message_chain = send_chain
        manager.random_sleep = lambda: asyncio.sleep(0)

        media_result = {}
        ok = await manager.send(
            "aiocqhttp:GroupMessage:123",
            "content",
            "https://example.com/news.png",
            media_result=media_result,
        )

        self.assertTrue(ok)
        self.assertEqual(
            media_result,
            {
                "text_sent": True,
                "audio_sent": False,
                "image_sent": True,
                "video_sent": False,
                "downloaded_image_path": "Temp/weibo_8005ce727817.png",
                "image_path": "Temp/weibo_8005ce727817.png",
            },
        )
        self.assertEqual(
            sent,
            [
                ["content"],
                [("file_image", "Temp/weibo_8005ce727817.png")],
            ],
        )

    async def test_daily_life_image_returns_path_without_sending(self):
        mod = _load_tasks_module()
        image_mod = importlib.import_module(f"{CORE_PACKAGE_NAME}.image")
        calls = []

        class DailyLifeImage:
            async def generate_image(self, prompt):
                calls.append(prompt)
                return types.SimpleNamespace(path="daily-life-image.jpg")

        class Context:
            def get_all_stars(self):
                runtime = types.SimpleNamespace(
                    media=types.SimpleNamespace(image=DailyLifeImage())
                )
                plugin = types.SimpleNamespace(runtime=runtime)
                return [
                    types.SimpleNamespace(
                        name="astrbot_plugin_daily_life",
                        root_dir_name="astrbot_plugin_daily_life",
                        display_name="daily_life",
                        star_cls=plugin,
                    )
                ]

        service = image_mod.ImageService(
            Context(),
            {
                "image_conf": {
                    "enable_ai_image": True,
                },
                "llm_conf": {},
            },
            lambda *args, **kwargs: asyncio.sleep(0, result=""),
        )
        service._check_involves_self = lambda *args, **kwargs: asyncio.sleep(0, result=False)
        service._agent_extract_visuals = lambda *args, **kwargs: asyncio.sleep(
            0,
            result={"environment": "卧室", "subject": "台灯"},
        )
        service._assemble_final_prompt = lambda *args, **kwargs: asyncio.sleep(0, result="图片提示词")
        event = _Event()

        result = await service.generate_image(
            "content",
            mod.ShareType.MOOD,
            "life",
            target_umo="aiocqhttp:FriendMessage:89761500",
            event=event,
        )

        self.assertEqual(result, "daily-life-image.jpg")
        self.assertEqual(calls, ["图片提示词"])
        self.assertEqual(event.sent, [])

    async def test_execute_share_generates_visual_media_before_audio(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.receiver_conf = {"users": ["aiocqhttp:FriendMessage:89761500"], "groups": []}
        plugin.image_conf = {
            "enable_ai_image": True,
            "enable_ai_video": False,
            "image_enabled_types": ["心情"],
        }
        plugin.tts_conf = {"enable_tts": True, "tts_enabled_types": ["心情"]}
        order = []

        async def text_to_speech(*args, **kwargs):
            order.append("audio")
            return "audio.wav"

        async def generate_image(*args, **kwargs):
            order.append("image")
            return "image.png"

        plugin.ctx_service.text_to_speech = text_to_speech
        plugin.image_service.generate_image = generate_image
        manager = mod.TaskManager(plugin)
        manager.get_curr_period = lambda: mod.TimePeriod.NIGHT
        manager.random_sleep = lambda: asyncio.sleep(0)

        await manager.execute_share(
            force_type=mod.ShareType.MOOD,
            specific_target="aiocqhttp:FriendMessage:89761500",
        )

        self.assertEqual(order, ["image", "audio"])

    async def test_execute_share_sends_audio_then_video_without_image_when_video_exists(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.receiver_conf = {"users": ["aiocqhttp:FriendMessage:89761500"], "groups": []}
        plugin.image_conf = {
            "enable_ai_image": True,
            "enable_ai_video": True,
            "image_enabled_types": ["心情"],
            "video_enabled_types": ["心情"],
        }
        plugin.tts_conf = {"enable_tts": True, "tts_enabled_types": ["心情"]}
        order = []
        sent = []

        async def generate_image(*args, **kwargs):
            order.append("image")
            return "image.png"

        async def generate_video_from_image(*args, **kwargs):
            order.append("video")
            return "video.mp4"

        async def text_to_speech(*args, **kwargs):
            order.append("audio")
            return "audio.wav"

        async def send_chain(uid, chain, event=None):
            sent.append(list(chain.items))

        plugin.image_service.generate_image = generate_image
        plugin.image_service.generate_video_from_image = generate_video_from_image
        plugin.ctx_service.text_to_speech = text_to_speech
        manager = mod.TaskManager(plugin)
        manager.get_curr_period = lambda: mod.TimePeriod.NIGHT
        manager._prepare_image_for_target = lambda _uid, path: asyncio.sleep(0, result=path)
        manager.random_sleep = lambda: asyncio.sleep(0)
        manager._send_message_chain = send_chain

        await manager.execute_share(
            force_type=mod.ShareType.MOOD,
            specific_target="aiocqhttp:FriendMessage:89761500",
            event=_Event(unified_msg_origin="aiocqhttp:FriendMessage:89761500"),
        )

        self.assertEqual(order, ["image", "video", "audio"])
        self.assertEqual(len(sent), 3)
        self.assertEqual(sent[0], ["content"])
        self.assertEqual(getattr(sent[1][0], "file", None), "audio.wav")
        self.assertEqual(getattr(sent[2][0], "source", None), ("file_video", "video.mp4"))
        self.assertFalse(any(("file_image", "image.png") in chain for chain in sent))

    async def test_async_daily_share_resolves_auto_before_requested_video(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.image_conf = {"enable_ai_image": True, "enable_ai_video": False}
        manager = mod.TaskManager(plugin)
        manager.get_curr_period = lambda: mod.TimePeriod.NIGHT
        sent = []

        async def send(target, content, image_path=None, audio_path=None, video_url=None, event=None, media_result=None):
            sent.append(
                {
                    "target": target,
                    "content": content,
                    "image_path": image_path,
                    "audio_path": audio_path,
                    "video_url": video_url,
                }
            )
            if media_result is not None:
                media_result["image_sent"] = bool(image_path)
                if image_path:
                    media_result["image_path"] = image_path
            return True

        async def prepare_image_for_target(target, image_path):
            return image_path

        manager.send = send
        manager._prepare_image_for_target = prepare_image_for_target
        event = _Event()

        await manager.async_daily_share_task(
            event,
            share_type="\u81ea\u52a8",
            source=None,
            get_image=True,
            need_image=False,
            need_video=True,
            need_voice=False,
            to_qzone=False,
        )

        self.assertEqual(event.sent, [])
        self.assertEqual(plugin.content_service.calls[0][0][0], mod.ShareType.RECOMMENDATION)
        self.assertEqual(plugin.image_service.generated[0]["share_type"], mod.ShareType.RECOMMENDATION)
        self.assertEqual(sent[0]["image_path"], "generated.png")
        self.assertEqual(len(plugin.db.history), 1)
        history_args, history_kwargs = plugin.db.history[0]
        self.assertEqual(history_kwargs["target_id"], event.unified_msg_origin)
        self.assertEqual(history_kwargs["share_type"], mod.ShareType.RECOMMENDATION.value)
        self.assertTrue(history_kwargs["success"])
        self.assertEqual(history_kwargs["media_type"], "image")
        self.assertEqual(history_kwargs["media_path"], "generated.png")

    async def test_async_daily_share_history_uses_downloaded_news_image_path(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.image_conf = {"attach_hot_news_image": True}

        class NewsService(_NewsService):
            async def get_hot_news(self, source=None, limit=None, allow_fallback=True):
                return (["news"], "weibo")

            def get_hot_news_image_url(self, source):
                return "https://example.com/news.png", None

        plugin.news_service = NewsService()
        manager = mod.TaskManager(plugin)
        manager.get_curr_period = lambda: mod.TimePeriod.NIGHT

        async def send(target, content, image_path=None, audio_path=None, video_url=None, event=None, media_result=None):
            self.assertEqual(image_path, "https://example.com/news.png")
            if media_result is not None:
                media_result["image_sent"] = True
                media_result["downloaded_image_path"] = "Temp/weibo_8005ce727817.png"
                media_result["image_path"] = "Temp/weibo_8005ce727817.png"
            return True

        manager.send = send
        event = _Event()

        await manager.async_daily_share_task(
            event,
            share_type="\u65b0\u95fb",
            source="weibo",
            get_image=True,
            need_image=False,
            need_video=False,
            need_voice=True,
            to_qzone=False,
        )

        self.assertEqual(len(plugin.db.history), 1)
        _history_args, history_kwargs = plugin.db.history[0]
        self.assertTrue(history_kwargs["success"])
        self.assertEqual(history_kwargs["media_type"], "image")
        self.assertEqual(history_kwargs["media_path"], "Temp/weibo_8005ce727817.png")
        self.assertNotIn("media_url", history_kwargs)

    async def test_async_daily_share_marks_llm_success_with_emoji(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = mod.TaskManager(plugin)
        manager.get_curr_period = lambda: mod.TimePeriod.NIGHT
        manager.send = lambda *args, **kwargs: asyncio.sleep(0, result=True)
        bot = _EmojiBot()
        event = _Event(bot=bot, message_id=321)

        await manager.async_daily_share_task(
            event,
            share_type="\u5fc3\u60c5",
            source=None,
            get_image=True,
            need_image=False,
            need_video=False,
            need_voice=False,
            to_qzone=False,
        )

        self.assertEqual([call["emoji_id"] for call in bot.calls], [125, 79])

    async def test_async_daily_share_marks_llm_failure_with_emoji(self):
        mod = _load_tasks_module()
        bot = _EmojiBot()
        event = _Event(bot=bot, message_id=322)

        await _manager(mod).async_daily_share_task(
            event,
            share_type="\u4e0d\u5b58\u5728",
            source=None,
            get_image=True,
            need_image=False,
            need_video=False,
            need_voice=False,
            to_qzone=False,
        )

        self.assertEqual([call["emoji_id"] for call in bot.calls], [125, 106])
        self.assertEqual(
            event.sent,
            [
                "\u4e0d\u652f\u6301\u7684\u5206\u4eab\u7c7b\u578b\uff1a"
                "\u4e0d\u5b58\u5728\u3002\u652f\u6301\uff1a\u81ea\u52a8\u3001"
                "\u95ee\u5019\u3001\u65b0\u95fb\u3001\u5fc3\u60c5\u3001\u77e5\u8bc6\u3001"
                "\u63a8\u8350\u300160s \u65b0\u95fb\u3001AI \u8d44\u8baf\u3002"
            ],
        )

    async def test_briefing_wrapper_schedules_random_delay(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.extra_shares_conf = {"briefing_schedule_mode": "cron", "briefing_cron_random_delay": 5}
        manager = mod.TaskManager(plugin)
        called = False

        async def execute_briefing_share(*args, **kwargs):
            nonlocal called
            called = True

        manager.execute_briefing_share = execute_briefing_share
        old_randint = mod.random.randint
        mod.random.randint = lambda start, end: 120
        try:
            await manager._task_wrapper_briefing()
        finally:
            mod.random.randint = old_randint

        self.assertFalse(called)
        self.assertEqual(len(plugin.scheduler.jobs), 1)
        job = plugin.scheduler.jobs[0]
        self.assertEqual(job["trigger"], "date")
        self.assertEqual(job["kwargs"]["id"], "delayed_briefing_share")
        self.assertIn("run_date", job["kwargs"])
        self.assertGreater(
            plugin.db.state["briefing"]["pending_delay_job"]["target_time"],
            datetime.now().timestamp(),
        )

    async def test_briefing_random_period_ignores_random_delay(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.extra_shares_conf = {"briefing_schedule_mode": "random_period", "briefing_cron_random_delay": 5}
        manager = mod.TaskManager(plugin)
        called = False

        async def execute_briefing_share(*args, **kwargs):
            nonlocal called
            called = True

        manager.execute_briefing_share = execute_briefing_share
        old_randint = mod.random.randint
        mod.random.randint = lambda start, end: 120
        try:
            await manager._task_wrapper_briefing()
        finally:
            mod.random.randint = old_randint

        await asyncio.wait_for(asyncio.gather(*plugin._bg_tasks), timeout=1)
        self.assertTrue(called)
        self.assertEqual(plugin.scheduler.jobs, [])
        self.assertIsNone(plugin.db.state["briefing"]["pending_delay_job"])

    async def test_scheduled_qzone_wrapper_returns_before_background_task_finishes(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = mod.TaskManager(plugin)
        started = asyncio.Event()
        release = asyncio.Event()

        async def execute_qzone_share(*args, **kwargs):
            started.set()
            await release.wait()

        manager.execute_qzone_share = execute_qzone_share

        await manager._execute_delayed_qzone_task()

        await asyncio.wait_for(started.wait(), timeout=1)
        self.assertEqual(plugin.db.state["qzone"]["pending_delay_job"], None)
        self.assertTrue(plugin._bg_tasks)
        self.assertTrue(plugin._lock.locked())

        release.set()
        await asyncio.wait_for(asyncio.gather(*plugin._bg_tasks), timeout=1)
        self.assertFalse(plugin._lock.locked())

    async def test_custom_target_cron_does_not_add_global_random_delay(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.basic_conf = {"cron_random_delay": 30}
        plugin.receiver_conf = {"groups": ["123:08:30:心情"], "users": []}
        manager = mod.TaskManager(plugin)
        called = asyncio.Event()

        async def execute_share(*args, **kwargs):
            called.set()

        manager.execute_share = execute_share
        manager.setup_custom_target_crons()

        custom_job = next(job for job in plugin.scheduler.jobs if job["kwargs"].get("id") == "custom_share_123")
        await custom_job["func"]()
        await asyncio.wait_for(called.wait(), timeout=1)

        job_ids = {job["kwargs"].get("id") for job in plugin.scheduler.jobs}
        self.assertNotIn("delayed_custom_share_123", job_ids)
        self.assertIsNone(plugin.db.state["target_123"]["pending_delay_job"])

    async def test_llm_smart_schedule_registers_valid_today_jobs(self):
        mod = _load_tasks_module()
        smart_mod = sys.modules[f"{TASKS_MODULE_NAME}.scheduler.smart"]
        plugin = _Plugin()
        plugin.basic_conf = {
            "share_type": "自动",
            "smart_schedule_max_count": 2,
            "smart_schedule_quiet_hours": ["23:30-07:30"],
            "smart_schedule_prompt": "早上轻一点",
        }
        manager = mod.TaskManager(plugin)

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 6, 14, 8, 0, 0)

        captured_llm = {}

        async def llm(**kwargs):
            captured_llm.update(kwargs)
            return (
                '[{"run_at":"2026-06-14 08:30",'
                '"share_type":"问候","reason":"早上适合轻量问候"}]'
            )

        old_datetime = smart_mod.datetime
        old_randrange = smart_mod.random.randrange
        plugin._call_llm_wrapper = llm
        smart_mod.datetime = FixedDateTime
        smart_mod.random.randrange = lambda start, stop=None: 23
        try:
            await manager._schedule_daily_smart_jobs()
        finally:
            smart_mod.datetime = old_datetime
            smart_mod.random.randrange = old_randrange

        self.assertEqual(len(plugin.scheduler.jobs), 1)
        job = plugin.scheduler.jobs[0]
        self.assertEqual(job["trigger"], "date")
        self.assertEqual(job["kwargs"]["id"], "smart_share_0")
        self.assertEqual(job["kwargs"]["run_date"].strftime("%Y-%m-%d %H:%M"), "2026-06-14 08:30")
        self.assertEqual(job["kwargs"]["run_date"].strftime("%S"), "23")
        self.assertNotIn("08:30", job["kwargs"]["name"])
        self.assertIn("问候", job["kwargs"]["name"])
        schedule = plugin.db.state["global"]["smart_schedule"]
        self.assertEqual(schedule["source"], "llm")
        self.assertEqual(schedule["jobs"][0]["share_type"], "问候")
        self.assertTrue(schedule["jobs"][0]["run_at"].endswith(":23"))
        self.assertIn("YYYY-MM-DD HH:MM:SS", captured_llm["prompt"])
        self.assertIn("05-55", captured_llm["prompt"])
        self.assertIn("勿扰时间", captured_llm["prompt"])
        self.assertIn("避开勿扰时间", captured_llm["system_prompt"])

    async def test_llm_smart_schedule_records_empty_plan_without_fallback(self):
        mod = _load_tasks_module()
        smart_mod = sys.modules[f"{TASKS_MODULE_NAME}.scheduler.smart"]
        plugin = _Plugin()
        plugin.qzone_conf = {
            "qzone_share_type": "心情",
            "qzone_fixed_times": ["20:00"],
            "qzone_smart_schedule_max_count": 1,
            "qzone_smart_schedule_quiet_hours": ["23:30-07:30"],
        }
        manager = mod.TaskManager(plugin)

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 6, 14, 8, 0, 0)

        async def llm(**kwargs):
            return "[]"

        old_datetime = smart_mod.datetime
        plugin._call_llm_wrapper = llm
        smart_mod.datetime = FixedDateTime
        try:
            await manager._schedule_daily_qzone_smart_jobs()
        finally:
            smart_mod.datetime = old_datetime

        self.assertEqual(len(plugin.scheduler.jobs), 0)
        schedule = plugin.db.state["qzone"]["smart_schedule"]
        self.assertEqual(schedule["source"], "none")
        self.assertEqual(schedule["jobs"], [])
        self.assertIn("未返回可用计划", schedule["last_error"])

    async def test_recover_pending_briefing_delay_job(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        target_time = datetime.now() + timedelta(minutes=3)
        plugin.db.state["briefing"] = {
            "pending_delay_job": {"target_time": target_time.timestamp()}
        }
        manager = mod.TaskManager(plugin)

        await manager._recover_pending_jobs()

        self.assertEqual(len(plugin.scheduler.jobs), 1)
        job = plugin.scheduler.jobs[0]
        self.assertEqual(job["trigger"], "date")
        self.assertEqual(job["kwargs"]["id"], "resume_briefing_share")
        self.assertEqual(job["kwargs"]["run_date"].replace(microsecond=0), target_time.replace(microsecond=0))


if __name__ == "__main__":
    unittest.main()


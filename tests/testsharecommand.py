import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "daily_share_share_command_testpkg"
CORE_PACKAGE_NAME = f"{PACKAGE_NAME}.core"
HOST_PACKAGE_NAME = f"{CORE_PACKAGE_NAME}.host"
SHARE_MODULE_NAME = f"{HOST_PACKAGE_NAME}.share"
ARGS_MODULE_NAME = f"{CORE_PACKAGE_NAME}.args"
CONFIG_MODULE_NAME = f"{CORE_PACKAGE_NAME}.config"
CONSTANTS_MODULE_NAME = f"{CORE_PACKAGE_NAME}.constants"


class _Logger:
    def debug(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None


def _install_stub_module(name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _clear_modules():
    for name in list(sys.modules):
        if name.startswith(PACKAGE_NAME) or name in {"astrbot", "astrbot.api", "astrbot.api.event"}:
            sys.modules.pop(name, None)


def _load_share_module():
    _clear_modules()
    for name, path in [
        (PACKAGE_NAME, ROOT),
        (CORE_PACKAGE_NAME, ROOT / "core"),
        (HOST_PACKAGE_NAME, ROOT / "core" / "host"),
    ]:
        module = _install_stub_module(name)
        module.__path__ = [str(path)]

    _install_stub_module("astrbot")
    _install_stub_module("astrbot.api", logger=_Logger())
    _install_stub_module(
        "astrbot.api.event",
        AstrMessageEvent=type("AstrMessageEvent", (), {}),
        MessageChain=type("MessageChain", (), {}),
    )

    for module_name, path in [
        (ARGS_MODULE_NAME, ROOT / "core" / "args.py"),
        (CONFIG_MODULE_NAME, ROOT / "core" / "config.py"),
        (CONSTANTS_MODULE_NAME, ROOT / "core" / "constants.py"),
        (SHARE_MODULE_NAME, ROOT / "core" / "host" / "share.py"),
    ]:
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        assert spec and spec.loader
        spec.loader.exec_module(module)
    return sys.modules[SHARE_MODULE_NAME]


class _Event:
    message_str = "/分享 心情 空间"
    unified_msg_origin = "aiocqhttp:GroupMessage:89761500"

    def __init__(self):
        self.sent = []

    def plain_result(self, text):
        return text

    def image_result(self, image):
        return image

    async def send(self, message):
        self.sent.append(message)


class _Db:
    def __init__(self):
        self.history = []

    async def add_sent_history(self, *args, **kwargs):
        self.history.append((args, kwargs))


class _NewsService:
    def __init__(self):
        self.ai_started = asyncio.Event()
        self.ai_release = asyncio.Event()

    def select_news_source(self):
        return "zhihu"

    def get_hot_news_image_url(self, source):
        return "https://example.com/news.png", "知乎"

    async def get_hot_news(self, *args, **kwargs):
        return ([{"title": "测试新闻"}], "zhihu")

    async def get_ai_news_json(self):
        self.ai_started.set()
        await self.ai_release.wait()
        return {"news": [{"title": "AI"}]}

    def get_ai_news_image_url(self):
        return "https://example.com/ai.png"


class _TaskManager:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = []
        self.snapshots = []

    async def execute_qzone_share(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        self.started.set()
        await self.release.wait()
        return True

    def get_news_snapshot_limit(self):
        return 5

    async def cache_news_snapshot(self, *args, **kwargs):
        self.snapshots.append((args, kwargs))

    def _build_news_image_filename(self, url, source_name):
        return "news.png"

    async def _download_image_to_local(self, url, filename):
        self.started.set()
        await self.release.wait()
        return "C:/Temp/news.png"

    def _image_history_kwargs(self, path):
        return {"media_path": path}


class ShareCommandBackgroundTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        share_module = _load_share_module()

        class Host(share_module.PluginShareMixin):
            def __init__(self):
                self.task_manager = _TaskManager()
                self.news_service = _NewsService()
                self.command_handler = types.SimpleNamespace()
                self.db = _Db()
                self._locks = {}
                self._tasks = []

            def _remember_event_adapter(self, event):
                return None

            def _is_admin_event(self, event):
                return True

            def _is_configured_receiver_event(self, event):
                return True

            def _plain_permission_denied(self, event):
                return "permission denied"

            def _get_share_lock(self, target_uid=None, *, global_scope=False):
                key = "global" if global_scope else str(target_uid or "")
                self._locks.setdefault(key, asyncio.Lock())
                return self._locks[key]

            def _is_share_busy(self, target_uid=None, *, global_scope=False):
                return self._get_share_lock(target_uid, global_scope=global_scope).locked()

            def _release_idle_share_lock(self, target_uid=None):
                return None

            def _track_task(self, coro):
                task = asyncio.create_task(coro)
                self._tasks.append(task)
                return task

        self.host = Host()

    async def asyncTearDown(self):
        self.host.task_manager.release.set()
        self.host.news_service.ai_release.set()
        for task in list(self.host._tasks):
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_qzone_share_command_returns_before_background_task_finishes(self):
        event = _Event()

        results = [item async for item in self.host._handle_share_main_impl(event)]

        self.assertEqual(results, ["正在向QQ空间生成并分享心情 ..."])
        await asyncio.wait_for(self.host.task_manager.started.wait(), timeout=1)
        self.assertEqual(len(self.host._tasks), 1)
        self.assertFalse(self.host._tasks[0].done())
        self.assertTrue(self.host._is_share_busy(global_scope=True))

        self.host.task_manager.release.set()
        await asyncio.wait_for(self.host._tasks[0], timeout=1)
        self.assertFalse(self.host._is_share_busy(global_scope=True))

    async def test_news_image_command_returns_before_background_task_finishes(self):
        event = _Event()
        event.message_str = "/分享 新闻 图片"

        results = [item async for item in self.host._handle_share_main_impl(event)]

        self.assertEqual(results, ["正在向当前会话分享知乎热搜图片..."])
        await asyncio.wait_for(self.host.task_manager.started.wait(), timeout=1)
        self.assertEqual(len(self.host._tasks), 1)
        self.assertFalse(self.host._tasks[0].done())
        self.assertTrue(self.host._is_share_busy(event.unified_msg_origin))

        self.host.task_manager.release.set()
        await asyncio.wait_for(self.host._tasks[0], timeout=1)
        self.assertIn("C:/Temp/news.png", event.sent)
        self.assertFalse(self.host._is_share_busy(event.unified_msg_origin))

    async def test_ai_image_command_returns_before_news_api_finishes(self):
        event = _Event()
        event.message_str = "/分享 ai"

        results = [item async for item in self.host._handle_share_main_impl(event)]

        self.assertEqual(results, ["正在向当前会话分享AI资讯快报..."])
        await asyncio.wait_for(self.host.news_service.ai_started.wait(), timeout=1)
        self.assertEqual(len(self.host._tasks), 1)
        self.assertFalse(self.host._tasks[0].done())
        self.assertTrue(self.host._is_share_busy(event.unified_msg_origin))

        self.host.news_service.ai_release.set()
        self.host.task_manager.release.set()
        await asyncio.wait_for(self.host._tasks[0], timeout=1)
        self.assertIn("C:/Temp/news.png", event.sent)
        self.assertFalse(self.host._is_share_busy(event.unified_msg_origin))


if __name__ == "__main__":
    unittest.main()

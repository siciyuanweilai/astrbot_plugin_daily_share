import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "daily_share_share_command_testpkg"
SUPPORT_MODULE_NAME = f"{PACKAGE_NAME}.core.support"


class _Logger:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


def _load_support_runtime():
    for name in list(sys.modules):
        if name.startswith(PACKAGE_NAME):
            sys.modules.pop(name, None)

    for name, path in (
        (PACKAGE_NAME, ROOT),
        (f"{PACKAGE_NAME}.core", ROOT / "core"),
        (f"{PACKAGE_NAME}.core.host", ROOT / "core" / "host"),
        (f"{PACKAGE_NAME}.core.tasks", ROOT / "core" / "tasks"),
        (
            f"{PACKAGE_NAME}.core.tasks.interact",
            ROOT / "core" / "tasks" / "interact",
        ),
        (f"{PACKAGE_NAME}.core.database", ROOT / "core" / "database"),
    ):
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module

    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    event = types.ModuleType("astrbot.api.event")
    api.logger = _Logger()
    api.event = event
    event.AstrMessageEvent = type("AstrMessageEvent", (), {})
    event.MessageChain = type("MessageChain", (), {})
    astrbot.api = api
    sys.modules["astrbot"] = astrbot
    sys.modules["astrbot.api"] = api
    sys.modules["astrbot.api.event"] = event

    spec = importlib.util.spec_from_file_location(
        SUPPORT_MODULE_NAME,
        ROOT / "core" / "support.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[SUPPORT_MODULE_NAME] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.SupportRuntime


class _Event:
    message_str = "/分享 心情 空间"
    unified_msg_origin = "aiocqhttp:GroupMessage:100000002"

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
        self.snapshot_store = self
        self.qzone_share = self
        self.delivery_assets = self
        self.executor_helpers = self

    async def execute_qzone_share(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        self.started.set()
        await self.release.wait()
        return True

    def get_news_snapshot_limit(self):
        return 5

    async def commit_sent_news_snapshot(self, *args, **kwargs):
        self.snapshots.append((args, kwargs))

    async def record_share_history(self, **kwargs):
        snapshot_data = kwargs.get("news_snapshot_data")
        if snapshot_data:
            self.snapshots.append(
                (
                    (kwargs.get("target_id"),),
                    {
                        "image_url": kwargs.get("news_image_url"),
                        "snapshot_data": snapshot_data,
                    },
                )
            )

    def build_news_image_filename(self, url, source_name):
        return "news.png"

    async def download_image_to_local(self, url, filename):
        self.started.set()
        await self.release.wait()
        return "C:/Temp/news.png"

    def image_history_kwargs(self, path):
        return {"media_path": path}


class ShareCommandBackgroundTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        SupportRuntime = _load_support_runtime()

        class Host(SupportRuntime):
            def __init__(self):
                plugin = types.SimpleNamespace(
                    task_manager=_TaskManager(),
                    news_service=_NewsService(),
                    command_handler=types.SimpleNamespace(),
                    db=_Db(),
                    config={},
                    receiver_conf={},
                    basic_conf={},
                    extra_shares_conf=[],
                    qzone_conf={},
                    contact_aliases={},
                    context=None,
                    ctx_service=None,
                    qzone_service=None,
                    _is_terminated=False,
                    _cached_adapter_id=None,
                    _cached_qq_adapter_id=None,
                    _cached_weixin_adapter_id=None,
                )
                super().__init__(plugin)
                self._locks = {}
                self._tasks = []
                self.permissions._remember_event_adapter = lambda event: None
                self.permissions._is_admin_event = lambda event: True
                self.permissions._is_configured_receiver_event = lambda event: True
                self.permissions._plain_permission_denied = lambda event: (
                    "permission denied"
                )

            def get_share_lock(self, target_uid=None, *, global_scope=False):
                key = "global" if global_scope else str(target_uid or "")
                self._locks.setdefault(key, asyncio.Lock())
                return self._locks[key]

            def is_share_busy(self, target_uid=None, *, global_scope=False):
                return self.get_share_lock(
                    target_uid, global_scope=global_scope
                ).locked()

            def release_idle_share_lock(self, target_uid=None):
                return None

            def track_task(self, coro):
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

        results = [
            item async for item in self.host.main_route.handle_share_command(event)
        ]

        self.assertEqual(results, ["正在向QQ空间生成并分享心情 ..."])
        await asyncio.wait_for(self.host.task_manager.started.wait(), timeout=1)
        self.assertEqual(len(self.host._tasks), 1)
        self.assertFalse(self.host._tasks[0].done())
        self.assertTrue(self.host.is_share_busy(global_scope=True))

        self.host.task_manager.release.set()
        await asyncio.wait_for(self.host._tasks[0], timeout=1)
        self.assertFalse(self.host.is_share_busy(global_scope=True))

    async def test_news_image_command_returns_before_background_task_finishes(self):
        event = _Event()
        event.message_str = "/分享 新闻 图片"

        results = [
            item async for item in self.host.main_route.handle_share_command(event)
        ]

        self.assertEqual(results, ["正在向当前会话分享知乎热搜图片..."])
        await asyncio.wait_for(self.host.task_manager.started.wait(), timeout=1)
        self.assertEqual(len(self.host._tasks), 1)
        self.assertFalse(self.host._tasks[0].done())
        self.assertTrue(self.host.is_share_busy(event.unified_msg_origin))

        self.host.task_manager.release.set()
        await asyncio.wait_for(self.host._tasks[0], timeout=1)
        self.assertIn("C:/Temp/news.png", event.sent)
        self.assertEqual(len(self.host.task_manager.snapshots), 1)
        snapshot_args, snapshot_kwargs = self.host.task_manager.snapshots[0]
        self.assertEqual(snapshot_args, (event.unified_msg_origin,))
        self.assertEqual(snapshot_kwargs["image_url"], "C:/Temp/news.png")
        self.assertEqual(snapshot_kwargs["snapshot_data"]["source"], "zhihu")
        self.assertFalse(self.host.is_share_busy(event.unified_msg_origin))

    async def test_failed_news_image_download_does_not_commit_snapshot(self):
        event = _Event()

        async def fail_download(url, filename):
            return None

        self.host.task_manager.download_image_to_local = fail_download
        await self.host.news_outbox._run_news_image_share(
            event,
            news_src="zhihu",
            current_uid=event.unified_msg_origin,
            is_qzone_target=False,
        )

        self.assertEqual(self.host.task_manager.snapshots, [])

    async def test_failed_news_image_send_does_not_commit_snapshot(self):
        event = _Event()

        async def fail_send(_message):
            raise RuntimeError("send failed")

        event.send = fail_send
        self.host.task_manager.release.set()
        await self.host.news_outbox._run_news_image_share(
            event,
            news_src="zhihu",
            current_uid=event.unified_msg_origin,
            is_qzone_target=False,
        )

        self.assertEqual(self.host.task_manager.snapshots, [])
        self.assertEqual(len(self.host.db.history), 1)
        self.assertFalse(self.host.db.history[0][0][3])

    async def test_failed_news_json_does_not_send_image_or_commit_snapshot(self):
        event = _Event()

        async def fail_news(*args, **kwargs):
            return None

        self.host.news_service.get_hot_news = fail_news
        await self.host.news_outbox._run_news_image_share(
            event,
            news_src="zhihu",
            current_uid=event.unified_msg_origin,
            is_qzone_target=False,
        )

        self.assertEqual(event.sent, ["获取新闻列表失败，长图分享已取消。"])
        self.assertEqual(self.host.task_manager.snapshots, [])

    async def test_ai_image_command_returns_before_news_api_finishes(self):
        event = _Event()
        event.message_str = "/分享 ai"

        results = [
            item async for item in self.host.main_route.handle_share_command(event)
        ]

        self.assertEqual(results, ["正在向当前会话分享AI资讯快报..."])
        await asyncio.wait_for(self.host.news_service.ai_started.wait(), timeout=1)
        self.assertEqual(len(self.host._tasks), 1)
        self.assertFalse(self.host._tasks[0].done())
        self.assertTrue(self.host.is_share_busy(event.unified_msg_origin))

        self.host.news_service.ai_release.set()
        self.host.task_manager.release.set()
        await asyncio.wait_for(self.host._tasks[0], timeout=1)
        self.assertIn("C:/Temp/news.png", event.sent)
        self.assertFalse(self.host.is_share_busy(event.unified_msg_origin))


if __name__ == "__main__":
    unittest.main()

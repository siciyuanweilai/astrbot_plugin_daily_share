import asyncio
import importlib
import importlib.util
import os
import sys
import tempfile
import threading
import types
import unittest
from datetime import datetime, timedelta
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
PLATFORM_MAIN = "bot-main"
PLATFORM_BACKUP = "bot-backup"
GROUP_TARGET_1 = f"{PLATFORM_MAIN}:GroupMessage:group-test-001"
GROUP_TARGET_2 = f"{PLATFORM_MAIN}:GroupMessage:group-test-002"
USER_TARGET_1 = f"{PLATFORM_MAIN}:FriendMessage:user-test-001"


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


class _MessageSesion:
    @staticmethod
    def from_str(value):
        platform_name, message_type, session_id = str(value).split(":", 2)
        return types.SimpleNamespace(
            platform_name=platform_name,
            message_type=message_type,
            session_id=session_id,
        )


class _DailyLifePublicPlugin:
    def __init__(self, runtime):
        self.runtime = runtime

    async def generate_share_image(
        self,
        event,
        prompt,
        *,
        model="",
        text_model="",
        edit_model="",
        contains_character=False,
    ):
        text_model = str(text_model or "").strip() or str(model or "").strip()
        edit_model = str(edit_model or "").strip() or str(model or "").strip()
        result = await self.runtime.generate_life_image_asset(
            event,
            prompt,
            "",
            contains_character=contains_character,
            preserve_reference_ratio=False,
            trusted_identity=contains_character,
            text_model=text_model,
            edit_model=edit_model,
        )
        if isinstance(result, dict):
            return str(result.get("path") or "")
        return str(getattr(result, "path", "") or "")

    async def generate_share_video(self, event, prompt, *, reference_image=""):
        result = await self.runtime.generate_life_video_asset(
            event, prompt, reference_image
        )
        if isinstance(result, dict):
            return str(result.get("url") or "")
        return str(getattr(result, "url", "") or "")


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
        self.news_snapshots = []

    async def _get_domain_state(self, key, default=None):
        return self.state.get(key, default if default is not None else {})

    async def _update_domain_state(self, key, updates):
        current = self.state.setdefault(key, {})
        current.update(updates)
        return None

    async def _set_domain_state(self, key, value):
        self.state[key] = value
        return None

    get_share_state = _get_domain_state
    get_qzone_state = _get_domain_state
    get_context_state = _get_domain_state
    get_cache_state = _get_domain_state
    update_share_state = _update_domain_state
    update_qzone_state = _update_domain_state
    update_context_state = _update_domain_state
    update_cache_state = _update_domain_state
    set_share_state = _set_domain_state
    set_qzone_state = _set_domain_state
    set_context_state = _set_domain_state
    set_cache_state = _set_domain_state

    async def add_sent_history(self, *args, **kwargs):
        self.history.append((args, kwargs))

    async def add_sent_history_with_news_snapshot(self, history, snapshot):
        self.history.append(((), dict(history)))
        await self.add_news_snapshot(
            history["target_id"],
            snapshot["source_key"],
            snapshot["source_name"],
            snapshot["image_url"],
            snapshot["items"],
        )
        return len(self.history), len(self.news_snapshots)

    async def add_sent_history_with_news_snapshots(self, history, snapshots):
        self.history.append({**history, "success": True})
        for snapshot in snapshots:
            await self.add_news_snapshot(
                snapshot["target_id"],
                snapshot["source_key"],
                snapshot["source_name"],
                snapshot["image_url"],
                snapshot["items"],
            )
        return len(self.history), list(
            range(
                len(self.news_snapshots) - len(snapshots) + 1,
                len(self.news_snapshots) + 1,
            )
        )

    async def get_recent_history_by_target(self, target_id, limit=3):
        return []

    async def add_news_snapshot(
        self, target_id, source_key, source_name, image_url, items
    ):
        snapshot = {
            "snapshot_id": len(self.news_snapshots) + 1,
            "target_id": target_id,
            "source_key": source_key,
            "source_name": source_name,
            "image_url": image_url,
            "items": items,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.news_snapshots.append(snapshot)
        return snapshot

    async def get_latest_news_snapshot(self, target_id, source_key=None):
        for snapshot in reversed(self.news_snapshots):
            if snapshot["target_id"] != target_id:
                continue
            if source_key and snapshot["source_key"] != source_key:
                continue
            return dict(snapshot)
        return None


class _CtxService:
    def __init__(self):
        self.life_context_targets = []

    async def get_life_context(self, target_umo=""):
        self.life_context_targets.append(target_umo)
        return {}

    def parse_umo(self, target):
        return "aiocqhttp", str(target).split(":")[-1]

    def is_group_chat(self, target):
        return "group" in str(target).lower()

    def is_weixin_platform(self, target):
        return str(target).endswith("@im.wechat")

    def is_onebot_event(self, event):
        return False

    def get_onebot_bot(self, target_umo="", event=None, adapter_id=""):
        return None

    async def call_onebot_action(self, bot, action, **params):
        return {}

    def _find_plugin(self, name):
        return types.SimpleNamespace(service=object())

    async def get_history_data(self, *args, **kwargs):
        return {}

    def check_group_strategy(self, *args, **kwargs):
        return True

    def format_structured_history_context(self, *args, **kwargs):
        return ""

    def format_life_context(self, *args, **kwargs):
        return ""

    async def record_bot_reply_to_history(self, *args, **kwargs):
        return None

    async def record_external_share(self, *args, **kwargs):
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

    async def generate_image(
        self, content, share_type, life_context=None, target_umo=None, event=None
    ):
        if share_type is None:
            raise AssertionError(
                "share_type should be resolved before image generation"
            )
        self.generated.append(
            {
                "content": content,
                "share_type": share_type,
                "life_context": life_context,
                "target_umo": target_umo,
            }
        )
        return "generated.png"

    async def generate_video_from_image(
        self, image_path, content, target_umo=None, event=None
    ):
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
                return _SchedulerJob(job)
        return None

    def get_jobs(self):
        return [_SchedulerJob(job) for job in self.jobs]

    def remove_job(self, job_id):
        self.jobs = [job for job in self.jobs if job["kwargs"].get("id") != job_id]


class _SchedulerJob:
    def __init__(self, record):
        kwargs = record["kwargs"]
        self.id = kwargs.get("id", "")
        self.name = kwargs.get("name", "")
        self.next_run_time = kwargs.get("run_date")


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
        self._cached_qq_adapter_id = "aiocqhttp"
        self._cached_weixin_adapter_id = ""
        self._is_terminated = False
        self._bg_tasks = set()
        self._target_locks = {}
        from daily_share_tasks_testpkg.core.container import PluginServices

        self.services = PluginServices(
            scheduler=self.scheduler,
            db=self.db,
            ctx_service=self.ctx_service,
            news_service=self.news_service,
            image_service=self.image_service,
            content_service=self.content_service,
            qzone_service=object(),
            lock=self._lock,
            target_locks={},
            basic_conf=self.basic_conf,
            extra_shares_conf=self.extra_shares_conf,
            qzone_conf=self.qzone_conf,
            image_conf=self.image_conf,
            tts_conf=self.tts_conf,
            context_conf=self.context_conf,
            receiver_conf=self.receiver_conf,
        )

    def track_task(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            coro.close()
            return None
        task = loop.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task

    def get_contact_alias(self, target_uid, event=None):
        return ""

    def emit_dashboard_event(self, event_type="status", data=None):
        return None

    def get_share_lock(self, target_uid=None, *, global_scope=False):
        if global_scope or not target_uid:
            return self._lock
        key = str(target_uid or "").strip()
        lock = self._target_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._target_locks[key] = lock
        return lock

    def is_share_busy(self, target_uid=None, *, global_scope=False):
        if global_scope:
            return self._lock.locked() or any(
                lock.locked() for lock in self._target_locks.values()
            )
        return self._lock.locked() or self.get_share_lock(target_uid).locked()

    def release_idle_share_lock(self, target_uid=None):
        key = str(target_uid or "").strip()
        lock = self._target_locks.get(key)
        if lock and not lock.locked():
            self._target_locks.pop(key, None)


def _clear_modules():
    for name in list(sys.modules):
        if name.startswith(PACKAGE_NAME) or name in {
            "astrbot",
            "astrbot.api",
            "astrbot.api.event",
            "astrbot.api.message_components",
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
    parts = name.split(".")[:-1]
    for index in range(1, len(parts) + 1):
        package_name = ".".join(parts[:index])
        if package_name in sys.modules:
            continue
        package = types.ModuleType(package_name)
        relative_parts = parts[1:index]
        package.__path__ = [str(ROOT.joinpath(*relative_parts))]
        sys.modules[package_name] = package
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
        "astrbot.core.platform.astr_message_event",
        MessageSesion=_MessageSesion,
        MessageSession=_MessageSesion,
    )
    _install_stub_module("aiofiles")
    _install_stub_module("aiohttp")

    _load_module(CONFIG_MODULE_NAME, ROOT / "core" / "config.py")
    _load_module(CONSTANTS_MODULE_NAME, ROOT / "core" / "constants.py")
    _load_module(KEYS_MODULE_NAME, ROOT / "core" / "database" / "keys.py")
    return importlib.import_module(TASKS_MODULE_NAME)


def _new_manager(mod, plugin):
    """按插件当前依赖显式重建测试服务容器。"""

    from daily_share_tasks_testpkg.core.container import PluginServices

    plugin.services = PluginServices(
        scheduler=plugin.scheduler,
        db=plugin.db,
        ctx_service=plugin.ctx_service,
        news_service=plugin.news_service,
        image_service=plugin.image_service,
        content_service=plugin.content_service,
        qzone_service=getattr(plugin, "qzone_service", object()),
        lock=plugin._lock,
        target_locks=getattr(plugin, "_target_locks", {}),
        basic_conf=plugin.basic_conf,
        extra_shares_conf=plugin.extra_shares_conf,
        qzone_conf=plugin.qzone_conf,
        image_conf=plugin.image_conf,
        tts_conf=plugin.tts_conf,
        context_conf=plugin.context_conf,
        receiver_conf=plugin.receiver_conf,
    )
    return mod.TaskManager(plugin)


def _manager(mod):
    manager = _new_manager(mod, _Plugin())
    manager.executor_helpers.get_curr_period = lambda: mod.TimePeriod.NIGHT
    return manager


class TaskFailureMessageTests(unittest.IsolatedAsyncioTestCase):
    def test_cron_validation_rejects_invalid_field_without_removing_old_job(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = _new_manager(mod, plugin)

        manager.schedule.setup_cron_job_custom(
            "qzone_auto_interaction", "0 */3 * * *", lambda: None
        )

        self.assertIsNone(manager.schedule.parse_cron_to_kwargs("*/ * * * *"))
        with self.assertRaisesRegex(ValueError, "定时表达式无效"):
            manager.schedule.setup_cron_job_custom(
                "qzone_auto_interaction", "*/ * * * *", lambda: None
            )

        jobs = [
            job
            for job in plugin.scheduler.jobs
            if job["kwargs"].get("id") == "qzone_auto_interaction"
        ]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["kwargs"]["minute"], "0")

    def test_setup_tasks_registers_enabled_fixed_time_schedule(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.config["enable_auto_share"] = True
        plugin.basic_conf.update(
            {
                "trigger_mode": "fixed_time",
                "fixed_times": ["08:00", "20:00"],
            }
        )
        plugin.extra_shares_conf.update(
            {
                "enable_60s_news": True,
                "briefing_schedule_mode": "fixed_time",
                "briefing_fixed_times": ["09:00"],
            }
        )
        plugin.qzone_conf.update(
            {
                "enable_qzone": True,
                "qzone_trigger_mode": "fixed_time",
                "qzone_fixed_times": ["21:00"],
            }
        )

        def close_background(coro):
            coro.close()
            return None

        plugin.track_task = close_background
        manager = _new_manager(mod, plugin)

        manager.schedule.setup_tasks()

        job_ids = {job.id for job in plugin.scheduler.get_jobs()}
        self.assertIn("auto_share_fixed_0", job_ids)
        self.assertIn("auto_share_fixed_1", job_ids)
        self.assertIn("share_briefing", job_ids)
        self.assertIn("qzone_share", job_ids)

    def test_setup_tasks_supports_every_schedule_mode_for_all_task_kinds(self):
        mod = _load_tasks_module()
        cases = {
            "fixed_time": {"auto_share", "share_briefing", "qzone_share"},
            "random_period": {
                "daily_random_scheduler",
                "daily_briefing_random_scheduler",
                "daily_qzone_random_scheduler",
            },
            "llm_smart": {
                "daily_smart_scheduler",
                "daily_briefing_smart_scheduler",
                "daily_qzone_smart_scheduler",
            },
            "cron": {"auto_share", "share_briefing", "qzone_share"},
        }

        for mode, expected_ids in cases.items():
            with self.subTest(mode=mode):
                plugin = _Plugin()
                plugin.config["enable_auto_share"] = True
                plugin.basic_conf.update(
                    {
                        "trigger_mode": mode,
                        "fixed_times": ["08:00"],
                        "random_periods": ["08:00-09:00"],
                        "share_cron": "0 8 * * *",
                    }
                )
                plugin.extra_shares_conf.update(
                    {
                        "enable_60s_news": True,
                        "briefing_schedule_mode": mode,
                        "briefing_fixed_times": ["09:00"],
                        "briefing_random_periods": ["09:00-10:00"],
                        "cron_briefing": "0 9 * * *",
                    }
                )
                plugin.qzone_conf.update(
                    {
                        "enable_qzone": True,
                        "qzone_trigger_mode": mode,
                        "qzone_fixed_times": ["20:00"],
                        "qzone_random_periods": ["20:00-21:00"],
                        "qzone_cron": "0 20 * * *",
                    }
                )

                def close_background(coro):
                    coro.close()
                    return None

                plugin.track_task = close_background
                manager = _new_manager(mod, plugin)
                manager.schedule.setup_tasks()

                job_ids = {job.id for job in plugin.scheduler.get_jobs()}
                self.assertTrue(expected_ids.issubset(job_ids), job_ids)

    def testlog_exception_includes_exception_type_when_message_empty(self):
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

        toolkit.log_exception("[日常分享] 测试异常日志", RuntimeError())

        self.assertEqual(len(errors), 1)
        message = errors[0][0][0]
        self.assertEqual(message, "[日常分享] 测试异常日志: RuntimeError")
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

        warnings = []

        def capture_warning(*args, **kwargs):
            warnings.append((args, kwargs))

        logger.warning = capture_warning

        class Runtime:
            def __init__(self):
                self.media = types.SimpleNamespace(
                    image=types.SimpleNamespace(generate_image=lambda _prompt: None)
                )

            async def generate_life_image_asset(
                self,
                event,
                prompt,
                aspect_ratio,
                *,
                contains_character=False,
                preserve_reference_ratio=True,
                trusted_identity=False,
                text_model="",
                edit_model="",
            ):
                raise RuntimeError()

        class Context:
            def get_all_stars(self):
                plugin = _DailyLifePublicPlugin(Runtime())
                return [
                    types.SimpleNamespace(
                        name="astrbot_plugin_daily_life",
                        root_dir_name="astrbot_plugin_daily_life",
                        display_name="daily_life",
                        activated=True,
                        star_cls=plugin,
                    )
                ]

        result = await toolkit.call_default_daily_life_media_tool(
            Context(),
            media_kind="image",
            prompt="图片提示词",
        )

        self.assertIsNone(result)
        self.assertEqual(len(warnings), 1)
        message = warnings[0][0][0]
        self.assertIn("默认配图工具调用失败", message)
        self.assertTrue(message.endswith("RuntimeError"))
        self.assertNotIn("exc_info", warnings[0][1])

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

        class Runtime:
            def __init__(self):
                self.media = types.SimpleNamespace(
                    image=types.SimpleNamespace(generate_image=lambda _prompt: None)
                )

            async def generate_life_image_asset(
                self,
                event,
                prompt,
                aspect_ratio,
                *,
                contains_character=False,
                preserve_reference_ratio=True,
                trusted_identity=False,
                text_model="",
                edit_model="",
            ):
                return types.SimpleNamespace(path="")

        class Context:
            def get_all_stars(self):
                plugin = _DailyLifePublicPlugin(Runtime())
                return [
                    types.SimpleNamespace(
                        name="astrbot_plugin_daily_life",
                        root_dir_name="astrbot_plugin_daily_life",
                        display_name="daily_life",
                        activated=True,
                        star_cls=plugin,
                    )
                ]

        result = await toolkit.call_default_daily_life_media_tool(
            Context(),
            media_kind="image",
            prompt="图片提示词",
        )

        self.assertIsNone(result)
        self.assertTrue(any("未返回有效结果" in item[0][0] for item in warnings))

    async def test_daily_life_image_uses_runtime_directed_prompt_generator(self):
        _clear_modules()

        logger = _Logger()
        _install_stub_module("astrbot")
        _install_stub_module("astrbot.api", logger=logger)

        toolkit = _load_module(
            f"{PACKAGE_NAME}.core.toolkit",
            ROOT / "core" / "toolkit.py",
        )

        calls = []
        event = object()

        class DailyLifeImage:
            async def generate_image(self, prompt):
                calls.append(("raw", prompt))
                raise AssertionError("should use runtime directed prompt generator")

        class Runtime:
            def __init__(self):
                self.media = types.SimpleNamespace(image=DailyLifeImage())

            async def generate_life_image_asset(
                self,
                received_event,
                prompt,
                aspect_ratio,
                *,
                contains_character=False,
                preserve_reference_ratio=True,
                trusted_identity=False,
                text_model="",
                edit_model="",
            ):
                calls.append(
                    (
                        "directed",
                        received_event,
                        prompt,
                        aspect_ratio,
                        contains_character,
                        preserve_reference_ratio,
                        trusted_identity,
                        text_model,
                        edit_model,
                    )
                )
                return types.SimpleNamespace(path="directed-image.jpg")

        class Context:
            def get_all_stars(self):
                plugin = _DailyLifePublicPlugin(Runtime())
                return [
                    types.SimpleNamespace(
                        name="astrbot_plugin_daily_life",
                        root_dir_name="astrbot_plugin_daily_life",
                        display_name="daily_life",
                        activated=True,
                        star_cls=plugin,
                    )
                ]

        result = await toolkit.call_default_daily_life_media_tool(
            Context(),
            media_kind="image",
            prompt="图片提示词",
            event=event,
        )

        self.assertEqual(result, "directed-image.jpg")
        self.assertEqual(
            calls,
            [
                (
                    "directed",
                    event,
                    "图片提示词",
                    "",
                    False,
                    False,
                    False,
                    "",
                    "",
                )
            ],
        )

    async def test_daily_life_image_requires_runtime_directed_prompt_generator(self):
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
                raise AssertionError("should not use raw image generator")

        class Context:
            def get_all_stars(self):
                runtime = types.SimpleNamespace(
                    media=types.SimpleNamespace(image=DailyLifeImage())
                )
                plugin = _DailyLifePublicPlugin(runtime)
                return [
                    types.SimpleNamespace(
                        name="astrbot_plugin_daily_life",
                        root_dir_name="astrbot_plugin_daily_life",
                        display_name="daily_life",
                        activated=True,
                        star_cls=plugin,
                    )
                ]

        result = await toolkit.call_default_daily_life_media_tool(
            Context(),
            media_kind="image",
            prompt="图片提示词",
        )

        self.assertIsNone(result)
        self.assertEqual(len(warnings), 1)
        self.assertIn("默认配图工具调用失败", warnings[0][0][0])

    async def test_daily_life_video_uses_runtime_video_asset_generator(self):
        _clear_modules()

        logger = _Logger()
        _install_stub_module("astrbot")
        _install_stub_module("astrbot.api", logger=logger)

        toolkit = _load_module(
            f"{PACKAGE_NAME}.core.toolkit",
            ROOT / "core" / "toolkit.py",
        )

        calls = []
        event = object()

        class Runtime:
            def __init__(self):
                self.media = types.SimpleNamespace(
                    video=types.SimpleNamespace(
                        generate_video=lambda *_args, **_kwargs: None
                    )
                )

            async def generate_life_video_asset(
                self,
                received_event,
                prompt,
                image_ref="",
            ):
                calls.append((received_event, prompt, image_ref))
                return types.SimpleNamespace(url="directed-video.mp4")

        class Context:
            def get_all_stars(self):
                plugin = _DailyLifePublicPlugin(Runtime())
                return [
                    types.SimpleNamespace(
                        name="astrbot_plugin_daily_life",
                        root_dir_name="astrbot_plugin_daily_life",
                        display_name="daily_life",
                        activated=True,
                        star_cls=plugin,
                    )
                ]

        result = await toolkit.call_default_daily_life_media_tool(
            Context(),
            media_kind="video",
            prompt="视频提示词",
            image_ref="D:/tmp/ref.png",
            event=event,
        )

        self.assertEqual(result, "directed-video.mp4")
        self.assertEqual(calls, [(event, "视频提示词", "D:/tmp/ref.png")])

    async def test_daily_life_video_only_requires_runtime_asset_generator(self):
        _clear_modules()

        logger = _Logger()
        _install_stub_module("astrbot")
        _install_stub_module("astrbot.api", logger=logger)

        toolkit = _load_module(
            f"{PACKAGE_NAME}.core.toolkit",
            ROOT / "core" / "toolkit.py",
        )

        class Runtime:
            def __init__(self):
                self.media = types.SimpleNamespace()

            async def generate_life_video_asset(
                self, received_event, prompt, image_ref=""
            ):
                return {"url": f"{prompt}:{image_ref}"}

        class Context:
            def get_all_stars(self):
                plugin = _DailyLifePublicPlugin(Runtime())
                return [
                    types.SimpleNamespace(
                        name="astrbot_plugin_daily_life",
                        root_dir_name="astrbot_plugin_daily_life",
                        display_name="daily_life",
                        activated=True,
                        star_cls=plugin,
                    )
                ]

        result = await toolkit.call_default_daily_life_media_tool(
            Context(),
            media_kind="video",
            prompt="新版视频提示词",
            image_ref="D:/tmp/ref.png",
        )

        self.assertEqual(result, "新版视频提示词:D:/tmp/ref.png")

    async def test_daily_life_video_requires_runtime_video_asset_generator(self):
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

        class Context:
            def get_all_stars(self):
                runtime = types.SimpleNamespace(
                    media=types.SimpleNamespace(
                        video=types.SimpleNamespace(
                            generate_video=lambda *_args, **_kwargs: None
                        )
                    )
                )
                plugin = _DailyLifePublicPlugin(runtime)
                return [
                    types.SimpleNamespace(
                        name="astrbot_plugin_daily_life",
                        root_dir_name="astrbot_plugin_daily_life",
                        display_name="daily_life",
                        activated=True,
                        star_cls=plugin,
                    )
                ]

        result = await toolkit.call_default_daily_life_media_tool(
            Context(),
            media_kind="video",
            prompt="视频提示词",
        )

        self.assertIsNone(result)
        self.assertEqual(len(warnings), 1)
        self.assertIn("默认视频工具调用失败", warnings[0][0][0])

    def test_news_image_filename_uses_source_key_and_long_random_suffix(self):
        mod = _load_tasks_module()
        delivery_mod = sys.modules[f"{TASKS_MODULE_NAME}.taskdelivery"]
        manager = _new_manager(mod, _Plugin())

        old_getrandbits = delivery_mod.random.getrandbits
        delivery_mod.random.getrandbits = lambda bits: 0x8005CE727817
        try:
            url = "https://api.nycnm.cn/api/v2/wb?format=image&apikey=test"
            self.assertEqual(
                manager.delivery_assets.build_news_image_filename(url),
                "weibo_8005ce727817.png",
            )
            self.assertEqual(
                manager.delivery_assets.build_news_image_filename(url),
                "weibo_8005ce727817.png",
            )

            safe_name = manager.delivery_assets.build_news_image_filename(
                "https://example.com/news.jpg?format=image",
                'A/B:C*?<>|"',
            )
            self.assertEqual(safe_name, "A_B_C_8005ce727817.jpg")

            static_name = manager.delivery_assets.build_news_image_filename(
                "https://example.com/60s",
                "60s新闻",
            )
            self.assertEqual(static_name, "60s_8005ce727817.png")

            ai_name = manager.delivery_assets.build_news_image_filename(
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
            manager = _new_manager(mod, plugin)

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

            manager.delivery_assets._cleanup_news_source_images_sync(2)

            remaining = {path.name for path in temp_dir.iterdir()}
            self.assertNotIn("weibo_000000000001.png", remaining)
            self.assertIn("zhihu_000000000002.jpg", remaining)
            self.assertIn("ai_000000000003.png", remaining)
            self.assertIn("weixin_send_000000000004.jpg", remaining)
            self.assertIn("generated.png", remaining)
            self.assertIn("global_hot_news.png", remaining)
            self.assertIn("weibo_notrandom.png", remaining)

    async def test_news_source_image_cleanup_after_download_runs_in_background(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.image_conf["news_image_cleanup_max_count"] = 2
        manager = _new_manager(mod, plugin)
        loop = asyncio.get_running_loop()
        entered = asyncio.Event()
        release = threading.Event()

        def sync_cleanup(_max_count):
            loop.call_soon_threadsafe(entered.set)
            release.wait(1)

        manager.delivery_assets._cleanup_news_source_images_sync = sync_cleanup

        manager.delivery_assets._cleanup_news_source_images_after_download()

        self.assertEqual(len(plugin._bg_tasks), 1)
        await asyncio.wait_for(entered.wait(), timeout=1)
        release.set()
        await asyncio.gather(*list(plugin._bg_tasks), return_exceptions=True)

    async def test_news_image_download_ignores_content_length_without_limit(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        written_chunks = []

        class AsyncFile:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def write(self, chunk):
                written_chunks.append(chunk)

        class Content:
            async def iter_chunked(self, _size):
                yield b"news-image"

        class Response:
            status = 200
            headers = {"Content-Length": str(33 * 1024 * 1024)}
            content = Content()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

        class Session:
            def get(self, _url, *, timeout):
                return Response()

        async def http():
            return Session()

        plugin.news_service.http = http
        cachemedia_module = sys.modules[f"{TASKS_MODULE_NAME}.cachemedia"]
        original_open = getattr(cachemedia_module.aiofiles, "open", None)
        cachemedia_module.aiofiles.open = lambda *_args, **_kwargs: AsyncFile()
        try:
            with tempfile.TemporaryDirectory() as temp_root:
                plugin.data_dir = Path(temp_root)
                manager = _new_manager(mod, plugin)

                result = await manager.delivery_assets.download_image_to_local(
                    "https://example.com/news.png", "news.png"
                )

                self.assertIsNotNone(result)
                self.assertEqual(written_chunks, [b"news-image"])
        finally:
            if original_open is None:
                del cachemedia_module.aiofiles.open
            else:
                cachemedia_module.aiofiles.open = original_open

    def test_setup_cleanup_tasks_registers_news_image_cleanup_job(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = _new_manager(mod, plugin)

        manager.schedule.setup_cleanup_tasks()

        job_ids = {job["kwargs"].get("id") for job in plugin.scheduler.jobs}
        self.assertIn("weixin_temp_cleanup", job_ids)
        self.assertIn("news_image_cleanup", job_ids)

    def test_disabled_auto_share_registers_no_scheduled_jobs(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.config["enable_auto_share"] = False
        manager = _new_manager(mod, plugin)

        manager.schedule.setup_tasks()

        self.assertEqual(plugin.scheduler.jobs, [])

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

            def remove_all_jobs(self):
                return None

            def shutdown(self, wait=False):
                return None

        class Host:
            def __init__(self):
                self._is_initialized = True
                self._is_terminated = False
                self._bg_tasks = set()
                self._lock = asyncio.Lock()
                self._target_locks = {}
                self.scheduler = Scheduler()
                self.db = types.SimpleNamespace(close=lambda: asyncio.sleep(0))
                self.news_service = types.SimpleNamespace(
                    close=lambda: asyncio.sleep(0)
                )
                self.qzone_service = types.SimpleNamespace(
                    close=lambda: asyncio.sleep(0)
                )

        started = asyncio.Event()

        async def never_finishes():
            started.set()
            await asyncio.Event().wait()

        host = Host()
        runtime = lifecycle.RuntimeService(host)
        task = runtime.track_task(never_finishes())
        await asyncio.wait_for(started.wait(), timeout=1)

        await runtime.terminate()
        await runtime.terminate()

        self.assertTrue(host._is_terminated)
        self.assertTrue(task.cancelled())
        self.assertEqual(host._bg_tasks, set())

    async def test_background_task_timeout_keeps_live_task_registered(self):
        _clear_modules()
        package = _install_stub_module(PACKAGE_NAME)
        package.__path__ = [str(ROOT)]
        core_package = _install_stub_module(CORE_PACKAGE_NAME)
        core_package.__path__ = [str(ROOT / "core")]
        host_package = _install_stub_module(f"{CORE_PACKAGE_NAME}.host")
        host_package.__path__ = [str(ROOT / "core" / "host")]
        _install_stub_module("astrbot")
        _install_stub_module("astrbot.api", logger=_Logger())
        _load_module(f"{CORE_PACKAGE_NAME}.toolkit", ROOT / "core" / "toolkit.py")
        lifecycle = _load_module(
            f"{PACKAGE_NAME}.core.host.lifecycle",
            ROOT / "core" / "host" / "lifecycle.py",
        )

        host = types.SimpleNamespace(_is_terminated=False, _bg_tasks=set())
        runtime = lifecycle.RuntimeService(host)
        cancellation_seen = asyncio.Event()
        release = asyncio.Event()

        async def ignores_first_cancel():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancellation_seen.set()
                await release.wait()

        task = runtime.track_task(ignores_first_cancel())
        await asyncio.sleep(0)
        remaining = await runtime.cancel_background_tasks(timeout=0.01)

        self.assertEqual(remaining, 1)
        self.assertTrue(cancellation_seen.is_set())
        self.assertIn(task, host._bg_tasks)
        release.set()
        await asyncio.wait_for(task, timeout=1)
        await asyncio.sleep(0)
        self.assertEqual(host._bg_tasks, set())

    def test_llm_timeout_uses_call_limit_bounded_by_global_limit(self):
        _clear_modules()
        package = _install_stub_module(PACKAGE_NAME)
        package.__path__ = [str(ROOT)]
        core_package = _install_stub_module(CORE_PACKAGE_NAME)
        core_package.__path__ = [str(ROOT / "core")]
        host_package = _install_stub_module(f"{CORE_PACKAGE_NAME}.host")
        host_package.__path__ = [str(ROOT / "core" / "host")]
        _install_stub_module("astrbot")
        _install_stub_module("astrbot.api", logger=_Logger())
        _load_module(f"{CORE_PACKAGE_NAME}.toolkit", ROOT / "core" / "toolkit.py")
        model = _load_module(
            f"{PACKAGE_NAME}.core.host.model",
            ROOT / "core" / "host" / "model.py",
        )
        service = model.LlmService(None, {"llm_timeout": 120}, lambda: False)

        self.assertEqual(service._llm_config_timeout(10), 10)
        self.assertEqual(service._llm_config_timeout(180), 120)
        self.assertEqual(service._llm_config_timeout(None), 120)

    async def test_llm_permanent_provider_error_falls_back_without_retry_delay(self):
        _clear_modules()
        package = _install_stub_module(PACKAGE_NAME)
        package.__path__ = [str(ROOT)]
        core_package = _install_stub_module(CORE_PACKAGE_NAME)
        core_package.__path__ = [str(ROOT / "core")]
        host_package = _install_stub_module(f"{CORE_PACKAGE_NAME}.host")
        host_package.__path__ = [str(ROOT / "core" / "host")]
        _install_stub_module("astrbot")
        _install_stub_module("astrbot.api", logger=_Logger())
        _load_module(f"{CORE_PACKAGE_NAME}.toolkit", ROOT / "core" / "toolkit.py")
        model = _load_module(
            f"{PACKAGE_NAME}.core.host.model",
            ROOT / "core" / "host" / "model.py",
        )

        class ProviderError(RuntimeError):
            status_code = 403
            body = {"code": "GROUP_DELETED", "message": "API Key 所属分组已删除"}

        class Context:
            def __init__(self):
                self.calls = []

            def get_config(self):
                return {
                    "provider_settings": {"default_provider_id": "provider-default"}
                }

            async def llm_generate(self, **kwargs):
                provider_id = kwargs["chat_provider_id"]
                self.calls.append(provider_id)
                if provider_id == "provider-broken":
                    raise ProviderError("403 GROUP_DELETED: API Key 所属分组已删除")
                return types.SimpleNamespace(completion_text="默认模型响应")

        context = Context()
        service = model.LlmService(
            context,
            {"llm_provider_id": "provider-broken", "llm_timeout": 60},
            lambda: False,
        )

        result = await asyncio.wait_for(service.call("测试提示"), timeout=0.5)
        next_result = await asyncio.wait_for(service.call("再次测试"), timeout=0.5)

        self.assertEqual(result, "默认模型响应")
        self.assertEqual(next_result, "默认模型响应")
        self.assertEqual(
            context.calls,
            [
                "provider-broken",
                "provider-default",
                "provider-broken",
                "provider-default",
            ],
        )

    async def test_llm_retry_uses_one_total_timeout_budget(self):
        _clear_modules()
        package = _install_stub_module(PACKAGE_NAME)
        package.__path__ = [str(ROOT)]
        core_package = _install_stub_module(CORE_PACKAGE_NAME)
        core_package.__path__ = [str(ROOT / "core")]
        host_package = _install_stub_module(f"{CORE_PACKAGE_NAME}.host")
        host_package.__path__ = [str(ROOT / "core" / "host")]
        _install_stub_module("astrbot")
        _install_stub_module("astrbot.api", logger=_Logger())
        _load_module(f"{CORE_PACKAGE_NAME}.toolkit", ROOT / "core" / "toolkit.py")
        model = _load_module(
            f"{PACKAGE_NAME}.core.host.model",
            ROOT / "core" / "host" / "model.py",
        )

        class Context:
            def __init__(self):
                self.calls = 0

            def get_config(self):
                return {"provider_settings": {"default_provider_id": "provider-main"}}

            async def llm_generate(self, **kwargs):
                self.calls += 1
                raise RuntimeError("临时网络错误")

        context = Context()
        service = model.LlmService(context, {"llm_timeout": 1}, lambda: False)

        result = await asyncio.wait_for(
            service.call("测试总时限", max_retries=5),
            timeout=1.5,
        )

        self.assertIsNone(result)
        self.assertEqual(context.calls, 1)

    async def test_manual_share_releases_lock_when_task_is_not_created(self):
        _clear_modules()
        package = _install_stub_module(PACKAGE_NAME)
        package.__path__ = [str(ROOT)]
        core_package = _install_stub_module(CORE_PACKAGE_NAME)
        core_package.__path__ = [str(ROOT / "core")]
        host_package = _install_stub_module(f"{CORE_PACKAGE_NAME}.host")
        host_package.__path__ = [str(ROOT / "core" / "host")]
        _install_stub_module("astrbot")
        _install_stub_module("astrbot.api", logger=_Logger())
        _install_stub_module("astrbot.api.event", AstrMessageEvent=object)
        job = _load_module(
            f"{PACKAGE_NAME}.core.host.job",
            ROOT / "core" / "host" / "job.py",
        )

        class Host(job.PluginShareJobService):
            def __init__(self):
                runtime = types.SimpleNamespace()
                super().__init__(runtime)
                runtime.jobs = self
                self.lock = asyncio.Lock()
                self.released = False

            def get_share_lock(self, target_uid=None, *, global_scope=False):
                return self.lock

            def track_task(self, coro):
                coro.close()
                return None

            def release_idle_share_lock(self, target_uid=None):
                self.released = True

        async def task_factory():
            return None

        host = Host()
        started = await host._start_manual_share_task(
            object(), specific_target="target", task_factory=task_factory
        )

        self.assertFalse(started)
        self.assertFalse(host.lock.locked())
        self.assertTrue(host.released)

    async def test_plugin_initialize_is_idempotent(self):
        _clear_modules()
        package = _install_stub_module(PACKAGE_NAME)
        package.__path__ = [str(ROOT)]
        core_package = _install_stub_module(CORE_PACKAGE_NAME)
        core_package.__path__ = [str(ROOT / "core")]
        host_package = _install_stub_module(f"{CORE_PACKAGE_NAME}.host")
        host_package.__path__ = [str(ROOT / "core" / "host")]
        _install_stub_module("astrbot")
        _install_stub_module("astrbot.api", logger=_Logger())
        _load_module(f"{CORE_PACKAGE_NAME}.toolkit", ROOT / "core" / "toolkit.py")
        lifecycle = _load_module(
            f"{PACKAGE_NAME}.core.host.lifecycle",
            ROOT / "core" / "host" / "lifecycle.py",
        )

        class Database:
            def __init__(self):
                self.initialize_calls = 0
                self.close_calls = 0

            async def initialize(self):
                self.initialize_calls += 1

            async def clean_expired_data(self, _days):
                return None

            async def close(self):
                self.close_calls += 1

        class Scheduler:
            running = False

            def get_jobs(self):
                return []

            def remove_all_jobs(self):
                return None

            def shutdown(self, wait=False):
                return None

        class CloseService:
            async def close(self):
                return None

        class Host:
            def __init__(self):
                self._is_initialized = False
                self._is_terminated = False
                self._runtime_state = "created"
                self._runtime_error = ""
                self._bg_tasks = set()
                self.db = Database()
                self.scheduler = Scheduler()
                self.news_service = CloseService()
                self.qzone_service = CloseService()
                self.content_service = types.SimpleNamespace(dedup_days=60)
                self.config = {}
                self.receiver_conf = {}
                self.task_manager = types.SimpleNamespace(
                    schedule=types.SimpleNamespace(setup_tasks=lambda: None)
                )
                self.ctx_service = types.SimpleNamespace(init_bots=lambda: None)
                self.tracked = 0

        with tempfile.TemporaryDirectory() as temp_dir:
            host = Host()
            host.data_dir = Path(temp_dir) / "data"
            runtime = lifecycle.RuntimeService(host)

            def track(coro):
                host.tracked += 1
                coro.close()

            runtime.track_task = track
            await runtime.initialize()
            await runtime.initialize()

        self.assertTrue(host._is_initialized)
        self.assertEqual(host._runtime_state, "ready")
        self.assertEqual(host.db.initialize_calls, 1)
        self.assertEqual(host.tracked, 1)

    async def test_plugin_terminate_continues_cleanup_when_scheduler_shutdown_fails(
        self,
    ):
        _clear_modules()
        package = _install_stub_module(PACKAGE_NAME)
        package.__path__ = [str(ROOT)]
        core_package = _install_stub_module(CORE_PACKAGE_NAME)
        core_package.__path__ = [str(ROOT / "core")]
        host_package = _install_stub_module(f"{CORE_PACKAGE_NAME}.host")
        host_package.__path__ = [str(ROOT / "core" / "host")]
        _install_stub_module("astrbot")
        _install_stub_module("astrbot.api", logger=_Logger())
        _load_module(f"{CORE_PACKAGE_NAME}.toolkit", ROOT / "core" / "toolkit.py")
        lifecycle = _load_module(
            f"{PACKAGE_NAME}.core.host.lifecycle",
            ROOT / "core" / "host" / "lifecycle.py",
        )

        class Scheduler:
            running = True

            def remove_all_jobs(self):
                return None

            def shutdown(self, wait=False):
                raise RuntimeError("shutdown failed")

        closed = []

        class Service:
            def __init__(self, name):
                self.name = name

            async def close(self):
                closed.append(self.name)

        class Host:
            def __init__(self):
                self._is_initialized = True
                self._is_terminated = False
                self._bg_tasks = set()
                self._lock = asyncio.Lock()
                self._target_locks = {}
                self.scheduler = Scheduler()
                self.db = Service("database")
                self.news_service = Service("news")
                self.qzone_service = Service("qzone")

        started = asyncio.Event()

        async def never_finishes():
            started.set()
            await asyncio.Event().wait()

        host = Host()
        runtime = lifecycle.RuntimeService(host)
        task = runtime.track_task(never_finishes())
        await asyncio.wait_for(started.wait(), timeout=1)
        await runtime.terminate()

        self.assertTrue(task.cancelled())
        self.assertEqual(closed, ["news", "qzone", "database"])

    def test_qzone_auto_interaction_default_cron_job_is_registered(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.qzone_conf = {
            "qzone_enable_auto_interaction": True,
            "qzone_enable_auto_comment": True,
            "qzone_enable_auto_reply": True,
        }
        manager = _new_manager(mod, plugin)

        manager.schedule.setup_qzone_auto_interaction_cron()

        jobs = {job["kwargs"].get("id"): job for job in plugin.scheduler.jobs}
        self.assertEqual(jobs["qzone_auto_interaction"]["trigger"], "cron")
        self.assertEqual(jobs["qzone_auto_interaction"]["kwargs"]["minute"], "0")
        self.assertEqual(jobs["qzone_auto_interaction"]["kwargs"]["hour"], "*/2")
        self.assertNotIn("qzone_auto_comment", jobs)
        self.assertNotIn("qzone_auto_reply", jobs)

    def test_qzone_auto_interaction_cron_uses_unified_schedule(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.qzone_conf = {
            "qzone_enable_auto_interaction": True,
            "qzone_enable_auto_comment": True,
            "qzone_auto_interaction_cron": "15 */3 * * *",
        }
        manager = _new_manager(mod, plugin)

        manager.schedule.setup_qzone_auto_interaction_cron()

        jobs = {job["kwargs"].get("id"): job for job in plugin.scheduler.jobs}
        self.assertEqual(jobs["qzone_auto_interaction"]["trigger"], "cron")
        self.assertEqual(jobs["qzone_auto_interaction"]["kwargs"]["minute"], "15")
        self.assertEqual(jobs["qzone_auto_interaction"]["kwargs"]["hour"], "*/3")

    async def test_qzone_auto_interaction_wrapper_schedules_random_delay(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.basic_conf = {"cron_random_delay": 0}
        plugin.qzone_conf = {"qzone_cron_random_delay": 5}
        manager = _new_manager(mod, plugin)
        called = False

        async def execute_qzone_auto_interaction(*args, **kwargs):
            nonlocal called
            called = True

        manager.qzone_interaction.execute_qzone_auto_interaction = (
            execute_qzone_auto_interaction
        )
        old_randint = mod.random.randint
        mod.random.randint = lambda start, end: 120
        try:
            await manager.schedule.triggers._task_wrapper_qzone_auto_interaction()
        finally:
            mod.random.randint = old_randint

        self.assertFalse(called)
        self.assertEqual(len(plugin.scheduler.jobs), 1)
        job = plugin.scheduler.jobs[0]
        self.assertEqual(job["trigger"], "date")
        self.assertEqual(job["kwargs"]["id"], "delayed_qzone_auto_interaction")
        self.assertIn("run_date", job["kwargs"])
        self.assertGreater(
            plugin.db.state["qzone_auto_interaction"]["pending_delay_job"][
                "target_time"
            ],
            datetime.now().timestamp(),
        )

    async def test_qzone_auto_interaction_wrapper_keeps_existing_pending_delay(self):
        mod = _load_tasks_module()
        delay_mod = sys.modules[f"{TASKS_MODULE_NAME}.scheduler.delay"]
        plugin = _Plugin()
        plugin.basic_conf = {"cron_random_delay": 0}
        plugin.qzone_conf = {"qzone_cron_random_delay": 30}
        manager = _new_manager(mod, plugin)
        called = False

        async def execute_qzone_auto_interaction(*args, **kwargs):
            nonlocal called
            called = True

        manager.qzone_interaction.execute_qzone_auto_interaction = (
            execute_qzone_auto_interaction
        )
        old_randint = delay_mod.random_module.randint
        delay_mod.random_module.randint = lambda start, end: 600
        try:
            await manager.schedule.triggers._task_wrapper_qzone_auto_interaction()
            first_target = plugin.db.state["qzone_auto_interaction"][
                "pending_delay_job"
            ]["target_time"]
            await manager.schedule.triggers._task_wrapper_qzone_auto_interaction()
        finally:
            delay_mod.random_module.randint = old_randint

        self.assertFalse(called)
        self.assertEqual(len(plugin.scheduler.jobs), 1)
        self.assertEqual(
            plugin.scheduler.jobs[0]["kwargs"]["id"], "delayed_qzone_auto_interaction"
        )
        self.assertEqual(
            plugin.db.state["qzone_auto_interaction"]["pending_delay_job"][
                "target_time"
            ],
            first_target,
        )

    async def test_qzone_fixed_time_uses_qzone_random_delay(self):
        mod = _load_tasks_module()
        delay_mod = sys.modules[f"{TASKS_MODULE_NAME}.scheduler.delay"]
        plugin = _Plugin()
        plugin.basic_conf = {"cron_random_delay": 30}
        plugin.qzone_conf = {
            "qzone_trigger_mode": "fixed_time",
            "qzone_cron_random_delay": 5,
        }
        manager = _new_manager(mod, plugin)
        called = asyncio.Event()

        async def execute_qzone_share(*args, **kwargs):
            called.set()

        manager.qzone_share.execute_qzone_share = execute_qzone_share
        old_randint = delay_mod.random_module.randint

        def fixed_delay_random(start, end):
            self.assertEqual((start, end), (0, 300))
            return 120

        delay_mod.random_module.randint = fixed_delay_random
        try:
            await manager.schedule.triggers._task_wrapper_qzone()
        finally:
            delay_mod.random_module.randint = old_randint

        self.assertFalse(called.is_set())
        jobs = {job["kwargs"].get("id"): job for job in plugin.scheduler.jobs}
        self.assertIn("delayed_qzone_share", jobs)
        self.assertGreater(
            plugin.db.state["qzone"]["pending_delay_job"]["target_time"],
            datetime.now().timestamp(),
        )

    async def test_qzone_random_period_does_not_add_random_delay(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.basic_conf = {"cron_random_delay": 30}
        plugin.qzone_conf = {
            "qzone_trigger_mode": "random_period",
            "qzone_cron_random_delay": 30,
        }
        manager = _new_manager(mod, plugin)
        called = asyncio.Event()

        async def execute_qzone_share(*args, **kwargs):
            called.set()

        manager.qzone_share.execute_qzone_share = execute_qzone_share

        await manager.schedule.triggers._task_wrapper_qzone()
        await asyncio.wait_for(called.wait(), timeout=1)

        self.assertFalse(
            any(
                job["kwargs"].get("id") == "delayed_qzone_share"
                for job in plugin.scheduler.jobs
            )
        )
        self.assertIsNone(plugin.db.state["qzone"]["pending_delay_job"])

    def test_news_tool_index_accepts_structured_chinese_ordinals(self):
        mod = _load_tasks_module()
        manager = _new_manager(mod, _Plugin())

        self.assertEqual(manager.snapshot_store._coerce_news_tool_index("10"), 10)
        self.assertEqual(manager.snapshot_store._coerce_news_tool_index("１２"), 12)
        self.assertEqual(
            manager.snapshot_store._coerce_news_tool_index("第10条链接"), 10
        )
        self.assertEqual(
            manager.snapshot_store._coerce_news_tool_index("刚才第十条原文"), 10
        )
        self.assertEqual(
            manager.snapshot_store._coerce_news_tool_index("任意文本第十一段任意后缀"),
            11,
        )
        self.assertEqual(manager.snapshot_store._coerce_news_tool_index("二十三"), 23)
        self.assertIsNone(manager.snapshot_store._coerce_news_tool_index("2024年新闻"))
        self.assertIsNone(
            manager.snapshot_store._coerce_news_tool_index("2024年第十条新闻")
        )
        self.assertIsNone(
            manager.snapshot_store._coerce_news_tool_index("第十条和第十一条")
        )

    async def test_commit_news_snapshot_stores_payload_without_fetch(self):
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
        manager = _new_manager(mod, plugin)

        ok = await manager.snapshot_store.commit_sent_news_snapshot(
            "aiocqhttp:GroupMessage:123",
            snapshot_data=manager.snapshot_store.news_snapshot_payload(
                [{"title": "新闻1", "url": "https://example.com/1"}],
                "zhihu",
            ),
        )

        snapshot = plugin.db.news_snapshots[0]
        self.assertTrue(ok)
        self.assertEqual(plugin.news_service.calls, [])
        self.assertEqual(len(snapshot["items"]), 1)
        self.assertEqual(snapshot["source_key"], "zhihu")

    async def test_load_execute_share_news_does_not_publish_snapshot_before_send(self):
        mod = _load_tasks_module()
        plugin = _Plugin()

        class NewsService(_NewsService):
            def __init__(self):
                self.calls = []

            def select_news_source(self, excluded_source=None):
                return "yicai"

            async def get_hot_news(self, source=None, limit=None, allow_fallback=True):
                self.calls.append((source, limit, allow_fallback))
                return (
                    [
                        {"title": f"新闻{i}", "url": f"https://example.com/{i}"}
                        for i in range(1, 21)
                    ],
                    source,
                )

        plugin.news_service = NewsService()
        manager = _new_manager(mod, plugin)

        loaded, news_data = await manager.share._load_execute_share_news(
            uid="aiocqhttp:GroupMessage:123",
            stype=mod.ShareType.NEWS,
            news_source="yicai",
            history_source="test",
            progress_id="progress",
        )

        self.assertTrue(loaded)
        self.assertEqual(len(news_data[0]), 20)
        self.assertEqual(plugin.news_service.calls, [("yicai", 50, True)])
        self.assertEqual(plugin.db.news_snapshots, [])
        self.assertNotIn(
            manager.snapshot_store._news_snapshot_key("aiocqhttp:GroupMessage:123"),
            plugin.db.state,
        )

    async def test_news_link_ignores_unsent_share_state_and_does_not_refresh(self):
        mod = _load_tasks_module()
        plugin = _Plugin()

        class NewsService(_NewsService):
            async def get_hot_news(self, *args, **kwargs):
                raise AssertionError("news-link lookup must not refresh remote news")

        plugin.news_service = NewsService()
        manager = _new_manager(mod, plugin)
        target = "aiocqhttp:GroupMessage:123"
        plugin.db.state[manager.snapshot_store._news_snapshot_key(target)] = {
            "source_key": "weibo",
            "source_name": "微博热搜",
            "items": [{"title": "未发送新闻", "url": "https://example.com/unsent"}],
        }

        result = await manager.snapshot_store.get_cached_news_link(
            target,
            index="1",
            source_key="weibo",
        )

        self.assertIn("还没有可用于反查的新闻列表", result)
        self.assertNotIn("https://example.com/unsent", result)

    async def test_news_link_rejects_expired_sent_snapshot(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = _new_manager(mod, plugin)
        target = "aiocqhttp:GroupMessage:123"
        await manager.snapshot_store.commit_sent_news_snapshot(
            target,
            snapshot_data=manager.snapshot_store.news_snapshot_payload(
                [{"title": "旧新闻", "url": "https://example.com/old"}],
                "weibo",
            ),
        )
        plugin.db.news_snapshots[0]["created_at"] = (
            datetime.now() - timedelta(hours=1)
        ).strftime("%Y-%m-%d %H:%M:%S")

        result = await manager.snapshot_store.get_cached_news_link(target, index="1")

        self.assertIn("新闻列表已过期", result)
        self.assertNotIn("https://example.com/old", result)

    async def test_cached_news_link_keeps_same_target_source_snapshots(self):
        mod = _load_tasks_module()
        plugin = _Plugin()

        class NewsService(_NewsService):
            async def get_hot_news(self, source=None, limit=None, allow_fallback=True):
                return (
                    [
                        {
                            "title": f"{source}新闻{i}",
                            "url": f"https://example.com/{source}/{i}",
                        }
                        for i in range(1, 3)
                    ],
                    source,
                )

        plugin.news_service = NewsService()
        manager = _new_manager(mod, plugin)
        target = "aiocqhttp:GroupMessage:123"

        await manager.snapshot_store.commit_sent_news_snapshot(
            target,
            snapshot_data=manager.snapshot_store.news_snapshot_payload(
                [
                    {"title": "知乎新闻1", "url": "https://example.com/zhihu/1"},
                    {"title": "zhihu新闻2", "url": "https://example.com/zhihu/2"},
                ],
                "zhihu",
            ),
        )
        await manager.snapshot_store.commit_sent_news_snapshot(
            target,
            snapshot_data=manager.snapshot_store.news_snapshot_payload(
                [
                    {"title": "澎湃新闻1", "url": "https://example.com/thepaper/1"},
                    {"title": "thepaper新闻2", "url": "https://example.com/thepaper/2"},
                ],
                "thepaper",
            ),
        )

        result = await manager.snapshot_store.get_cached_news_link(
            target,
            index="2",
            source_key="zhihu",
        )

        self.assertIn("zhihu新闻2", result)
        self.assertIn("https://example.com/zhihu/2", result)
        self.assertNotIn("thepaper", result)

    async def test_sent_news_snapshot_history_uses_latest_matching_source(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = _new_manager(mod, plugin)
        target = "aiocqhttp:GroupMessage:123"

        async def commit(source, title, suffix):
            await manager.snapshot_store.commit_sent_news_snapshot(
                target,
                snapshot_data=manager.snapshot_store.news_snapshot_payload(
                    [
                        {
                            "title": f"{title}{index}",
                            "url": f"https://example.com/{suffix}/{index}",
                        }
                        for index in range(1, 15)
                    ],
                    source,
                ),
                image_url=f"C:/Temp/{suffix}.png",
            )

        await commit("weibo", "09时微博", "weibo-09")
        await commit("douyin", "10时抖音", "douyin-10")
        await commit("weibo", "11时微博", "weibo-11")

        latest = await manager.snapshot_store.get_cached_news_link(target, index="14")
        douyin = await manager.snapshot_store.get_cached_news_link(
            target,
            index="14",
            source_key="douyin",
        )
        weibo = await manager.snapshot_store.get_cached_news_link(
            target,
            index="14",
            source_key="weibo",
        )

        self.assertIn("11时微博14", latest)
        self.assertIn("weibo-11/14", latest)
        self.assertIn("10时抖音14", douyin)
        self.assertIn("douyin-10/14", douyin)
        self.assertIn("11时微博14", weibo)
        self.assertNotIn("09时微博14", weibo)

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
        manager = _new_manager(mod, plugin)
        await manager.snapshot_store.commit_sent_news_snapshot(
            "aiocqhttp:GroupMessage:123",
            snapshot_data=manager.snapshot_store.news_snapshot_payload(
                [
                    {
                        "title": "目标新闻",
                        "url": "https://www.36kr.com/p/3841823029447170",
                        "description": "这是一条摘要",
                    }
                ],
                "yicai",
            ),
        )

        result = await manager.snapshot_store.get_cached_news_link(
            "aiocqhttp:GroupMessage:123",
            index="1",
        )

        self.assertEqual(
            plugin.news_service.seen_url,
            "https://www.36kr.com/p/3841823029447170",
        )
        self.assertIn("http://qdls.top/?c=abc123", result)
        self.assertNotIn("https://www.36kr.com/p/3841823029447170", result)
        self.assertIn("摘要：这是一条摘要", result)

    async def test_get_cached_news_link_reuses_short_url_cache(self):
        mod = _load_tasks_module()
        plugin = _Plugin()

        class NewsService(_NewsService):
            def __init__(self):
                self.calls = []

            async def shorten_url(self, url):
                self.calls.append(url)
                return "http://qdls.top/?c=abc123"

        plugin.news_service = NewsService()
        manager = _new_manager(mod, plugin)
        target = "aiocqhttp:GroupMessage:123"
        await manager.snapshot_store.commit_sent_news_snapshot(
            target,
            snapshot_data=manager.snapshot_store.news_snapshot_payload(
                [
                    {
                        "title": "目标新闻",
                        "url": "https://www.36kr.com/p/3841823029447170",
                    }
                ],
                "yicai",
            ),
        )

        first = await manager.snapshot_store.get_cached_news_link(target, index="1")
        second = await manager.snapshot_store.get_cached_news_link(target, index="1")

        self.assertEqual(
            plugin.news_service.calls, ["https://www.36kr.com/p/3841823029447170"]
        )
        self.assertIn("http://qdls.top/?c=abc123", first)
        self.assertIn("http://qdls.top/?c=abc123", second)
        self.assertIn("news_short_url_cache", plugin.db.state)

    async def test_get_cached_news_link_keeps_original_url_when_shortener_fails(self):
        mod = _load_tasks_module()
        plugin = _Plugin()

        class NewsService(_NewsService):
            async def shorten_url(self, url):
                raise RuntimeError("shortener unavailable")

        plugin.news_service = NewsService()
        manager = _new_manager(mod, plugin)
        await manager.snapshot_store.commit_sent_news_snapshot(
            "aiocqhttp:GroupMessage:123",
            snapshot_data=manager.snapshot_store.news_snapshot_payload(
                [{"title": "目标新闻", "url": "https://example.com/original"}],
                "yicai",
            ),
        )

        result = await manager.snapshot_store.get_cached_news_link(
            "aiocqhttp:GroupMessage:123",
            query="目标",
        )

        self.assertIn("https://example.com/original", result)

    async def test_get_cached_news_link_reuses_last_focused_item_for_followup(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = _new_manager(mod, plugin)
        target = "aiocqhttp:GroupMessage:123"
        await manager.snapshot_store.commit_sent_news_snapshot(
            target,
            snapshot_data=manager.snapshot_store.news_snapshot_payload(
                [
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
                "yicai",
            ),
        )

        first = await manager.snapshot_store.get_cached_news_link(
            target,
            index="2",
        )
        followup = await manager.snapshot_store.get_cached_news_link(
            target,
            action="summary",
        )

        self.assertIn("第二条新闻", first)
        self.assertIn("第二条新闻", followup)
        self.assertIn("摘要：第二条摘要", followup)

    async def test_get_cached_news_link_does_not_reuse_focus_across_sources(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = _new_manager(mod, plugin)
        target = "aiocqhttp:GroupMessage:123"

        def items(source):
            return [
                {
                    "title": f"{source}新闻{i}",
                    "url": f"https://example.com/{source}/{i}",
                }
                for i in range(1, 13)
            ]

        await manager.snapshot_store.commit_sent_news_snapshot(
            target,
            snapshot_data=manager.snapshot_store.news_snapshot_payload(
                items("微博"), "weibo"
            ),
        )
        await manager.snapshot_store.commit_sent_news_snapshot(
            target,
            snapshot_data=manager.snapshot_store.news_snapshot_payload(
                items("抖音"), "douyin"
            ),
        )

        focused = await manager.snapshot_store.get_cached_news_link(
            target,
            index="12",
            source_key="weibo",
        )
        followup = await manager.snapshot_store.get_cached_news_link(
            target,
            action="summary",
        )

        self.assertIn("微博新闻12", focused)
        self.assertIn("1. 抖音新闻1", followup)
        self.assertNotIn("抖音新闻12", followup)

    async def test_get_cached_news_link_returns_source_detail(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = _new_manager(mod, plugin)
        target = "aiocqhttp:GroupMessage:123"
        await manager.snapshot_store.commit_sent_news_snapshot(
            target,
            snapshot_data=manager.snapshot_store.news_snapshot_payload(
                [{"title": "目标新闻", "url": "https://example.com/source"}],
                "yicai",
            ),
        )

        result = await manager.snapshot_store.get_cached_news_link(
            target,
            action="source",
            index="1",
        )

        self.assertIn("标题：目标新闻", result)
        self.assertIn(f"来源：{YICAI_NAME}", result)
        self.assertIn("来源标识：yicai", result)

    async def test_get_cached_news_link_keeps_full_sentence_query_as_keyword(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = _new_manager(mod, plugin)
        target = "aiocqhttp:GroupMessage:123"
        await manager.snapshot_store.commit_sent_news_snapshot(
            target,
            snapshot_data=manager.snapshot_store.news_snapshot_payload(
                [{"title": "目标新闻", "url": "https://example.com/target"}],
                "yicai",
            ),
        )

        result = await manager.snapshot_store.get_cached_news_link(
            target,
            query="第1条链接",
        )

        self.assertIn("新闻列表里没找到", result)
        self.assertNotIn("https://example.com/target", result)
        self.assertNotIn("阿拉伯数字", result)

    async def test_get_cached_news_link_prefers_valid_index_over_query(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = _new_manager(mod, plugin)
        target = "aiocqhttp:GroupMessage:123"
        await manager.snapshot_store.commit_sent_news_snapshot(
            target,
            snapshot_data=manager.snapshot_store.news_snapshot_payload(
                [
                    {"title": "第一条", "url": "https://example.com/1"},
                    {"title": "第二条", "url": "https://example.com/2"},
                ],
                "yicai",
            ),
        )

        result = await manager.snapshot_store.get_cached_news_link(
            target,
            index="第二条",
            query="第一条",
        )

        self.assertIn("第二条", result)
        self.assertIn("https://example.com/2", result)

    async def test_get_cached_news_link_uses_query_when_index_is_invalid(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = _new_manager(mod, plugin)
        target = "aiocqhttp:GroupMessage:123"
        await manager.snapshot_store.commit_sent_news_snapshot(
            target,
            snapshot_data=manager.snapshot_store.news_snapshot_payload(
                [{"title": "目标新闻", "url": "https://example.com/target"}],
                "yicai",
            ),
        )

        result = await manager.snapshot_store.get_cached_news_link(
            target,
            index="无法识别",
            query="目标新闻",
        )

        self.assertIn("目标新闻", result)
        self.assertIn("https://example.com/target", result)

    async def test_share_history_keeps_success_and_records_media_degradation(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = _new_manager(mod, plugin)

        await manager.executor_helpers.record_share_history(
            target_id=GROUP_TARGET_1,
            share_type=mod.ShareType.MOOD,
            content="已发送内容",
            success=True,
            source_type="scheduled",
            degradation_reason="视频生成失败，继续发送图片",
            media_result={
                "text_sent": True,
                "image_sent": True,
                "image_path": "generated.png",
                "partial_errors": [
                    {
                        "stage": "audio",
                        "stage_label": "语音",
                        "message": "平台不支持",
                    }
                ],
            },
        )

        _args, history = plugin.db.history[0]
        self.assertTrue(history["success"])
        self.assertTrue(history["degraded"])
        self.assertIn("视频生成失败", history["degradation_reason"])
        self.assertIn("语音发送失败", history["degradation_reason"])

    def test_independent_target_schedule_accepts_clock_time(self):
        mod = _load_tasks_module()
        manager = _new_manager(mod, _Plugin())

        parsed = manager.targets.parse_targets_config(
            [f"{GROUP_TARGET_1}:8:30:问候"], expected_group=True
        )

        self.assertEqual(parsed[GROUP_TARGET_1]["cron"], "30 8 * * *")
        self.assertEqual(parsed[GROUP_TARGET_1]["seq"], "问候")

    def test_target_config_rejects_incomplete_session_id_and_wrong_bucket(self):
        mod = _load_tasks_module()
        manager = _new_manager(mod, _Plugin())

        self.assertEqual(
            manager.targets.parse_targets_config(["group-test-001"]),
            {},
        )
        self.assertEqual(
            manager.targets.parse_targets_config([USER_TARGET_1], expected_group=True),
            {},
        )

    def test_target_platform_selection_uses_exact_instance_id(self):
        mod = _load_tasks_module()
        plugin = _Plugin()

        class Platform:
            def __init__(self, platform_id):
                self.platform_id = platform_id

            def meta(self):
                return types.SimpleNamespace(
                    id=self.platform_id,
                    name="aiocqhttp",
                    support_proactive_message=True,
                )

        main = Platform(PLATFORM_MAIN)
        backup = Platform(PLATFORM_BACKUP)
        plugin.context = types.SimpleNamespace(
            platform_manager=types.SimpleNamespace(get_insts=lambda: [backup, main])
        )
        manager = _new_manager(mod, plugin)

        selected = manager.targets._select_platform_instance_for_target(GROUP_TARGET_1)

        self.assertIs(selected, main)
        self.assertIsNone(
            manager.targets._select_platform_instance_for_target(
                "bot-missing:GroupMessage:group-test-001"
            )
        )

    def test_target_input_auto_binds_only_available_instance(self):
        mod = _load_tasks_module()
        plugin = _Plugin()

        class Platform:
            def meta(self):
                return types.SimpleNamespace(
                    id=PLATFORM_MAIN,
                    name="aiocqhttp",
                    support_proactive_message=True,
                )

        plugin.context = types.SimpleNamespace(
            platform_manager=types.SimpleNamespace(get_insts=lambda: [Platform()])
        )
        manager = _new_manager(mod, plugin)

        target = manager.targets.resolve_target_input(
            "group-test-003",
            expected_group=True,
        )

        self.assertEqual(
            target,
            f"{PLATFORM_MAIN}:GroupMessage:group-test-003",
        )

    def test_target_input_requires_selection_with_multiple_instances(self):
        mod = _load_tasks_module()
        plugin = _Plugin()

        class Platform:
            def __init__(self, platform_id):
                self.platform_id = platform_id

            def meta(self):
                return types.SimpleNamespace(
                    id=self.platform_id,
                    name="aiocqhttp",
                    support_proactive_message=True,
                )

        plugin.context = types.SimpleNamespace(
            platform_manager=types.SimpleNamespace(
                get_insts=lambda: [
                    Platform(PLATFORM_MAIN),
                    Platform(PLATFORM_BACKUP),
                ]
            )
        )
        manager = _new_manager(mod, plugin)

        with self.assertRaisesRegex(ValueError, "多个机器人实例"):
            manager.targets.resolve_target_input(
                "user-test-003",
                expected_group=False,
            )

        target = manager.targets.resolve_target_input(
            "user-test-003",
            expected_group=False,
            adapter_id=PLATFORM_BACKUP,
        )
        self.assertEqual(
            target,
            f"{PLATFORM_BACKUP}:FriendMessage:user-test-003",
        )

    def test_same_id_across_platforms_is_resolved_by_target_shape(self):
        mod = _load_tasks_module()
        plugin = _Plugin()

        class Platform:
            def __init__(self, platform_type):
                self.platform_type = platform_type

            def meta(self):
                return types.SimpleNamespace(
                    id=PLATFORM_MAIN,
                    name=self.platform_type,
                    support_proactive_message=True,
                )

        plugin.context = types.SimpleNamespace(
            platform_manager=types.SimpleNamespace(
                get_insts=lambda: [Platform("aiocqhttp"), Platform("weixin_oc")]
            )
        )
        manager = _new_manager(mod, plugin)

        qq_target = manager.targets.resolve_target_input(
            "10001",
            expected_group=False,
        )
        weixin_target = manager.targets.resolve_target_input(
            "contact@im.wechat",
            expected_group=False,
        )

        self.assertEqual(qq_target, f"{PLATFORM_MAIN}:FriendMessage:10001")
        self.assertEqual(
            weixin_target,
            f"{PLATFORM_MAIN}:FriendMessage:contact@im.wechat",
        )
        self.assertEqual(
            manager.targets.ensure_target_platform_routable(qq_target).platform_type,
            "aiocqhttp",
        )
        self.assertEqual(
            manager.targets.ensure_target_platform_routable(
                weixin_target
            ).platform_type,
            "weixin_oc",
        )

    async def test_same_id_across_platforms_sends_through_selected_instance(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        calls = []

        class Platform:
            def __init__(self, platform_type):
                self.platform_type = platform_type

            def meta(self):
                return types.SimpleNamespace(
                    id=PLATFORM_MAIN,
                    name=self.platform_type,
                    support_proactive_message=True,
                )

            async def send_by_session(self, session, chain):
                calls.append((self.platform_type, session.session_id, chain))

        async def unexpected_framework_send(_uid, _chain):
            raise AssertionError("同名平台不应交给框架按 ID 取第一个实例")

        plugin.context = types.SimpleNamespace(
            send_message=unexpected_framework_send,
            platform_manager=types.SimpleNamespace(
                get_insts=lambda: [Platform("weixin_oc"), Platform("aiocqhttp")]
            ),
        )
        manager = _new_manager(mod, plugin)
        target = f"{PLATFORM_MAIN}:FriendMessage:10001"

        await manager.delivery.send_message_chain(
            target,
            _MessageChain().message("测试内容"),
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:2], ("aiocqhttp", "10001"))

    async def test_duplicate_platform_ids_block_delivery_before_framework_send(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        calls = []

        class Platform:
            def __init__(self, platform_type):
                self.platform_type = platform_type

            def meta(self):
                return types.SimpleNamespace(
                    id=PLATFORM_MAIN,
                    name=self.platform_type,
                    support_proactive_message=True,
                )

        async def send_message(_uid, _chain):
            calls.append(True)
            return True

        plugin.context = types.SimpleNamespace(
            send_message=send_message,
            platform_manager=types.SimpleNamespace(
                get_insts=lambda: [Platform("aiocqhttp"), Platform("aiocqhttp")]
            ),
        )
        manager = _new_manager(mod, plugin)

        with self.assertRaisesRegex(ValueError, "ID.*冲突"):
            await manager.delivery.send_message_chain(
                USER_TARGET_1,
                _MessageChain().message("测试内容"),
            )

        self.assertEqual(calls, [])

    def test_webchat_and_weixin_are_private_only_target_candidates(self):
        mod = _load_tasks_module()
        plugin = _Plugin()

        class Platform:
            def __init__(self, platform_id, platform_type):
                self.platform_id = platform_id
                self.platform_type = platform_type

            def meta(self):
                return types.SimpleNamespace(
                    id=self.platform_id,
                    name=self.platform_type,
                    support_proactive_message=True,
                )

        plugin.context = types.SimpleNamespace(
            platform_manager=types.SimpleNamespace(
                get_insts=lambda: [
                    Platform("browser-main", "webchat"),
                    Platform("wechat-main", "weixin_oc"),
                    Platform(PLATFORM_MAIN, "aiocqhttp"),
                ]
            )
        )
        manager = _new_manager(mod, plugin)

        self.assertEqual(
            manager.targets.get_target_platform_candidates(expected_group=True),
            [PLATFORM_MAIN],
        )
        self.assertEqual(
            manager.targets.get_target_platform_candidates(expected_group=False),
            ["browser-main", "wechat-main", PLATFORM_MAIN],
        )

    def test_target_input_keeps_matching_offline_binding(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.context = types.SimpleNamespace(
            platform_manager=types.SimpleNamespace(get_insts=lambda: [])
        )
        manager = _new_manager(mod, plugin)

        target = manager.targets.resolve_target_input(
            "group-test-004",
            expected_group=True,
            adapter_id=PLATFORM_MAIN,
            original_umo=f"{PLATFORM_MAIN}:GroupMessage:group-test-004",
        )

        self.assertEqual(
            target,
            f"{PLATFORM_MAIN}:GroupMessage:group-test-004",
        )
        with self.assertRaisesRegex(ValueError, "当前没有可绑定"):
            manager.targets.resolve_target_input(
                "group-test-005",
                expected_group=True,
            )

    def test_event_reuse_requires_exact_platform_session(self):
        mod = _load_tasks_module()
        manager = _new_manager(mod, _Plugin())
        event = _Event(unified_msg_origin=GROUP_TARGET_1)

        self.assertTrue(manager.targets.event_matches_target(event, GROUP_TARGET_1))
        self.assertFalse(
            manager.targets.event_matches_target(
                event,
                f"{PLATFORM_BACKUP}:GroupMessage:group-test-001",
            )
        )

    def test_custom_schedule_keeps_full_session_before_platform_startup(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.context = types.SimpleNamespace(
            platform_manager=types.SimpleNamespace(get_insts=lambda: [])
        )
        plugin.receiver_conf = {
            "groups": [f"{GROUP_TARGET_1}:08:30:心情"],
            "users": [],
        }
        manager = _new_manager(mod, plugin)

        manager.schedule.setup_custom_target_crons()

        job_ids = {job["kwargs"].get("id") for job in plugin.scheduler.jobs}
        self.assertIn(f"custom_share_{GROUP_TARGET_1}", job_ids)

    def test_broadcast_targets_can_be_limited_to_groups_or_users(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.receiver_conf = {
            "groups": [GROUP_TARGET_1, GROUP_TARGET_2],
            "users": [USER_TARGET_1],
        }
        manager = _new_manager(mod, plugin)

        self.assertEqual(
            manager.targets.get_broadcast_targets(target_scope="all"),
            [GROUP_TARGET_1, GROUP_TARGET_2, USER_TARGET_1],
        )
        self.assertEqual(
            manager.targets.get_broadcast_targets(target_scope="groups"),
            [GROUP_TARGET_1, GROUP_TARGET_2],
        )
        self.assertEqual(
            manager.targets.get_broadcast_targets(target_scope="users"),
            [USER_TARGET_1],
        )

    def test_manual_target_resolution_includes_independent_cron_targets(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.receiver_conf = {
            "groups": [],
            "users": [f"{USER_TARGET_1}:0 9,12,15,18 * * *:新闻"],
        }
        manager = _new_manager(mod, plugin)

        self.assertEqual(
            manager.share.resolve_execute_share_targets(target_scope="users"),
            [],
        )
        self.assertEqual(
            manager.share.resolve_execute_share_targets(
                target_scope="users",
                exclude_custom_cron=False,
            ),
            [USER_TARGET_1],
        )

    async def test_execute_share_sends_plain_news_failure_message(self):
        mod = _load_tasks_module()
        event = _Event()

        await _manager(mod).share.execute_share(
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

    async def test_execute_share_returns_false_without_targets(self):
        mod = _load_tasks_module()
        event = _Event()

        result = await _manager(mod).share.execute_share(event=event)

        self.assertFalse(result)
        self.assertEqual(
            event.sent,
            ["分享失败：未配置接收对象，也没有指定当前会话目标。"],
        )

    async def test_execute_share_continues_after_one_target_send_failure(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.receiver_conf = {
            "groups": [GROUP_TARGET_1, GROUP_TARGET_2],
            "users": [],
        }
        manager = _new_manager(mod, plugin)
        calls = []

        async def send(uid, *args, **kwargs):
            calls.append(uid)
            return len(calls) > 1

        manager.delivery.send = send

        result = await manager.share.execute_share(force_type=mod.ShareType.MOOD)

        self.assertTrue(result)
        self.assertEqual(
            calls,
            [GROUP_TARGET_1, GROUP_TARGET_2],
        )
        self.assertEqual(
            plugin.ctx_service.life_context_targets,
            [GROUP_TARGET_1, GROUP_TARGET_2],
        )
        self.assertTrue(
            any(item[1].get("success") is False for item in plugin.db.history)
        )
        self.assertTrue(
            any(item[1].get("success") is True for item in plugin.db.history)
        )

    async def test_framework_false_send_result_is_delivery_failure(self):
        mod = _load_tasks_module()
        plugin = _Plugin()

        async def send_message(_uid, _chain):
            return False

        class Platform:
            def meta(self):
                return types.SimpleNamespace(
                    id=PLATFORM_MAIN,
                    name="aiocqhttp",
                    support_proactive_message=True,
                )

        plugin.context = types.SimpleNamespace(
            send_message=send_message,
            platform_manager=types.SimpleNamespace(get_insts=lambda: [Platform()]),
        )
        manager = _new_manager(mod, plugin)

        with self.assertRaisesRegex(RuntimeError, "未找到目标平台实例"):
            await manager.delivery.send_message_chain(
                GROUP_TARGET_1,
                _MessageChain().message("测试内容"),
            )

    async def test_failed_delivery_does_not_write_success_side_effects(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.receiver_conf = {"groups": [GROUP_TARGET_1], "users": []}
        memory_calls = []

        async def record_memory(*args, **kwargs):
            memory_calls.append((args, kwargs))

        plugin.ctx_service.record_bot_reply_to_history = record_memory
        plugin.ctx_service.record_external_share = record_memory
        manager = _new_manager(mod, plugin)
        manager.delivery.send = lambda *args, **kwargs: asyncio.sleep(0, result=False)

        result = await manager.share.execute_share(force_type=mod.ShareType.MOOD)

        self.assertFalse(result)
        self.assertEqual(memory_calls, [])
        self.assertEqual(plugin.db.news_snapshots, [])
        self.assertEqual(len(plugin.db.history), 1)
        self.assertFalse(plugin.db.history[0][1]["success"])

    async def test_news_image_failure_after_text_success_skips_snapshot(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = _new_manager(mod, plugin)

        async def attach_news_image(**kwargs):
            return "https://example.com/news-image.png"

        async def generate_media(**kwargs):
            return None, "https://example.com/news-image.png", None, None, ""

        async def send(*args, media_result=None, **kwargs):
            media_result.update(
                {
                    "text_sent": True,
                    "audio_sent": False,
                    "image_sent": False,
                    "video_sent": False,
                    "partial_errors": [
                        {
                            "stage": "image",
                            "stage_label": "配图",
                            "message": "发送失败",
                        }
                    ],
                }
            )
            return True

        manager.share._maybe_attach_hot_news_image = attach_news_image
        manager.share._generate_execute_share_media = generate_media
        manager.delivery.send = send

        result = await manager.share._send_execute_share_content(
            uid=GROUP_TARGET_1,
            stype=mod.ShareType.NEWS,
            content="新闻测试内容",
            news_data=(
                [{"title": "测试新闻", "url": "https://example.com/news"}],
                "weibo",
            ),
            life_ctx="",
            period="morning",
            progress_id="progress-test",
            history_source="test",
        )

        self.assertTrue(result)
        self.assertEqual(plugin.db.news_snapshots, [])
        self.assertEqual(len(plugin.db.history), 1)
        self.assertTrue(plugin.db.history[0][1]["success"])

    async def test_execute_qzone_share_keeps_qzone_news_failure_message(self):
        mod = _load_tasks_module()
        event = _Event()

        await _manager(mod).qzone_share.execute_qzone_share(
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

        async def safe_publish_qzone(text, images):
            published.append({"text": text, "images": images})

        plugin.publish_qzone = safe_publish_qzone
        manager = _new_manager(mod, plugin)
        manager.executor_helpers.get_curr_period = lambda: mod.TimePeriod.NIGHT
        sent = []

        async def send(
            uid,
            text,
            img_path=None,
            audio_path=None,
            video_url=None,
            event=None,
            image_optional=False,
        ):
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

        manager.delivery.send = send
        event = _Event(unified_msg_origin="weixin_oc:FriendMessage:o9test@im.wechat")

        ok = await manager.qzone_share.execute_qzone_share(
            force_type=mod.ShareType.MOOD, event=event
        )

        self.assertTrue(ok)
        self.assertEqual(event.sent, [])
        self.assertEqual(published, [{"text": "content", "images": []}])
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

    async def test_execute_qzone_share_ignores_removed_video_config_and_publishes_image(
        self,
    ):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.image_conf = {"enable_ai_image": True, "enable_ai_video": True}
        plugin.qzone_conf = {
            "qzone_enable_image": True,
        }
        published = []

        async def safe_publish_qzone(text, images):
            published.append({"text": text, "images": list(images or [])})

        plugin.publish_qzone = safe_publish_qzone
        manager = _new_manager(mod, plugin)
        manager.executor_helpers.get_curr_period = lambda: mod.TimePeriod.NIGHT

        async def prepare_qzone_image(image_ref):
            return b"image-bytes"

        manager.delivery_assets.prepare_qzone_image = prepare_qzone_image

        ok = await manager.qzone_share.execute_qzone_share(
            force_type=mod.ShareType.MOOD
        )

        self.assertTrue(ok)
        self.assertEqual(published, [{"text": "content", "images": [b"image-bytes"]}])
        history_args, history_kwargs = plugin.db.history[0]
        self.assertEqual(
            history_kwargs["target_id"], sys.modules[KEYS_MODULE_NAME].QZONE_TARGET_ID
        )
        self.assertTrue(history_kwargs["success"])
        self.assertEqual(history_kwargs["media_type"], "image")
        self.assertEqual(history_kwargs["media_path"], "generated.png")

    async def test_execute_qzone_share_falls_back_to_text_when_image_publish_fails(
        self,
    ):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.image_conf = {"enable_ai_image": True, "enable_ai_video": True}
        plugin.qzone_conf = {
            "qzone_enable_image": True,
        }
        published = []

        async def safe_publish_qzone(text, images):
            payload = {"text": text, "images": list(images or [])}
            published.append(payload)
            if payload["images"]:
                raise RuntimeError("image upload failed")

        plugin.publish_qzone = safe_publish_qzone
        manager = _new_manager(mod, plugin)
        manager.executor_helpers.get_curr_period = lambda: mod.TimePeriod.NIGHT

        async def prepare_qzone_image(image_ref):
            return b"image-bytes"

        manager.delivery_assets.prepare_qzone_image = prepare_qzone_image

        ok = await manager.qzone_share.execute_qzone_share(
            force_type=mod.ShareType.MOOD
        )

        self.assertTrue(ok)
        self.assertEqual(
            published,
            [
                {"text": "content", "images": [b"image-bytes"]},
                {"text": "content", "images": []},
            ],
        )
        _history_args, history_kwargs = plugin.db.history[0]
        self.assertTrue(history_kwargs["success"])
        self.assertNotIn("media_type", history_kwargs)
        self.assertNotIn("media_path", history_kwargs)

    async def test_weixin_image_send_retries_with_smaller_copy(self):
        mod = _load_tasks_module()
        manager = _new_manager(mod, _Plugin())
        calls = []

        async def send_image(uid, img_path, event=None, media_result=None):
            calls.append(img_path)
            if len(calls) == 1:
                raise RuntimeError("upload media to cdn failed: 500")

        async def prepare_retry(img_path):
            return "small.jpg"

        manager.delivery._send_image_chain = send_image
        manager.weixin_delivery.prepare_weixin_retry_image = prepare_retry

        await manager.delivery._send_image_chain_with_retry(
            "weixin_oc:FriendMessage:o9test@im.wechat",
            "large.jpg",
        )

        self.assertEqual(calls, ["large.jpg", "small.jpg"])

    async def test_optional_weixin_image_failure_keeps_text_success(self):
        mod = _load_tasks_module()
        manager = _new_manager(mod, _Plugin())
        sent = []

        async def send_chain(uid, chain, event=None):
            sent.append(list(chain.items))
            if (
                chain.items
                and isinstance(chain.items[0], tuple)
                and chain.items[0][0] == "file_image"
            ):
                raise RuntimeError("upload media to cdn failed: 500")

        async def prepare_image(uid, img_path):
            return "prepared.jpg"

        async def prepare_retry(img_path):
            return "retry.jpg"

        manager.delivery.send_message_chain = send_chain
        manager.weixin_delivery.prepare_image_for_target = prepare_image
        manager.weixin_delivery.prepare_weixin_retry_image = prepare_retry
        manager.delivery.random_sleep = lambda: asyncio.sleep(0)

        ok = await manager.delivery.send(
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
        manager = _new_manager(mod, _Plugin())
        sent = []

        async def download_image(url, filename=None):
            self.assertEqual(url, "https://example.com/news.png")
            self.assertEqual(filename, "weibo_8005ce727817.png")
            return "Temp/weibo_8005ce727817.png"

        async def prepare_image(target, image_path):
            return image_path

        async def send_chain(uid, chain, event=None):
            sent.append(list(chain.items))

        manager.delivery_assets.build_news_image_filename = lambda url: (
            "weibo_8005ce727817.png"
        )
        manager.delivery_assets.download_image_to_local = download_image
        manager.weixin_delivery.prepare_image_for_target = prepare_image
        manager.delivery.send_message_chain = send_chain
        manager.delivery.random_sleep = lambda: asyncio.sleep(0)

        media_result = {}
        ok = await manager.delivery.send(
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

    async def test_daily_life_image_passes_character_signal_without_sending(self):
        mod = _load_tasks_module()
        image_mod = importlib.import_module(f"{CORE_PACKAGE_NAME}.image")
        calls = []

        class Runtime:
            def __init__(self):
                self.media = types.SimpleNamespace(
                    image=types.SimpleNamespace(generate_image=lambda _prompt: None)
                )

            async def generate_life_image_asset(
                self,
                received_event,
                prompt,
                aspect_ratio,
                *,
                contains_character=False,
                preserve_reference_ratio=True,
                trusted_identity=False,
                text_model="",
                edit_model="",
            ):
                calls.append(
                    (
                        received_event,
                        prompt,
                        aspect_ratio,
                        contains_character,
                        preserve_reference_ratio,
                        trusted_identity,
                        text_model,
                        edit_model,
                    )
                )
                return types.SimpleNamespace(path="daily-life-image.jpg")

        class Context:
            def get_all_stars(self):
                plugin = _DailyLifePublicPlugin(Runtime())
                return [
                    types.SimpleNamespace(
                        name="astrbot_plugin_daily_life",
                        root_dir_name="astrbot_plugin_daily_life",
                        display_name="daily_life",
                        activated=True,
                        star_cls=plugin,
                    )
                ]

        service = image_mod.ImageService(
            Context(),
            {
                "image_conf": {
                    "enable_ai_image": True,
                    "daily_life_text_image_model": "gpt-image-text",
                    "daily_life_edit_image_model": "gpt-image-edit",
                },
            },
            lambda *args, **kwargs: asyncio.sleep(0, result=""),
        )
        service._check_involves_self = lambda *args, **kwargs: asyncio.sleep(
            0, result=True
        )
        service._agent_extract_visuals = lambda *args, **kwargs: asyncio.sleep(
            0,
            result={"environment": "卧室", "subject": "台灯"},
        )
        service._assemble_final_prompt = lambda *args, **kwargs: asyncio.sleep(
            0, result="图片提示词"
        )
        event = _Event()

        result = await service.generate_image(
            "content",
            mod.ShareType.MOOD,
            "life",
            target_umo="aiocqhttp:FriendMessage:100000002",
            event=event,
        )

        self.assertEqual(result.path, "daily-life-image.jpg")
        self.assertEqual(result.description, "图片提示词")
        self.assertEqual(
            calls,
            [
                (
                    event,
                    "图片提示词",
                    "",
                    True,
                    False,
                    True,
                    "gpt-image-text",
                    "gpt-image-edit",
                )
            ],
        )
        self.assertEqual(event.sent, [])

    async def test_execute_share_generates_visual_media_before_audio(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.receiver_conf = {
            "users": ["aiocqhttp:FriendMessage:100000002"],
            "groups": [],
        }
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
        manager = _new_manager(mod, plugin)
        manager.executor_helpers.get_curr_period = lambda: mod.TimePeriod.NIGHT
        manager.delivery.random_sleep = lambda: asyncio.sleep(0)

        await manager.share.execute_share(
            force_type=mod.ShareType.MOOD,
            specific_target="aiocqhttp:FriendMessage:100000002",
        )

        self.assertEqual(order, ["image", "audio"])

    async def test_execute_share_sends_audio_then_video_without_image_when_video_exists(
        self,
    ):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.receiver_conf = {
            "users": ["aiocqhttp:FriendMessage:100000002"],
            "groups": [],
        }
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
        manager = _new_manager(mod, plugin)
        manager.executor_helpers.get_curr_period = lambda: mod.TimePeriod.NIGHT
        manager.weixin_delivery.prepare_image_for_target = lambda _uid, path: (
            asyncio.sleep(0, result=path)
        )
        manager.delivery.random_sleep = lambda: asyncio.sleep(0)
        manager.delivery.send_message_chain = send_chain

        await manager.share.execute_share(
            force_type=mod.ShareType.MOOD,
            specific_target="aiocqhttp:FriendMessage:100000002",
            event=_Event(unified_msg_origin="aiocqhttp:FriendMessage:100000002"),
        )

        self.assertEqual(order, ["image", "video", "audio"])
        self.assertEqual(len(sent), 3)
        self.assertEqual(sent[0], ["content"])
        self.assertEqual(getattr(sent[1][0], "file", None), "audio.wav")
        self.assertEqual(
            getattr(sent[2][0], "source", None), ("file_video", "video.mp4")
        )
        self.assertFalse(any(("file_image", "image.png") in chain for chain in sent))

    async def test_async_daily_share_resolves_auto_before_requested_video(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.image_conf = {"enable_ai_image": True, "enable_ai_video": False}
        manager = _new_manager(mod, plugin)
        manager.executor_helpers.get_curr_period = lambda: mod.TimePeriod.NIGHT
        sent = []

        async def send(
            target,
            content,
            image_path=None,
            audio_path=None,
            video_url=None,
            event=None,
            media_result=None,
        ):
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

        manager.delivery.send = send
        manager.weixin_delivery.prepare_image_for_target = prepare_image_for_target
        event = _Event()

        await manager.command_share.async_daily_share_task(
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
        self.assertEqual(
            plugin.content_service.calls[0][0][0], mod.ShareType.RECOMMENDATION
        )
        self.assertEqual(
            plugin.image_service.generated[0]["share_type"],
            mod.ShareType.RECOMMENDATION,
        )
        self.assertEqual(sent[0]["image_path"], "generated.png")
        self.assertEqual(len(plugin.db.history), 1)
        history_args, history_kwargs = plugin.db.history[0]
        self.assertEqual(history_kwargs["target_id"], event.unified_msg_origin)
        self.assertEqual(
            history_kwargs["share_type"], mod.ShareType.RECOMMENDATION.value
        )
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
        manager = _new_manager(mod, plugin)
        manager.executor_helpers.get_curr_period = lambda: mod.TimePeriod.NIGHT

        async def send(
            target,
            content,
            image_path=None,
            audio_path=None,
            video_url=None,
            event=None,
            media_result=None,
        ):
            self.assertEqual(image_path, "https://example.com/news.png")
            if media_result is not None:
                media_result["image_sent"] = True
                media_result["downloaded_image_path"] = "Temp/weibo_8005ce727817.png"
                media_result["image_path"] = "Temp/weibo_8005ce727817.png"
            return True

        manager.delivery.send = send
        event = _Event()

        await manager.command_share.async_daily_share_task(
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
        manager = _new_manager(mod, plugin)
        manager.executor_helpers.get_curr_period = lambda: mod.TimePeriod.NIGHT
        manager.delivery.send = lambda *args, **kwargs: asyncio.sleep(0, result=True)
        bot = _EmojiBot()
        event = _Event(bot=bot, message_id=321)

        await manager.command_share.async_daily_share_task(
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

        await _manager(mod).command_share.async_daily_share_task(
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
                "不支持的分享类型：不存在。支持：自动、问候、新闻、心情、知识、"
                "推荐、60 秒新闻、AI 资讯。"
            ],
        )

    async def test_briefing_wrapper_schedules_random_delay(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.extra_shares_conf = {
            "briefing_schedule_mode": "cron",
            "briefing_cron_random_delay": 5,
        }
        manager = _new_manager(mod, plugin)
        called = False

        async def execute_briefing_share(*args, **kwargs):
            nonlocal called
            called = True

        manager.briefing.execute_briefing_share = execute_briefing_share
        old_randint = mod.random.randint
        mod.random.randint = lambda start, end: 120
        try:
            await manager.schedule.triggers._task_wrapper_briefing()
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

    async def test_execute_briefing_share_returns_false_without_images(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = _new_manager(mod, plugin)

        result = await manager.briefing.execute_briefing_share()

        self.assertFalse(result)

    async def test_briefing_random_period_ignores_random_delay(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.extra_shares_conf = {
            "briefing_schedule_mode": "random_period",
            "briefing_cron_random_delay": 5,
        }
        manager = _new_manager(mod, plugin)
        called = False

        async def execute_briefing_share(*args, **kwargs):
            nonlocal called
            called = True

        manager.briefing.execute_briefing_share = execute_briefing_share
        old_randint = mod.random.randint
        mod.random.randint = lambda start, end: 120
        try:
            await manager.schedule.triggers._task_wrapper_briefing()
        finally:
            mod.random.randint = old_randint

        await asyncio.wait_for(asyncio.gather(*plugin._bg_tasks), timeout=1)
        self.assertTrue(called)
        self.assertEqual(plugin.scheduler.jobs, [])
        self.assertIsNone(plugin.db.state["briefing"]["pending_delay_job"])

    async def test_scheduled_qzone_wrapper_returns_before_background_task_finishes(
        self,
    ):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = _new_manager(mod, plugin)
        started = asyncio.Event()
        release = asyncio.Event()

        async def execute_qzone_share(*args, **kwargs):
            started.set()
            await release.wait()

        manager.qzone_share.execute_qzone_share = execute_qzone_share

        await manager.schedule.triggers._execute_delayed_qzone_task()

        await asyncio.wait_for(started.wait(), timeout=1)
        self.assertEqual(plugin.db.state["qzone"]["pending_delay_job"], None)
        self.assertTrue(plugin._bg_tasks)
        self.assertTrue(plugin._lock.locked())

        release.set()
        await asyncio.wait_for(asyncio.gather(*plugin._bg_tasks), timeout=1)
        self.assertFalse(plugin._lock.locked())

    async def test_overlapping_briefing_trigger_is_skipped_without_queue(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = _new_manager(mod, plugin)
        started = asyncio.Event()
        release = asyncio.Event()
        call_count = 0

        async def execute_briefing_share(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            started.set()
            await release.wait()

        manager.briefing.execute_briefing_share = execute_briefing_share

        await manager.schedule.triggers._execute_delayed_briefing_task()
        await asyncio.wait_for(started.wait(), timeout=1)
        await manager.schedule.triggers._execute_delayed_briefing_task()

        self.assertEqual(call_count, 1)
        self.assertTrue(manager.state.briefing_share_lock.locked())
        self.assertEqual(len(plugin._bg_tasks), 1)
        self.assertIsNone(plugin.db.state["briefing"]["pending_delay_job"])

        release.set()
        await asyncio.wait_for(asyncio.gather(*plugin._bg_tasks), timeout=1)
        self.assertFalse(manager.state.briefing_share_lock.locked())

    async def test_custom_target_cron_uses_global_random_delay(self):
        mod = _load_tasks_module()
        delay_mod = sys.modules[f"{TASKS_MODULE_NAME}.scheduler.delay"]
        plugin = _Plugin()
        plugin.basic_conf = {"cron_random_delay": 30}
        plugin.receiver_conf = {
            "groups": [f"{GROUP_TARGET_1}:08:30:心情"],
            "users": [],
        }
        manager = _new_manager(mod, plugin)
        called = asyncio.Event()

        async def execute_share(*args, **kwargs):
            called.set()

        manager.share.execute_share = execute_share
        manager.schedule.setup_custom_target_crons()

        custom_job = next(
            job
            for job in plugin.scheduler.jobs
            if job["kwargs"].get("id") == f"custom_share_{GROUP_TARGET_1}"
        )
        old_randint = delay_mod.random_module.randint
        delay_mod.random_module.randint = lambda start, end: 120
        try:
            await custom_job["func"]()
        finally:
            delay_mod.random_module.randint = old_randint

        job_ids = {job["kwargs"].get("id") for job in plugin.scheduler.jobs}
        self.assertFalse(called.is_set())
        self.assertIn(f"delayed_custom_share_{GROUP_TARGET_1}", job_ids)
        self.assertGreater(
            plugin.db.state[f"target_{GROUP_TARGET_1}"]["pending_delay_job"][
                "target_time"
            ],
            datetime.now().timestamp(),
        )

    async def test_custom_target_cron_without_random_delay_runs_immediately(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.basic_conf = {"cron_random_delay": 0}
        plugin.receiver_conf = {
            "groups": [f"{GROUP_TARGET_1}:08:30:心情"],
            "users": [],
        }
        manager = _new_manager(mod, plugin)
        called = asyncio.Event()

        async def execute_share(*args, **kwargs):
            called.set()

        manager.share.execute_share = execute_share
        manager.schedule.setup_custom_target_crons()

        custom_job = next(
            job
            for job in plugin.scheduler.jobs
            if job["kwargs"].get("id") == f"custom_share_{GROUP_TARGET_1}"
        )
        await custom_job["func"]()
        await asyncio.wait_for(called.wait(), timeout=1)

        job_ids = {job["kwargs"].get("id") for job in plugin.scheduler.jobs}
        self.assertNotIn(f"delayed_custom_share_{GROUP_TARGET_1}", job_ids)
        self.assertIsNone(
            plugin.db.state[f"target_{GROUP_TARGET_1}"]["pending_delay_job"]
        )

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
        manager = _new_manager(mod, plugin)

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
        plugin.call_llm = llm
        smart_mod.datetime = FixedDateTime
        smart_mod.random.randrange = lambda start, stop=None: 23
        try:
            await manager.schedule.smart._schedule_daily_smart_jobs()
        finally:
            smart_mod.datetime = old_datetime
            smart_mod.random.randrange = old_randrange

        self.assertEqual(len(plugin.scheduler.jobs), 1)
        job = plugin.scheduler.jobs[0]
        self.assertEqual(job["trigger"], "date")
        self.assertEqual(job["kwargs"]["id"], "smart_share_0")
        self.assertEqual(
            job["kwargs"]["run_date"].strftime("%Y-%m-%d %H:%M"), "2026-06-14 08:30"
        )
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
        manager = _new_manager(mod, plugin)

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 6, 14, 8, 0, 0)

        async def llm(**kwargs):
            return "[]"

        old_datetime = smart_mod.datetime
        plugin.call_llm = llm
        smart_mod.datetime = FixedDateTime
        try:
            await manager.schedule.smart._schedule_daily_qzone_smart_jobs()
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
        manager = _new_manager(mod, plugin)

        await manager.schedule.recovery._recover_pending_jobs()

        self.assertEqual(len(plugin.scheduler.jobs), 1)
        job = plugin.scheduler.jobs[0]
        self.assertEqual(job["trigger"], "date")
        self.assertEqual(job["kwargs"]["id"], "resume_briefing_share")
        self.assertEqual(
            job["kwargs"]["run_date"].replace(microsecond=0),
            target_time.replace(microsecond=0),
        )

    async def test_stale_random_schedule_build_cannot_register_jobs(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.basic_conf["random_periods"] = ["08:00-10:00"]
        manager = _new_manager(mod, plugin)
        entered = asyncio.Event()
        release = asyncio.Event()

        async def blocked_state(*args, **kwargs):
            entered.set()
            await release.wait()
            return {}

        plugin.db.get_share_state = blocked_state
        generation = manager.schedule._build_generation
        task = asyncio.create_task(
            manager.schedule.random._schedule_daily_random_jobs(generation=generation)
        )
        await asyncio.wait_for(entered.wait(), timeout=1)
        manager.schedule.invalidate_builds()
        release.set()
        await task

        self.assertEqual(plugin.scheduler.jobs, [])
        self.assertNotIn("global", plugin.db.state)

    async def test_random_period_rejects_cross_midnight_range(self):
        mod = _load_tasks_module()
        manager = _new_manager(mod, _Plugin())

        with self.assertRaisesRegex(ValueError, "随机时段不支持跨天"):
            manager.schedule.random._get_random_run_time(datetime.now(), "23:00-01:00")

    async def test_stale_smart_schedule_build_cannot_store_or_register_jobs(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        plugin.basic_conf.update(
            {
                "share_type": "自动",
                "smart_schedule_max_count": 1,
                "smart_schedule_quiet_hours": [],
            }
        )
        manager = _new_manager(mod, plugin)
        entered = asyncio.Event()
        release = asyncio.Event()

        async def blocked_llm(**kwargs):
            entered.set()
            await release.wait()
            tomorrow = datetime.now() + timedelta(days=1)
            return (
                '[{"run_at":"'
                + tomorrow.strftime("%Y-%m-%d %H:%M:%S")
                + '","share_type":"问候"}]'
            )

        plugin.call_llm = blocked_llm
        generation = manager.schedule._build_generation
        task = asyncio.create_task(
            manager.schedule.smart._schedule_daily_smart_jobs(generation=generation)
        )
        await asyncio.wait_for(entered.wait(), timeout=1)
        manager.schedule.invalidate_builds()
        release.set()
        await task

        self.assertEqual(plugin.scheduler.jobs, [])
        self.assertNotIn("global", plugin.db.state)

    async def test_stale_recovery_build_cannot_restore_pending_job(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        manager = _new_manager(mod, plugin)
        entered = asyncio.Event()
        release = asyncio.Event()
        target_time = datetime.now() + timedelta(minutes=3)

        async def blocked_state(key, default=None):
            entered.set()
            await release.wait()
            if key == "global":
                return {"pending_delay_job": {"target_time": target_time.timestamp()}}
            return default if default is not None else {}

        plugin.db.get_share_state = blocked_state
        generation = manager.schedule._build_generation
        task = asyncio.create_task(
            manager.schedule.recovery._recover_pending_jobs(generation=generation)
        )
        await asyncio.wait_for(entered.wait(), timeout=1)
        manager.schedule.invalidate_builds()
        release.set()
        await task

        self.assertEqual(plugin.scheduler.jobs, [])


if __name__ == "__main__":
    unittest.main()

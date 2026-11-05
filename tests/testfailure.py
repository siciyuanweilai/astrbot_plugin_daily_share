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

    async def merge_cache_entries(
        self, domain, key, entries, *, max_items, cache_field=None
    ):
        current = self.state.setdefault(key, {})
        cache = current if cache_field is None else current.setdefault(cache_field, {})
        for item_key, value in entries.items():
            cache.pop(item_key, None)
            cache[item_key] = value
        for item_key in list(cache)[: max(0, len(cache) - max_items)]:
            cache.pop(item_key, None)
        return current

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

    async def get_qzone_share_context(self):
        return {"life_context": "", "post_context": ""}

    async def get_chat_share_context(self, target_umo):
        context = await self.get_life_context(target_umo)
        return {"life_context": context, "post_context": context}

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
        self.qzone_conf = {"qzone_trigger_mode": "llm_smart"}
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
    manager.executor_helpers.period.get_curr_period = lambda: mod.TimePeriod.NIGHT
    return manager


class TaskFailureMessageTests(unittest.IsolatedAsyncioTestCase):
    def test_cron_weekday_uses_standard_crontab_sunday_mapping(self):
        mod = _load_tasks_module()
        manager = _manager(mod)

        self.assertEqual(
            manager.schedule.parse_cron_to_kwargs("0 8 * * 0")["day_of_week"],
            "6",
        )
        self.assertEqual(
            manager.schedule.parse_cron_to_kwargs("0 8 * * 7")["day_of_week"],
            "6",
        )
        self.assertEqual(
            manager.schedule.parse_cron_to_kwargs("0 8 * * 1-5")["day_of_week"],
            "0,1,2,3,4",
        )

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
        assets_mod = sys.modules[f"{TASKS_MODULE_NAME}.cachemedia"]
        manager = _new_manager(mod, _Plugin())

        old_getrandbits = assets_mod.random.getrandbits
        assets_mod.random.getrandbits = lambda bits: 0x8005CE727817
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
            assets_mod.random.getrandbits = old_getrandbits

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
            "qzone_trigger_mode": "llm_smart",
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
            "qzone_trigger_mode": "llm_smart",
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
        plugin.qzone_conf = {
            "qzone_trigger_mode": "llm_smart",
            "qzone_cron_random_delay": 5,
        }
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
        plugin.qzone_conf = {
            "qzone_trigger_mode": "llm_smart",
            "qzone_cron_random_delay": 30,
        }
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

    async def test_news_history_commit_invalidates_tool_context(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        invalidations = []
        plugin.support_service = types.SimpleNamespace(
            operations=types.SimpleNamespace(
                tool_context=types.SimpleNamespace(
                    invalidate_context_prompt=lambda kind, target: invalidations.append(
                        (kind, target)
                    )
                )
            )
        )
        manager = _new_manager(mod, plugin)
        target = GROUP_TARGET_1

        await manager.executor_helpers.records.record_share_history(
            target_id=target,
            share_type=mod.ShareType.NEWS,
            content="新闻内容",
            success=True,
            source_type="scheduled",
            news_snapshot_data=manager.snapshot_store.news_snapshot_payload(
                [{"title": "新闻", "url": "https://example.com/news"}],
                "yicai",
            ),
        )

        self.assertEqual(invalidations, [("news", target)])

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

        loaded, news_data = await manager.share.news.load_news(
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

        self.assertIn("标题：�commit_news_snapshot_stores_payload_without_fetch(self):
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

    async def test_news_history_commit_invalidates_tool_context(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        invalidations = []
        plugin.support_service = types.SimpleNamespace(
            operations=types.SimpleNamespace(
                tool_context=types.SimpleNamespace(
                    invalidate_context_prompt=lambda kind, target: invalidations.append(
                        (kind, target)
                    )
                )
            )
        )
        manager = _new_manager(mod, plugin)
        target = GROUP_TARGET_1

        await manager.executor_helpers.records.record_share_history(
            target_id=target,
            share_type=mod.ShareType.NEWS,
            content="新闻内容",
            success=True,
            source_type="scheduled",
            news_snapshot_data=manager.snapshot_store.news_snapshot_payload(
                [{"title": "新闻", "url": "https://example.com/news"}],
                "yicai",
            ),
        )

        self.assertEqual(invalidations, [("news", target)])

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

        loaded, news_data = await manager.share.news.load_news(
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

        self.assertIn("标题：�commit_news_snapshot_stores_payload_without_fetch(self):
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

    async def test_news_history_commit_invalidates_tool_context(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        invalidations = []
        plugin.support_service = types.SimpleNamespace(
            operations=types.SimpleNamespace(
                tool_context=types.SimpleNamespace(
                    invalidate_context_prompt=lambda kind, target: invalidations.append(
                        (kind, target)
                    )
                )
            )
        )
        manager = _new_manager(mod, plugin)
        target = GROUP_TARGET_1

        await manager.executor_helpers.records.record_share_history(
            target_id=target,
            share_type=mod.ShareType.NEWS,
            content="新闻内容",
            success=True,
            source_type="scheduled",
            news_snapshot_data=manager.snapshot_store.news_snapshot_payload(
                [{"title": "新闻", "url": "https://example.com/news"}],
                "yicai",
            ),
        )

        self.assertEqual(invalidations, [("news", target)])

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

        loaded, news_data = await manager.share.news.load_news(
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

        self.assertIn("标题：�commit_news_snapshot_stores_payload_without_fetch(self):
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

    async def test_news_history_commit_invalidates_tool_context(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        invalidations = []
        plugin.support_service = types.SimpleNamespace(
            operations=types.SimpleNamespace(
                tool_context=types.SimpleNamespace(
                    invalidate_context_prompt=lambda kind, target: invalidations.append(
                        (kind, target)
                    )
                )
            )
        )
        manager = _new_manager(mod, plugin)
        target = GROUP_TARGET_1

        await manager.executor_helpers.records.record_share_history(
            target_id=target,
            share_type=mod.ShareType.NEWS,
            content="新闻内容",
            success=True,
            source_type="scheduled",
            news_snapshot_data=manager.snapshot_store.news_snapshot_payload(
                [{"title": "新闻", "url": "https://example.com/news"}],
                "yicai",
            ),
        )

        self.assertEqual(invalidations, [("news", target)])

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

        loaded, news_data = await manager.share.news.load_news(
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

        self.assertIn("标题：�commit_news_snapshot_stores_payload_without_fetch(self):
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

    async def test_news_history_commit_invalidates_tool_context(self):
        mod = _load_tasks_module()
        plugin = _Plugin()
        invalidations = []
        plugin.support_service = types.SimpleNamespace(
            operations=types.SimpleNamespace(
                tool_context=types.SimpleNamespace(
                    invalidate_context_prompt=lambda kind, target: invalidations.append(
                        (kind, target)
                    )
                )
            )
        )
        manager = _new_manager(mod, plugin)
        target = GROUP_TARGET_1

        await manager.executor_helpers.records.record_share_history(
            target_id=target,
            share_type=mod.ShareType.NEWS,
            content="新闻内容",
            success=True,
            source_type="scheduled",
            news_snapshot_data=manager.snapshot_store.news_snapshot_payload(
                [{"title": "新闻", "url": "https://example.com/news"}],
                "yicai",
            ),
        )

        self.assertEqual(invalidations, [("news", target)])

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

        loaded, news_data = await manager.share.news.load_news(
            uid="aiocqhtthedu�nager.snapshot_storeemcanagi3Thnews_tfn excluded_source=Nonppn)
   tle": f"新闻{i}/news_sllow_fl(invalidcn)
         uid="aiocqhtthedu�news_se= "aiocqhttp:Gfor i in range(1, 21)
           
        plugin = _Plugin()
    n range(1, 21)
0ource=Nonpr.snapshotnsSer manager.snapshot� for i in r�t man
       ed_news_link_keepssample.com/{i}"}ync def get_hot_ni�an
       ednfple.n = _Plugin(14")
        douyin = await manager.snapshot_store.get_cached_news_link(
      ep=e.geter.snce=Nonhort_url(selfls = []

            def select_news_source(self, excludt manahot_store.get_cached_news_link(
      ert_u, soget_cached_news_link(target, index="1")
             rrce=Nonppn)
   tle"eibo",
        )
        followup = await �= weibo)

    async def ��t_get_cached_news  self.a sc�-{��           []

      =9�news_lEgr.snws_lEgr.snws_lEganavailable    s                 ],
                    so_manager(mod, p= []"�{��urceh�r(mod, plsnapshotnsSeple.com/zhihu/2"},
      _�c\              ],
                    so_manager(mod, p= []"�{��urceh�r(mod, plsnapshotnsSeplyt�c\             0e_()
        invalidatiog
     ni3Thnews_tfn et        iksnapshotnsSer manplugin.newoad_ne manager.snapshot� for i in r�t man
       ed_news_link_keepssample.com/{i}"}ync desut refresh remote n�b�tore.news_snapsho"ws_snapsho"ws_snapshpB�  _�cawait manager.share.news.load_news(
    psho"ws_snapshpBt manager.snapshot_store.commit_sent_news_snapshot(
            target,
            snapshot_data=manager.snaps{jsertIn("nd}             source,
   �/�D6kr.�news.l:yu�dews_snabqual(
__(self):
           (
  et_cachekr.�news.l:yu�dewul(se def get_hot_ni�an
       ednfple.n = _Plugp      manager o\     plugie_key": "weibo",ka��闻{pews(
            uid="aiocqhtthedu�In("nd}                  0e_()                source,
                )

        plugin.news_segin = _Plugine_()def      )

        0hot_dr                        "url": "httself.as     iksnapshotnsSer mar_ws_snapsce(self, excludt manarl":w_manager(mod, plugin)

        ok = await manager.snapshot_store.commit_sent_news_snapshot(
            "aiocqhttp:GroupMessage:123",
            snapshot_data=manager.snapshot_store.news_snapshot_payload(
                [{"title": "新闻1", "url": "https    rollowup = await �= weibop = await �= we           )

        plugin.newsugine_()def             )
        ).(ervice(_NewsServi�c          sna"     defanews_snapshot_data=manager.sna{fails(self):
  de    }
           )
     roupMessage:123"
        awm �-{���ewsugine_()def       elf):cesh remoten23"
  manager.slf):
  de plugi       [t_cached_news_link(
      ert_uohttp:GroupMessage:123"   operation refrink(
   t          
                �0er.sows_snapshot_history_uses_      snapshot_d�(    }
           )
     roupget_cachf.assertTrue(loadegin = _Plugin()
        manager = _nefttlugin_      snaervip170",
�"news_/{i}"rnnews_/{i}"rnnews__ws_/{i}"rnnews_/{i}"rnnews__ws_/{i}"rnnews_/{i}"rnnews__ws_/{i}"rnnews_/{i}"rnnews__ws_/{i}"rnnews_/{i}"rnnews__ws_/{i}"rnnews_/{i}"rnnews__ws_/{i}"rnnews_/{i}"rnnews__ws_/{i}"rnnews_/{i}"rnnews__ws_/{i}"rnnews_/{i}"rnnews__i (kind, target)
           70",
�"news_/{i}"rnnews_/{i}"rnnews__ws_/{i}"rnnews_/{i}"rnnews__ws_/{i}"rnnews_/{i}"rnnews__ws_/{i}"rnnews_/{i}"rnnews__ws_/{i}"rnnews_/{i}"rnnews__ws_/{i}"rnnews_/{i}"rnnews__ws_/{i}"rnnews_/{i}"rnnews__ws_/{i}"rnne��tasks_module()
        plugin�e   ws_/{i}f{i}"rnnews_/u:GroupMessage:123"

  cessage:123"

  cessage:123"

  cessage:123"

  canager.snapshot_stormodule�      )    ".share.news.loaiourcen0.g.(ernaps3"

  cessage:123"ksIn("http://qdls.to,r�otpr  )         �内news_/{i}"rnnews_  snapshot_data=manager.t thedu�In("nd}     _key": "�./{i}"rnnews__ws_/{i}"rnne_manarl":w_manager(mod, plge_u         target,
ssage0bn ras�_=(
            t  "url":        as�_=(
            t  "url":    tem_for_followup(self):
 %sf):
        mod = _load_tasks_e   sour�rews_/{i}"rnnewsnews.loaiourcenur�re[
        modddddddddddddddddmanarl":w_manager(mod, plge_u         target,
ssage0bn ras�_=(
    aAhare.news.loaiourcen0.g.(ernaps3"

     pe)data[    aAhare.news.loaiourcen0.gds3"

  c_�)  "url": "httself     ("http://qdls.t�    news.�n__/u:Gro",
            ne", "url": "https    rollowup = await �= weibop = await �= we           )

        plug
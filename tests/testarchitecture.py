import ast
import asyncio
import copy
import gc
import importlib.util
import inspect
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

if __package__:
    from .testfailure import _load_tasks_module
    from .testmedia import _load_main_module
else:
    from testfailure import _load_tasks_module
    from testmedia import _load_main_module

ROOT = Path(__file__).resolve().parents[1]


def _load_panel_revision_module():
    spec = importlib.util.spec_from_file_location(
        "daily_share_panel_revision", ROOT / "core" / "panel" / "revision.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class TaskArchitectureTests(unittest.TestCase):
    def test_release_version_is_consistent(self):
        metadata = (ROOT / "metadata.yaml").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        self.assertIn("version: 1.0.6", metadata)
        self.assertIn("version-1.0.6", readme)
        self.assertIn("v1.0.6 已发布", readme)
        self.assertIn("v1.0.6 · 2026-08-13", changelog)
        self.assertLess(changelog.index("v1.0.6"), changelog.index("v1.0.5"))
        release = changelog.split("## 🧭 v1.0.6", 1)[1].split("## 🎨 v1.0.5", 1)[0]
        self.assertIn("get_share_context(target_umo)", release)
        self.assertIn("数据库结构保持 v2", release)
        self.assertIn("成功分享记录", release)

    def test_plugin_supports_astrbot_426_and_later(self):
        metadata = (ROOT / "metadata.yaml").read_text(encoding="utf-8")
        self.assertIn('astrbot_version: ">=4.26.0"', metadata)

        platform_source = (ROOT / "core" / "platform.py").read_text(encoding="utf-8")
        permission_source = (ROOT / "core" / "host" / "permission.py").read_text(
            encoding="utf-8"
        )
        panel_source = (ROOT / "core" / "panel" / "common.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("find_platform_instance_by_keywords", platform_source)
        self.assertNotIn("_resolve_message_event", permission_source)
        self.assertNotIn("except Exception", panel_source)

    def test_panel_runtime_error_uses_chinese_description(self):
        source = (ROOT / "core" / "panel" / "panelcomponent.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("仪表盘组件必须绑定运行时", source)
        self.assertNotIn("Panel 组件必须绑定运行时", source)

    def test_services_do_not_call_other_services_private_methods(self):
        pattern = re.compile(
            r"(?:(?:task_manager|services)\.[A-Za-z_]\w*|[A-Za-z_]\w*_service)"
            r"\._[A-Za-z_]\w*"
        )
        violations = []
        for path in (ROOT / "core").rglob("*.py"):
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                if pattern.search(line):
                    violations.append(f"{path.relative_to(ROOT)}:{line_number}")
        self.assertEqual(violations, [])

    def test_event_send_is_centralized(self):
        violations = []
        for path in (ROOT / "core").rglob("*.py"):
            if path.name == "eventdelivery.py":
                continue
            if "await event.send(" in path.read_text(encoding="utf-8"):
                violations.append(str(path.relative_to(ROOT)))
        self.assertEqual(violations, [])

    def test_main_plugin_constructor_builds_command_handler_from_support_contract(self):
        mod = _load_main_module()
        context = mod.Context()
        registered_routes = []
        context.register_web_api = lambda *args: registered_routes.append(args)

        plugin = mod.DailySharePlugin(context, {})

        self.assertIs(plugin.command_handler.plugin, plugin.support_service)
        self.assertIs(plugin.command_handler.basic_conf, plugin.basic_conf)
        self.assertIs(
            plugin.command_handler.extra_shares_conf, plugin.extra_shares_conf
        )
        self.assertIs(plugin.command_handler.qzone_conf, plugin.qzone_conf)
        self.assertEqual(registered_routes, [])

    def test_main_plugin_shares_one_daily_life_bridge_across_services(self):
        mod = _load_main_module()
        context = mod.Context()
        context.register_web_api = lambda *args: None

        plugin = mod.DailySharePlugin(context, {})

        self.assertIs(plugin.ctx_service.daily_life_bridge, plugin.daily_life_bridge)
        self.assertIs(
            plugin.content_service.daily_life_bridge, plugin.daily_life_bridge
        )
        self.assertIs(plugin.image_service.daily_life_bridge, plugin.daily_life_bridge)
        self.assertIs(plugin.services.daily_life_bridge, plugin.daily_life_bridge)
        self.assertEqual(
            plugin.task_manager.executor_helpers._media_failure_message(
                "image", "配图生成失败"
            ),
            "生活插件未安装、未启用或正在重载，无法使用配图能力，继续发送文案",
        )

        context.get_all_stars = lambda: [
            SimpleNamespace(
                name="astrbot_plugin_daily_life",
                root_dir_name="astrbot_plugin_daily_life",
                activated=True,
                star_cls=SimpleNamespace(generate_share_image=lambda: None),
            )
        ]
        self.assertEqual(
            plugin.task_manager.executor_helpers._media_failure_message(
                "image", "配图生成失败"
            ),
            "配图生成失败",
        )

        plugin.daily_life_bridge._set_media_result(
            "image",
            "unavailable",
            "生活插件正在初始化、重载或停止",
        )
        self.assertEqual(
            plugin.task_manager.executor_helpers._media_failure_message(
                "image", "配图生成失败"
            ),
            "生活插件正在初始化、重载或停止，继续发送文案",
        )

    def test_main_plugin_exposes_contact_alias_service_contract(self):
        mod = _load_main_module()
        context = mod.Context()
        context.register_web_api = lambda *args: None
        plugin = mod.DailySharePlugin(context, {})
        plugin.contact_aliases = ["10001:测试用户甲"]

        self.assertEqual(plugin.get_contact_alias("10001"), "测试用户甲")
        self.assertEqual(
            plugin.support_service.get_contact_alias("10001"), "测试用户甲"
        )
        self.assertTrue(callable(plugin.set_contact_alias))
        self.assertTrue(callable(plugin.remove_contact_alias))

    def test_panel_runtime_applies_slider_payload(self):
        mod = _load_main_module()
        context = mod.Context()
        context.register_web_api = lambda *args: None
        plugin = mod.DailySharePlugin(context, {})

        plugin.dashboard_service.operations.apply._apply_page_config_payload(
            {
                "sections": {
                    "basic": {
                        "data_retention_days": 45,
                        "llm_provider_id": "provider-main",
                        "llm_timeout": 90,
                    }
                }
            }
        )

        self.assertEqual(plugin.config["basic_conf"]["data_retention_days"], 45)
        self.assertEqual(
            plugin.config["basic_conf"]["llm_provider_id"], "provider-main"
        )
        self.assertEqual(plugin.config["basic_conf"]["llm_timeout"], 90)
        self.assertNotIn("llm_conf", plugin.config)

    def test_panel_config_revisions_isolate_targets_from_other_settings(self):
        revision = _load_panel_revision_module()
        config = {
            "enable_auto_share": True,
            "receiver": {
                "groups": ["bot-main:GroupMessage:group-001:0 8 * * *:新闻"],
                "users": [],
            },
            "extra_shares": {
                "briefing_groups": [],
                "briefing_users": ["bot-main:FriendMessage:user-001"],
                "enable_ai_news": True,
            },
            "basic_conf": {"llm_timeout": 90},
        }

        target_revision = revision.target_config_revision(config)
        settings_revision = revision.settings_config_revision(config)

        target_changed = copy.deepcopy(config)
        target_changed["receiver"]["groups"] = []
        self.assertNotEqual(
            revision.target_config_revision(target_changed), target_revision
        )
        self.assertEqual(
            revision.settings_config_revision(target_changed), settings_revision
        )

        settings_changed = copy.deepcopy(config)
        settings_changed["basic_conf"]["llm_timeout"] = 120
        self.assertEqual(
            revision.target_config_revision(settings_changed), target_revision
        )
        self.assertNotEqual(
            revision.settings_config_revision(settings_changed), settings_revision
        )

    def test_panel_settings_payload_cannot_overwrite_target_lists(self):
        mod = _load_main_module()
        context = mod.Context()
        context.register_web_api = lambda *args: None
        plugin = mod.DailySharePlugin(
            context,
            {
                "receiver": {
                    "groups": ["bot-main:GroupMessage:group-001"],
                    "users": ["bot-main:FriendMessage:user-001"],
                },
                "extra_shares": {
                    "briefing_groups": ["bot-main:GroupMessage:group-001"],
                    "briefing_users": ["bot-main:FriendMessage:user-001"],
                },
            },
        )

        plugin.dashboard_service.operations.apply._apply_page_config_payload(
            {
                "sections": {
                    "target": {
                        "groups": [],
                        "users": [],
                        "briefing_groups": [],
                        "briefing_users": [],
                        "contact_aliases": ["user-001:测试用户"],
                    }
                },
                "schema_extra": {
                    "sections": {
                        "receiver": {"groups": [], "users": []},
                        "extra_shares": {
                            "briefing_groups": [],
                            "briefing_users": [],
                        },
                    }
                },
            }
        )

        self.assertEqual(
            plugin.config["receiver"]["groups"],
            ["bot-main:GroupMessage:group-001"],
        )
        self.assertEqual(
            plugin.config["receiver"]["users"],
            ["bot-main:FriendMessage:user-001"],
        )
        self.assertEqual(
            plugin.config["extra_shares"]["briefing_groups"],
            ["bot-main:GroupMessage:group-001"],
        )
        self.assertEqual(
            plugin.config["extra_shares"]["briefing_users"],
            ["bot-main:FriendMessage:user-001"],
        )
        self.assertEqual(plugin.config["contact_aliases"], ["user-001:测试用户"])

    def test_dashboard_frontend_submits_and_preserves_config_revisions(self):
        app = (ROOT / "pages" / "dashboard" / "app.js").read_text(encoding="utf-8")
        targets = (ROOT / "pages" / "dashboard" / "ui" / "targets.js").read_text(
            encoding="utf-8"
        )
        prefs = (ROOT / "pages" / "dashboard" / "ui" / "prefs.js").read_text(
            encoding="utf-8"
        )
        view = (ROOT / "pages" / "dashboard" / "ui" / "view.js").read_text(
            encoding="utf-8"
        )
        schema_map = (ROOT / "pages" / "dashboard" / "ui" / "schemamap.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("nextStatus.target_revision = state.status.target_revision", app)
        self.assertIn('target_revision: state.status?.target_revision || ""', targets)
        self.assertIn(
            'settings_revision: state.configData?.settings_revision || ""', prefs
        )
        self.assertIn("!state.configDirty && !state.configSaving", view)
        self.assertIn('target: ["cfgContactAliases"]', schema_map)

    def test_dashboard_media_uses_separate_models_without_manual_appearance(self):
        html = (ROOT / "pages" / "dashboard" / "index.html").read_text(encoding="utf-8")
        elements = (ROOT / "pages" / "dashboard" / "ui" / "elements.js").read_text(
            encoding="utf-8"
        )
        schema_map = (ROOT / "pages" / "dashboard" / "ui" / "schemamap.js").read_text(
            encoding="utf-8"
        )

        for element_id, field in (
            ("cfgDailyLifeTextImageModel", "daily_life_text_image_model"),
            ("cfgDailyLifeEditImageModel", "daily_life_edit_image_model"),
        ):
            self.assertIn(f'id="{element_id}"', html)
            self.assertIn(f'document.getElementById("{element_id}")', elements)
            self.assertIn(f'field: "{field}"', schema_map)
        self.assertNotIn("cfgAppearancePrompt", html + elements + schema_map)
        self.assertNotIn('field: "appearance_prompt"', schema_map)

        mod = _load_main_module()
        context = mod.Context()
        context.register_web_api = lambda *args: None
        plugin = mod.DailySharePlugin(context, {})
        plugin.dashboard_service.operations.apply._apply_page_config_payload(
            {
                "sections": {
                    "media": {
                        "daily_life_text_image_model": "gpt-image-text",
                        "daily_life_edit_image_model": "gpt-image-edit",
                        "appearance_prompt": "不应保存",
                    }
                }
            }
        )

        self.assertEqual(
            plugin.config["image_conf"]["daily_life_text_image_model"],
            "gpt-image-text",
        )
        self.assertEqual(
            plugin.config["image_conf"]["daily_life_edit_image_model"],
            "gpt-image-edit",
        )
        self.assertNotIn("appearance_prompt", plugin.config["image_conf"])

    def test_dashboard_labels_all_video_sources_as_video(self):
        items = (ROOT / "pages" / "dashboard" / "ui" / "items.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('badge.textContent = "视频"', items)
        self.assertNotIn("外链视频", items)
        self.assertNotIn("外部链接，可能失效", items)

    def test_panel_event_broadcast_keeps_bound_runtime_clients(self):
        mod = _load_main_module()
        context = mod.Context()
        context.register_web_api = lambda *args: None
        plugin = mod.DailySharePlugin(context, {})
        runtime = plugin.dashboard_service.operations
        queue = asyncio.Queue(maxsize=2)
        runtime._page_event_clients.add(queue)

        runtime.events.emit_dashboard_event("status", {"ready": True})

        self.assertIn(queue, runtime._page_event_clients)
        payload = queue.get_nowait()
        self.assertEqual(payload["type"], "status")
        self.assertTrue(payload["data"]["ready"])

    def test_panel_shutdown_wakes_and_removes_event_clients(self):
        mod = _load_main_module()
        context = mod.Context()
        context.register_web_api = lambda *args: None
        if not hasattr(context, "registered_web_apis"):
            context.registered_web_apis = []
        plugin = mod.DailySharePlugin(context, {})
        runtime = plugin.dashboard_service.operations
        queue = asyncio.Queue(maxsize=1)
        runtime._page_event_clients.add(queue)

        plugin.dashboard_service.shutdown()

        self.assertEqual(runtime._page_event_clients, set())
        self.assertIsNone(queue.get_nowait())

    def test_qzone_relation_tabs_use_complete_keyboard_tab_contract(self):
        html = (ROOT / "pages" / "dashboard" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "pages" / "dashboard" / "ui" / "zonerel.js").read_text(
            encoding="utf-8"
        )

        self.assertEqual(html.count('aria-controls="qzoneRelationGrid"'), 2)
        self.assertIn('role="tabpanel"', html)
        self.assertIn('aria-controls="qzoneRelationGrid"', html)
        self.assertIn('aria-selected="true"', html)
        self.assertNotIn('data-qzone-relation="care" aria-pressed', html)
        for key in ("ArrowLeft", "ArrowRight", "Home", "End"):
            self.assertIn(key, script)
        self.assertIn('setAttribute("aria-selected"', script)

    def test_panel_class_methods_have_explicit_binding_semantics(self):
        violations = []
        for path in (ROOT / "core" / "panel").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for class_node in (
                node for node in tree.body if isinstance(node, ast.ClassDef)
            ):
                for node in class_node.body:
                    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    decorators = {
                        decorator.id
                        for decorator in node.decorator_list
                        if isinstance(decorator, ast.Name)
                    }
                    if decorators & {"staticmethod", "classmethod"}:
                        continue
                    first_arg = node.args.args[0].arg if node.args.args else ""
                    if first_arg not in {"self", "cls"}:
                        violations.append(
                            f"{path.relative_to(ROOT)}:{node.lineno}:{node.name}"
                        )
        self.assertEqual(violations, [])

    def test_main_plugin_is_a_composed_star_service_host(self):
        mod = _load_main_module()
        plugin_type = mod.DailySharePlugin

        self.assertEqual(plugin_type.__bases__, (mod.Star,))
        self.assertNotIn("__getattr__", plugin_type.__dict__)
        self.assertNotIn(mod.RuntimeService, plugin_type.__mro__)
        self.assertNotIn(mod.LlmService, plugin_type.__mro__)
        self.assertNotIn(mod.SupportService, plugin_type.__mro__)
        self.assertNotIn(mod.DashboardService, plugin_type.__mro__)

        source = inspect.getsource(plugin_type.__init__)
        for attribute in (
            "runtime_service",
            "llm_service",
            "support_service",
            "dashboard_service",
        ):
            self.assertIn(f"self.{attribute} =", source)

    def test_public_support_and_dashboard_services_use_composition(self):
        mod = _load_main_module()

        self.assertEqual(mod.SupportService.__bases__, (object,))
        self.assertEqual(mod.DashboardService.__bases__, (object,))

    def test_core_domain_runtimes_have_no_inheritance_chain(self):
        mod = _load_main_module()
        tasks_mod = _load_tasks_module()
        from daily_share_tasks_testpkg.core.tasks.scheduler import (
            TaskSchedulerService,
        )
        from daily_share_tasks_testpkg.core.tasks.taskbase import TaskServiceBase

        support_runtime = mod.SupportService.__init__.__globals__["SupportRuntime"]
        panel_runtime = mod.DashboardService.__init__.__globals__["PanelRuntime"]
        services = (
            mod.ContentService,
            mod.ContextService,
            mod.DatabaseManager,
        )

        self.assertIsNotNone(tasks_mod)
        for service_type in services:
            with self.subTest(service=service_type.__name__):
                self.assertEqual(service_type.__bases__, (object,))

        self.assertEqual(panel_runtime.__bases__, (object,))
        self.assertEqual(support_runtime.__bases__, (object,))
        self.assertEqual(mod.QzoneService.__bases__, (object,))
        self.assertFalse((ROOT / "core" / "space" / "component.py").exists())

        panel_component = (ROOT / "core" / "panel" / "panelcomponent.py").read_text(
            encoding="utf-8"
        )
        support_component = (ROOT / "core" / "host" / "supportcomponent.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("class PanelDispatch", panel_component)
        self.assertNotIn("class SupportDispatch", support_component)

        self.assertEqual(TaskSchedulerService.__bases__, (TaskServiceBase,))

    def test_qzone_runtime_does_not_guess_host_api_with_getattr(self):
        source = (ROOT / "core" / "space" / "qzone.py").read_text(encoding="utf-8")
        init_source = inspect.getsource(_load_main_module().QzoneService.__init__)

        self.assertNotIn("getattr(", init_source)
        self.assertNotIn("hasattr(", init_source)
        self.assertNotIn("self.plugin", source)

    def test_qzone_public_operations_are_explicit_service_methods(self):
        qzone_type = _load_main_module().QzoneService
        public_operations = {
            "close",
            "invalidate",
            "configured",
            "status",
            "context",
            "comment",
            "delete_comment",
            "reply_comment",
            "detail",
            "last_friend_feeds_meta",
            "query_posts",
            "query_home_posts",
            "query_recent_posts",
            "query_about_me",
            "query_mention_posts",
            "query_last_year",
            "query_favorites",
            "query_message_board",
            "query_relations",
            "query_visit_stats",
        }

        self.assertTrue(public_operations <= qzone_type.__dict__.keys())
        for name in public_operations - {"last_friend_feeds_meta"}:
            with self.subTest(operation=name):
                self.assertTrue(callable(qzone_type.__dict__[name]))
        self.assertIsInstance(qzone_type.__dict__["last_friend_feeds_meta"], property)

    def test_main_plugin_registers_the_complete_llm_tool_contract(self):
        mod = _load_main_module()
        source = inspect.getsource(mod.DailySharePlugin)
        tool_names = set(re.findall(r'@filter\.llm_tool\(name="([^"]+)"\)', source))

        self.assertEqual(
            tool_names,
            {"daily_share", "news_link", "qzone", "qzone_auto_interact"},
        )

    def test_task_manager_has_no_dynamic_business_method_routing(self):
        mod = _load_tasks_module()
        manager_type = mod.TaskManager

        self.assertEqual(manager_type.__bases__, (object,))
        self.assertNotIn("__getattr__", manager_type.__dict__)
        self.assertNotIn("_bind_service_methods", manager_type.__dict__)

        from daily_share_tasks_testpkg.core.tasks.components import TaskServiceBase

        self.assertNotIn("__getattr__", TaskServiceBase.__dict__)
        self.assertNotIn("__setattr__", TaskServiceBase.__dict__)
        self.assertNotIn("_owner", TaskServiceBase.__dict__)

    def test_task_service_methods_are_bound_to_real_services(self):
        mod = _load_tasks_module()
        manager = mod.TaskManager(_ArchitecturePlugin())

        service_fields = tuple(manager.services.__dataclass_fields__)
        self.assertEqual(
            tuple(manager.services),
            tuple(getattr(manager.services, name) for name in service_fields),
        )
        self.assertEqual(len(manager.services), len(service_fields))
        self.assertIs(manager.share, manager.services.share)
        self.assertIs(manager.snapshot_store, manager.services.snapshots)
        self.assertFalse(hasattr(manager, "snapshots"))
        self.assertIs(manager.delivery, manager.services.delivery)
        self.assertIs(manager.schedule, manager.services.schedule)
        self.assertNotIn("execute_share", manager.__dict__)
        self.assertIs(manager.share.execute_share.__self__, manager.share)
        self.assertIs(
            manager.snapshot_store.get_cached_news_link.__self__,
            manager.snapshot_store,
        )
        self.assertIs(
            manager.qzone_interaction.execute_qzone_auto_interaction.__self__,
            manager.qzone_interaction,
        )

    def test_services_use_explicit_named_dependencies(self):
        mod = _load_tasks_module()
        manager = mod.TaskManager(_ArchitecturePlugin())

        self.assertIs(manager.share.services.targets, manager.targets)
        self.assertIs(manager.schedule.services.share, manager.share)
        self.assertIs(
            manager.delivery.services.weixin_delivery, manager.weixin_delivery
        )
        self.assertIs(manager.schedule.triggers.state, manager.state)
        self.assertIs(manager.schedule.smart.state, manager.state)
        self.assertFalse(inspect.ismethod(getattr(manager, "execute_share", None)))

    def test_core_does_not_use_class_dictionary_method_transplantation(self):
        violations = []
        for path in (ROOT / "core").rglob("*.py"):
            if "__dict__[" in path.read_text(encoding="utf-8"):
                violations.append(str(path.relative_to(ROOT)))
        self.assertEqual(violations, [])

    def test_components_require_explicit_runtime_without_dual_mode_fallbacks(self):
        for relative_path in (
            Path("core/panel/panelcomponent.py"),
            Path("core/host/supportcomponent.py"),
        ):
            source = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertNotIn("return self if runtime is None", source)
            self.assertNotIn("vars(self)", source)
            self.assertNotIn("__dict__.get", source)

        mod = _load_main_module()
        context = mod.Context()
        context.register_web_api = lambda *args: None
        plugin = mod.DailySharePlugin(context, {})
        panel_component = type(plugin.dashboard_service.operations.server).__mro__[1]
        support_component = type(plugin.support_service.operations.tools).__mro__[1]
        with self.assertRaises(TypeError):
            panel_component(None)
        with self.assertRaises(TypeError):
            support_component(None)

    def test_runtime_requires_explicit_service_container(self):
        _load_tasks_module()
        from daily_share_tasks_testpkg.core.tasks.runtime import TaskRuntime

        with self.assertRaises((AttributeError, TypeError)):
            TaskRuntime.from_plugin(object())


class RuntimeLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_persist_config_prefers_framework_async_save(self):
        mod = _load_main_module()

        class Config(dict):
            def __init__(self):
                super().__init__()
                self.save_calls = 0

            async def save_config_async(self):
                self.save_calls += 1

        config = Config()
        runtime = mod.RuntimeService(SimpleNamespace(config=config))

        await runtime.persist_config()

        self.assertEqual(config.save_calls, 1)

    async def test_persist_config_supports_astrbot_426_sync_save(self):
        mod = _load_main_module()

        class Config(dict):
            def __init__(self):
                super().__init__()
                self.save_calls = 0

            def save_config(self):
                self.save_calls += 1

        config = Config()
        runtime = mod.RuntimeService(SimpleNamespace(config=config))

        await runtime.persist_config()

        self.assertEqual(config.save_calls, 1)

    def test_busy_query_does_not_create_target_lock(self):
        mod = _load_main_module()
        plugin = SimpleNamespace(_lock=asyncio.Lock(), _target_locks={})
        runtime = mod.RuntimeService(plugin)

        self.assertFalse(runtime.is_share_busy("target-without-job"))
        self.assertEqual(plugin._target_locks, {})

    async def test_config_rollback_rebuilds_old_schedule_when_file_restore_fails(self):
        mod = _load_main_module()
        context = mod.Context()
        context.register_web_api = lambda *args: None
        plugin = mod.DailySharePlugin(context, {"enable_auto_share": True})
        runtime = plugin.dashboard_service.operations
        previous = {"enable_auto_share": True, "basic_conf": {"share_cron": "old"}}
        plugin.config.clear()
        plugin.config.update(
            {"enable_auto_share": False, "basic_conf": {"share_cron": "new"}}
        )
        rebuild_calls = 0

        async def fail_save():
            raise OSError("配置文件不可写")

        async def rebuild(**_kwargs):
            nonlocal rebuild_calls
            rebuild_calls += 1

        plugin.runtime_service.persist_config = fail_save
        runtime.refresh._refresh_config_refs = lambda: None
        runtime.refresh._rebuild_scheduler_after_config = rebuild

        with self.assertRaisesRegex(OSError, "配置文件不可写"):
            await runtime.refresh.save_config_and_refresh_runtime(
                previous_config=previous
            )

        self.assertEqual(plugin.config, previous)
        self.assertEqual(rebuild_calls, 1)

    async def test_config_transactions_serialize_mutation_save_and_rebuild(self):
        mod = _load_main_module()
        context = mod.Context()
        context.register_web_api = lambda *args: None
        plugin = mod.DailySharePlugin(context, {"enable_auto_share": False})
        refresh = plugin.dashboard_service.operations.refresh
        active = 0
        max_active = 0
        saved_configs = []

        async def persist_config():
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            saved_configs.append(dict(plugin.config))
            await asyncio.sleep(0)
            active -= 1

        async def rebuild(**_kwargs):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0)
            active -= 1

        plugin.runtime_service.persist_config = persist_config
        refresh.refresh._rebuild_scheduler_after_config = rebuild

        await asyncio.gather(
            refresh.save_config_and_refresh_runtime(
                mutation=lambda: plugin.config.__setitem__("first", True)
            ),
            refresh.save_config_and_refresh_runtime(
                mutation=lambda: plugin.config.__setitem__("second", True)
            ),
        )

        self.assertEqual(max_active, 1)
        self.assertTrue(plugin.config["first"])
        self.assertTrue(plugin.config["second"])
        self.assertEqual(len(saved_configs), 2)
        self.assertTrue(saved_configs[-1]["first"])
        self.assertTrue(saved_configs[-1]["second"])

    async def test_config_refresh_rebinds_all_qzone_consumers(self):
        mod = _load_main_module()
        context = mod.Context()
        context.register_web_api = lambda *args: None
        plugin = mod.DailySharePlugin(context, {})
        refresh = plugin.dashboard_service.operations.refresh
        next_qzone = {"enable_qzone": True, "qzone_adapter_id": "测试实例"}
        plugin.config["qzone_conf"] = next_qzone

        refresh.refresh._refresh_config_refs()

        self.assertIs(plugin.qzone_conf, next_qzone)
        self.assertIs(plugin.qzone_service.qzone_conf, next_qzone)
        self.assertIs(plugin.content_service.qzone_conf, next_qzone)
        self.assertIs(plugin.task_manager.config.qzone, next_qzone)

    async def test_initialize_and_terminate_are_idempotent_and_clear_tasks(self):
        mod = _load_main_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin = _LifecyclePlugin(Path(temp_dir))
            runtime = mod.RuntimeService(plugin)

            await runtime.initialize()
            await runtime.initialize()
            self.assertEqual(plugin.db.initialize_calls, 1)
            self.assertEqual(len(plugin._bg_tasks), 1)
            self.assertTrue(plugin._is_initialized)
            self.assertEqual(plugin._runtime_state, "ready")
            self.assertEqual(runtime.runtime_status()["error"], "")

            await runtime.terminate()
            await runtime.terminate()
            await asyncio.sleep(0)

            self.assertFalse(plugin._is_initialized)
            self.assertTrue(plugin._is_terminated)
            self.assertEqual(plugin._runtime_state, "terminated")
            self.assertFalse(plugin._bg_tasks)
            self.assertEqual(plugin.scheduler.shutdown_calls, 1)
            self.assertEqual(plugin.schedule_build_invalidations, 1)
            self.assertFalse(plugin.scheduler.shutdown_wait)
            self.assertEqual(plugin.db.close_calls, 1)
            self.assertEqual(plugin.news_service.close_calls, 1)
            self.assertEqual(plugin.qzone_service.close_calls, 1)

    async def test_initialize_secures_framework_config_file(self):
        mod = _load_main_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config" / "daily-share.json"
            config_path.parent.mkdir(parents=True)
            config_path.write_text("{}", encoding="utf-8")
            config_path.chmod(0o664)

            class Config(dict):
                pass

            plugin = _LifecyclePlugin(root / "data")
            plugin.config = Config()
            plugin.config.config_path = str(config_path)
            runtime = mod.RuntimeService(plugin)

            await runtime.initialize()
            await runtime.terminate()

            self.assertEqual(config_path.stat().st_mode & 0o777, 0o600)

    async def test_concurrent_initialize_and_terminate_run_once(self):
        mod = _load_main_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin = _LifecyclePlugin(Path(temp_dir))
            runtime = mod.RuntimeService(plugin)

            await asyncio.gather(runtime.initialize(), runtime.initialize())
            await asyncio.gather(runtime.terminate(), runtime.terminate())

            self.assertEqual(plugin.db.initialize_calls, 1)
            self.assertEqual(plugin.scheduler.shutdown_calls, 1)
            self.assertEqual(plugin.schedule_build_invalidations, 1)
            self.assertEqual(plugin.db.close_calls, 1)
            self.assertEqual(plugin.news_service.close_calls, 1)
            self.assertEqual(plugin.qzone_service.close_calls, 1)

    async def test_resources_close_when_background_task_cannot_stop(self):
        mod = _load_main_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin = _LifecyclePlugin(Path(temp_dir))
            runtime = mod.RuntimeService(plugin)
            plugin._is_initialized = True
            pending_marker = object()
            plugin._bg_tasks.add(pending_marker)

            async def report_pending_tasks(*, timeout=5.0):
                return 1

            runtime.cancel_background_tasks = report_pending_tasks
            await runtime.terminate()

            self.assertTrue(plugin._is_terminated)
            self.assertFalse(plugin._is_initialized)
            self.assertEqual(plugin.scheduler.shutdown_calls, 1)
            self.assertEqual(plugin.schedule_build_invalidations, 1)
            self.assertEqual(plugin.db.close_calls, 1)
            self.assertEqual(plugin.news_service.close_calls, 1)
            self.assertEqual(plugin.qzone_service.close_calls, 1)
            self.assertEqual(plugin._bg_tasks, {pending_marker})

    async def test_initialize_failure_cleans_resources_and_reports_failed_state(
        self,
    ):
        mod = _load_main_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin = _LifecyclePlugin(Path(temp_dir))

            def fail_setup():
                raise AttributeError("调度服务缺少必要入口")

            plugin.task_manager.schedule.setup_tasks = fail_setup
            runtime = mod.RuntimeService(plugin)

            with self.assertRaisesRegex(AttributeError, "调度服务缺少必要入口"):
                await runtime.initialize()

            self.assertFalse(plugin._is_initialized)
            self.assertTrue(plugin._is_terminated)
            self.assertEqual(plugin._runtime_state, "failed")
            self.assertIn("调度服务缺少必要入口", plugin._runtime_error)
            self.assertFalse(plugin._bg_tasks)
            self.assertEqual(plugin.scheduler.shutdown_calls, 1)
            self.assertEqual(plugin.schedule_build_invalidations, 1)
            self.assertEqual(plugin.db.close_calls, 1)
            self.assertEqual(plugin.news_service.close_calls, 1)
            self.assertEqual(plugin.qzone_service.close_calls, 1)

    async def test_terminated_task_failure_is_consumed(self):
        mod = _load_main_module()
        host = SimpleNamespace(_is_terminated=False, _bg_tasks=set())
        runtime = mod.RuntimeService(host)
        release = asyncio.Event()
        loop_errors = []
        loop = asyncio.get_running_loop()
        old_handler = loop.get_exception_handler()
        loop.set_exception_handler(lambda _loop, context: loop_errors.append(context))

        async def fail_after_cancel():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await release.wait()
                raise RuntimeError("关闭阶段任务失败")

        try:
            task = runtime.track_task(fail_after_cancel())
            await asyncio.sleep(0)
            remaining = await runtime.cancel_background_tasks(timeout=0.01)
            self.assertEqual(remaining, 1)
            host._is_terminated = True
            release.set()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            self.assertTrue(task.done())
            self.assertFalse(host._bg_tasks)
            del task
            gc.collect()
            await asyncio.sleep(0)
            self.assertEqual(loop_errors, [])
        finally:
            loop.set_exception_handler(old_handler)


class PanelThemeContractTests(unittest.TestCase):
    def test_panel_backend_and_dashboard_page_directory_names_are_fixed(self):
        self.assertTrue((ROOT / "core" / "panel" / "__init__.py").is_file())
        self.assertTrue((ROOT / "pages" / "dashboard" / "index.html").is_file())
        self.assertFalse((ROOT / "core" / "dashboard").exists())
        self.assertFalse((ROOT / "pages" / "panel").exists())

    def test_panel_keeps_berry_bento_theme_and_original_effect_defaults(self):
        dashboard_dir = ROOT / "pages" / "dashboard"
        style = (dashboard_dir / "style.css").read_text(encoding="utf-8")
        self.assertIn("./styles/berrybento.css", style)
        self.assertNotIn("workbench.css", style)

        theme_dir = dashboard_dir / "styles" / "berrybento"
        expected_sections = (
            "bentobase.css",
            "hero.css",
            "dashboard.css",
            "media.css",
            "zonepanel.css",
            "bentosettings.css",
            "overlays.css",
            "responsive.css",
        )
        self.assertTrue((dashboard_dir / "styles" / "berrybento.css").is_file())
        for filename in ("form.css", "lists.css", "overview.css"):
            self.assertTrue((dashboard_dir / "styles" / filename).is_file())
        self.assertTrue(all((theme_dir / name).is_file() for name in expected_sections))

        sakura = (dashboard_dir / "ui" / "sakura.js").read_text(encoding="utf-8")
        self.assertIn('localStorage.getItem(storageKey) !== "off"', sakura)
        trails = (dashboard_dir / "ui" / "trails.js").read_text(encoding="utf-8")
        effect_limits = {
            name: int(value)
            for name, value in re.findall(
                r"const (cursorTrailMaxItems|sakuraDesktopPetals|sakuraMobilePetals) = (\d+);",
                trails,
            )
        }
        self.assertEqual(
            set(effect_limits),
            {"cursorTrailMaxItems", "sakuraDesktopPetals", "sakuraMobilePetals"},
        )
        self.assertGreaterEqual(
            effect_limits["cursorTrailMaxItems"], effect_limits["sakuraDesktopPetals"]
        )
        self.assertLessEqual(
            effect_limits["sakuraMobilePetals"], effect_limits["sakuraDesktopPetals"]
        )
        self.assertIn(
            'document.documentElement.dataset.motion === "reduce"',
            trails,
        )

    def test_panel_local_assets_do_not_use_cache_version_identifiers(self):
        dashboard_dir = ROOT / "pages" / "dashboard"
        cache_keys = ("v", "ver", "version", "cache", "cachebuster", "cb")
        cache_query = re.compile(rf"[?&](?:{'|'.join(cache_keys)})=", re.IGNORECASE)

        for path in sorted(dashboard_dir.rglob("*")):
            if path.suffix.lower() not in {".html", ".css", ".js"}:
                continue
            with self.subTest(path=path.relative_to(dashboard_dir)):
                content = path.read_text(encoding="utf-8")
                self.assertIsNone(cache_query.search(content))

    def test_dashboard_hero_has_stable_tablet_and_mobile_layout_rules(self):
        dashboard_dir = ROOT / "pages" / "dashboard"
        hero = (dashboard_dir / "styles" / "berrybento" / "hero.css").read_text(
            encoding="utf-8"
        )
        responsive = (
            dashboard_dir / "styles" / "berrybento" / "responsive.css"
        ).read_text(encoding="utf-8")

        self.assertIn("word-break: keep-all", hero)
        self.assertIn("@media (max-width: 900px)", responsive)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", responsive)
        self.assertIn("@media (max-width: 420px)", responsive)
        self.assertIn("inset-block: auto 12px", responsive)

    def test_dashboard_css_keeps_accessible_stable_typography_contract(self):
        styles_dir = ROOT / "pages" / "dashboard" / "styles"
        css = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(styles_dir.rglob("*.css"))
        )

        self.assertNotRegex(css, r"outline\s*:\s*(?:none|0)(?:\s|;)")
        self.assertNotRegex(css, r"letter-spacing\s*:\s*-")
        self.assertNotRegex(css, r"font-size\s*:[^;]*(?:vw|vh)")
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertIn('html[data-motion="reduce"],', css)
        self.assertIn(":focus-visible", css)

    def test_custom_select_options_use_activedescendant_focus_model(self):
        dashboard_dir = ROOT / "pages" / "dashboard" / "ui"
        for filename in ("selects.js", "combos.js"):
            source = (dashboard_dir / filename).read_text(encoding="utf-8")
            self.assertIn("item.tabIndex = -1;", source)
            self.assertIn('role = "option"', source)

    def test_custom_select_receives_combo_close_contract(self):
        dashboard_dir = ROOT / "pages" / "dashboard" / "ui"
        selects = (dashboard_dir / "selects.js").read_text(encoding="utf-8")
        combos = (dashboard_dir / "combos.js").read_text(encoding="utf-8")

        self.assertIn("closeSweetCombos,\n    initSweetCombos", selects)
        self.assertIn("closeSweetCombos,\n    initSweetCombos", combos)

    def test_qzone_random_delay_follows_fixed_and_advanced_schedule_modes(self):
        dashboard_dir = ROOT / "pages" / "dashboard"
        page = (dashboard_dir / "index.html").read_text(encoding="utf-8")
        settings = (dashboard_dir / "ui" / "prefs.js").read_text(encoding="utf-8")

        self.assertIn('<label class="setting-field" data-schedule="qzone-delay">', page)
        self.assertIn(
            'const delayVisible = mode === "fixed_time" || mode === "cron";',
            settings,
        )

    def test_dashboard_does_not_expose_persona_overrides(self):
        dashboard_dir = ROOT / "pages" / "dashboard"
        sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(dashboard_dir.rglob("*"))
            if path.suffix.lower() in {".html", ".js"}
        )

        self.assertNotIn("cfgUsePersona", sources)
        self.assertNotIn("cfgPersonaId", sources)
        self.assertNotIn("cfgPersonaOptions", sources)

    def test_dashboard_model_controls_are_inside_basic_section(self):
        page = (ROOT / "pages" / "dashboard" / "index.html").read_text(encoding="utf-8")
        basic_start = page.index('<section id="settings-basic"')
        sequence_start = page.index('<section id="settings-sequence"')
        basic_section = page[basic_start:sequence_start]

        self.assertIn('id="cfgLlmProviderId"', basic_section)
        self.assertIn('id="cfgLlmTimeout"', basic_section)
        self.assertNotIn('id="settings-llm"', page)
        self.assertNotIn('href="#settings-llm"', page)


class _LifecycleDb:
    def __init__(self):
        self.initialize_calls = 0
        self.close_calls = 0

    async def initialize(self):
        self.initialize_calls += 1

    async def close(self):
        self.close_calls += 1


class _LifecycleCloseService:
    def __init__(self):
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1


class _LifecycleScheduler:
    def __init__(self):
        self.running = True
        self.shutdown_calls = 0
        self.shutdown_wait = None

    def remove_all_jobs(self):
        return None

    def shutdown(self, wait=True):
        self.shutdown_calls += 1
        self.shutdown_wait = wait
        self.running = False


class _LifecyclePlugin:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.config = {}
        self.receiver_conf = {}
        self.db = _LifecycleDb()
        self.scheduler = _LifecycleScheduler()
        self.news_service = _LifecycleCloseService()
        self.qzone_service = _LifecycleCloseService()
        self.content_service = SimpleNamespace(dedup_days=60)
        self.schedule_build_invalidations = 0
        self.task_manager = SimpleNamespace(
            schedule=SimpleNamespace(
                setup_tasks=lambda: None,
                invalidate_builds=self._invalidate_schedule_builds,
            )
        )
        self.ctx_service = SimpleNamespace(init_bots=lambda: None)
        self._is_initialized = False
        self._is_terminated = False
        self._runtime_state = "created"
        self._runtime_error = ""
        self._bg_tasks = set()

    def _invalidate_schedule_builds(self):
        self.schedule_build_invalidations += 1


class _ArchitecturePlugin:
    def __init__(self):
        import asyncio
        from types import SimpleNamespace

        self.scheduler = SimpleNamespace()
        self.db = SimpleNamespace()
        self.ctx_service = SimpleNamespace()
        self.news_service = SimpleNamespace()
        self.image_service = SimpleNamespace()
        self.content_service = SimpleNamespace()
        self._lock = asyncio.Lock()
        self.basic_conf = {}
        self.extra_shares_conf = {}
        self.qzone_conf = {}
        self.image_conf = {}
        self.tts_conf = {}
        self.context_conf = {}
        self.receiver_conf = {}
        from daily_share_tasks_testpkg.core.container import PluginServices

        self.services = PluginServices(
            scheduler=self.scheduler,
            db=self.db,
            ctx_service=self.ctx_service,
            news_service=self.news_service,
            image_service=self.image_service,
            content_service=self.content_service,
            qzone_service=SimpleNamespace(),
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


if __name__ == "__main__":
    unittest.main()

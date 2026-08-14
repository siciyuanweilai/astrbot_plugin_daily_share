import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "daily_share_dashboard_run_testpkg"
CORE_PACKAGE_NAME = f"{PACKAGE_NAME}.core"
DASHBOARD_PACKAGE_NAME = f"{CORE_PACKAGE_NAME}.panel"
ROUTES_PACKAGE_NAME = f"{DASHBOARD_PACKAGE_NAME}.routes"
DATABASE_PACKAGE_NAME = f"{CORE_PACKAGE_NAME}.database"


class _Logger:
    def exception(self, *args, **kwargs):
        return None


def _install_stub_module(name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _clear_modules():
    for name in list(sys.modules):
        if name.startswith(PACKAGE_NAME) or name in {"astrbot", "astrbot.api"}:
            sys.modules.pop(name, None)


def _load_route_modules():
    _clear_modules()
    package = _install_stub_module(PACKAGE_NAME)
    package.__path__ = [str(ROOT)]
    core_package = _install_stub_module(CORE_PACKAGE_NAME)
    core_package.__path__ = [str(ROOT / "core")]
    dashboard_package = _install_stub_module(DASHBOARD_PACKAGE_NAME)
    dashboard_package.__path__ = [str(ROOT / "core" / "panel")]
    routes_package = _install_stub_module(ROUTES_PACKAGE_NAME)
    routes_package.__path__ = [str(ROOT / "core" / "panel" / "routes")]
    database_package = _install_stub_module(DATABASE_PACKAGE_NAME)
    database_package.__path__ = [str(ROOT / "core" / "database")]
    _install_stub_module("astrbot")
    _install_stub_module("astrbot.api", logger=_Logger())

    keys_name = f"{DATABASE_PACKAGE_NAME}.keys"
    keys_spec = importlib.util.spec_from_file_location(
        keys_name,
        ROOT / "core" / "database" / "keys.py",
    )
    keys_module = importlib.util.module_from_spec(keys_spec)
    sys.modules[keys_name] = keys_module
    assert keys_spec and keys_spec.loader
    keys_spec.loader.exec_module(keys_module)

    modules = {"keys": keys_module}
    for route_name in ("operation", "retry"):
        module_name = f"{ROUTES_PACKAGE_NAME}.{route_name}"
        spec = importlib.util.spec_from_file_location(
            module_name,
            ROOT / "core" / "panel" / "routes" / f"{route_name}.py",
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        assert spec and spec.loader
        spec.loader.exec_module(module)
        modules[route_name] = module
    return types.SimpleNamespace(**modules)


class _TaskManager:
    def __init__(
        self,
        groups=None,
        users=None,
        execute_result=True,
        qzone_result=True,
        briefing_result=True,
    ):
        self.groups = list(groups or [])
        self.users = list(users or [])
        self.execute_result = execute_result
        self.qzone_result = qzone_result
        self.briefing_result = briefing_result
        self.execute_calls = []
        self.share = self
        self.qzone_share = self
        self.briefing = self

    def resolve_execute_share_targets(
        self,
        specific_target=None,
        target_scope="all",
        *,
        exclude_custom_cron=True,
    ):
        if specific_target:
            return [specific_target]
        if target_scope == "groups":
            return self.groups
        if target_scope == "users":
            return self.users
        return [*self.groups, *self.users]

    async def execute_share(self, **kwargs):
        self.execute_calls.append(kwargs)
        return self.execute_result

    async def execute_qzone_share(self, **kwargs):
        self.execute_calls.append({"qzone": kwargs})
        return self.qzone_result

    async def execute_briefing_share(self, **kwargs):
        self.execute_calls.append({"briefing": kwargs})
        return self.briefing_result


class DashboardRunTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        modules = _load_route_modules()

        class Dashboard(
            modules.operation.DashboardRouteActionService,
            modules.retry.DashboardRouteRetryService,
        ):
            def __init__(self, body, task_manager):
                runtime = types.SimpleNamespace()
                super().__init__(runtime)
                for name in (
                    "action_routes",
                    "activity",
                    "labels",
                    "retry_routes",
                    "server",
                    "targets",
                    "validation",
                ):
                    setattr(runtime, name, self)
                self.body = body
                self.task_manager = task_manager
                self._lock = asyncio.Lock()
                self._page_action_runs = {}
                self._page_action_seq = 0
                self.tracked = []

            async def _page_json(self, callback, headers=None):
                try:
                    return await callback()
                except Exception as exc:
                    return {"ok": False, "error": {"message": str(exc)}}

            async def _page_json_body(self):
                return dict(self.body)

            def is_share_busy(self, global_scope=True):
                return False

            def _page_share_type(self, value):
                return value or "自动"

            def _page_news_source(self, value):
                return value or ""

            def _page_specific_share_target(self, target, target_id, adapter_id=""):
                raw = str(target_id or "").strip()
                if not raw or target not in {"broadcast_groups", "broadcast_users"}:
                    return "", ""
                kind = "group" if target == "broadcast_groups" else "user"
                message_type = "GroupMessage" if kind == "group" else "FriendMessage"
                parts = raw.split(":", 2)
                if len(parts) == 3 and parts[1] == message_type and all(parts):
                    return raw, kind
                if not adapter_id:
                    raise RuntimeError("检测到多个机器人实例，请选择要发送的机器人")
                return f"{adapter_id}:{message_type}:{raw}", kind

            async def _resolve_page_target_label(self, specific_target, specific_kind):
                return f"{specific_kind}:{specific_target}"

            def track_task(self, coro):
                self.tracked.append(coro)
                coro.close()

            def _page_prune_actions(self):
                return None

        self.Dashboard = Dashboard
        self.keys = modules.keys

    async def test_page_run_rejects_empty_group_target_before_creating_action(self):
        dashboard = self.Dashboard(
            {"target": "broadcast_groups", "specific_target": ""},
            _TaskManager(groups=[]),
        )

        result = await dashboard.page_run()

        self.assertFalse(result["ok"])
        self.assertIn("未找到可用群聊接收对象", result["error"]["message"])
        self.assertEqual(dashboard._page_action_runs, {})
        self.assertEqual(dashboard.tracked, [])

    async def test_page_run_allows_specific_group_without_configured_groups(self):
        dashboard = self.Dashboard(
            {
                "target": "broadcast_groups",
                "specific_target": "group-test-001",
                "specific_adapter_id": "bot-main",
            },
            _TaskManager(groups=[]),
        )

        result = await dashboard.page_run()

        self.assertTrue(result["ok"])
        run = result["data"]["run"]
        self.assertEqual(run["target_id"], "bot-main:GroupMessage:group-test-001")
        self.assertEqual(run["kind"], "group")
        self.assertEqual(len(dashboard.tracked), 1)

    async def test_page_run_rejects_unbound_specific_target(self):
        dashboard = self.Dashboard(
            {
                "target": "broadcast_groups",
                "specific_target": "group-test-001",
            },
            _TaskManager(groups=[]),
        )

        result = await dashboard.page_run()

        self.assertFalse(result["ok"])
        self.assertIn("选择要发送的机器人", result["error"]["message"])
        self.assertEqual(dashboard._page_action_runs, {})

    async def test_run_page_action_marks_failed_execute_share_as_error(self):
        manager = _TaskManager(
            groups=["aiocqhttp:GroupMessage:123"], execute_result=False
        )
        dashboard = self.Dashboard({"target": "broadcast_groups"}, manager)
        dashboard._page_action_runs["run-1"] = {
            "id": "run-1",
            "status": "running",
            "started_at": "",
        }

        await dashboard._run_page_action("run-1", "broadcast_groups", "自动", "")

        run = dashboard._page_action_runs["run-1"]
        self.assertEqual(run["status"], "error")
        self.assertEqual(run["message"], "分享失败，请查看日志")

    async def test_run_page_action_marks_failed_briefing_as_error(self):
        manager = _TaskManager(briefing_result=False)
        dashboard = self.Dashboard({"target": "briefing"}, manager)
        dashboard._page_action_runs["run-1"] = {
            "id": "run-1",
            "status": "running",
            "started_at": "",
        }

        await dashboard._run_page_action("run-1", "briefing", "自动", "")

        run = dashboard._page_action_runs["run-1"]
        self.assertEqual(run["status"], "error")
        self.assertEqual(run["message"], "早报分享失败，请查看日志")

    async def test_run_page_retry_action_marks_failed_global_retry_as_error(self):
        manager = _TaskManager(execute_result=False)
        dashboard = self.Dashboard({}, manager)
        dashboard._page_action_runs["retry-1"] = {
            "id": "retry-1",
            "status": "running",
            "started_at": "",
        }

        await dashboard._run_page_retry_action(
            "retry-1",
            {"target_id": self.keys.GLOBAL_TARGET_ID, "type": "心情"},
        )

        run = dashboard._page_action_runs["retry-1"]
        self.assertEqual(run["status"], "error")
        self.assertEqual(run["message"], "重试失败，请查看日志")

    async def test_run_page_retry_action_marks_failed_briefing_retry_as_error(self):
        manager = _TaskManager(briefing_result=False)
        dashboard = self.Dashboard({}, manager)
        dashboard._page_action_runs["retry-1"] = {
            "id": "retry-1",
            "status": "running",
            "started_at": "",
        }

        await dashboard._run_page_retry_action(
            "retry-1",
            {"target_id": self.keys.BRIEFING_TARGET_ID, "type": "早报"},
        )

        run = dashboard._page_action_runs["retry-1"]
        self.assertEqual(run["status"], "error")
        self.assertEqual(run["message"], "早报重试失败，请查看日志")


if __name__ == "__main__":
    unittest.main()

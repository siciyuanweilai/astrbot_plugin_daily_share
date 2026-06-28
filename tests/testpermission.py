import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PERMISSION_MODULE_PATH = ROOT / "core" / "host" / "permission.py"
TOOLS_MODULE_PATH = ROOT / "core" / "host" / "tools.py"
TOOLS_PACKAGE_NAME = "daily_share_permission_tool_testpkg"
TOOLS_CORE_PACKAGE_NAME = f"{TOOLS_PACKAGE_NAME}.core"
TOOLS_HOST_PACKAGE_NAME = f"{TOOLS_CORE_PACKAGE_NAME}.host"
TOOLS_DATABASE_PACKAGE_NAME = f"{TOOLS_CORE_PACKAGE_NAME}.database"
TOOLS_KEYS_MODULE_NAME = f"{TOOLS_DATABASE_PACKAGE_NAME}.keys"
TOOLS_MODULE_NAME = f"{TOOLS_HOST_PACKAGE_NAME}.tools"


class _Logger:
    def debug(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None


def _install_stub_module(name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _install_astrbot_stub():
    event_module = _install_stub_module("astrbot.api.event")
    event_module.AstrMessageEvent = object
    api_module = _install_stub_module("astrbot.api", logger=_Logger())
    api_module.event = event_module
    _install_stub_module("astrbot", api=api_module)


def _load_module(module_name: str, module_path: Path):
    _install_astrbot_stub()
    return _exec_module(module_name, module_path)


def _exec_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_tools_module():
    _install_astrbot_stub()
    for name in [
        TOOLS_PACKAGE_NAME,
        TOOLS_CORE_PACKAGE_NAME,
        TOOLS_HOST_PACKAGE_NAME,
        TOOLS_DATABASE_PACKAGE_NAME,
    ]:
        module = _install_stub_module(name)
        module.__path__ = []
    _exec_module(TOOLS_KEYS_MODULE_NAME, ROOT / "core" / "database" / "keys.py")
    return _exec_module(TOOLS_MODULE_NAME, TOOLS_MODULE_PATH)


class _Event:
    def __init__(self, *, role="member", is_admin_error=False):
        self.role = role
        self.is_admin_error = is_admin_error
        self.unified_msg_origin = "aiocqhttp:FriendMessage:10001"
        self.extras = {}

    def is_admin(self):
        if self.is_admin_error:
            raise RuntimeError("boom")
        return self.role == "admin"

    def set_extra(self, key, value):
        self.extras[key] = value


class _AgentContext:
    def __init__(self, event):
        self.event = event


class _ContextWrapper:
    def __init__(self, event):
        self.context = _AgentContext(event)


class PermissionTests(unittest.TestCase):
    def setUp(self):
        module = _load_module("permission_test", PERMISSION_MODULE_PATH)

        class PermissionHost(module.PluginPermissionMixin):
            pass

        self.host = PermissionHost()

    def test_respects_astrbot_event_admin_role(self):
        event = _Event(role="admin")

        self.assertTrue(self.host._is_admin_event(event))

    def test_rejects_member_role(self):
        event = _Event(role="member")

        self.assertFalse(self.host._is_admin_event(event))

    def test_uses_role_when_is_admin_method_fails(self):
        event = _Event(role="admin", is_admin_error=True)

        self.assertTrue(self.host._is_admin_event(event))

    def test_resolves_event_from_tool_context_wrapper(self):
        event = _Event(role="admin")
        wrapper = _ContextWrapper(event)

        self.assertIs(self.host._resolve_message_event(wrapper), event)
        self.assertTrue(self.host._is_admin_event(wrapper))


class _TaskManager:
    def __init__(self):
        self.calls = []

    async def get_cached_news_link(self, target_uid, **kwargs):
        self.calls.append((target_uid, kwargs))
        return "第5条链接：https://example.com/news"


class NewsLinkToolPermissionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        permission_module = _load_module("permission_test_for_tool", PERMISSION_MODULE_PATH)
        tools_module = _load_tools_module()

        class ToolHost(tools_module.PluginToolMixin, permission_module.PluginPermissionMixin):
            _is_terminated = False

            def __init__(self):
                self.task_manager = _TaskManager()

            def _resolve_news_source_name(self, source):
                return source

            def _extract_news_link_urls(self, result):
                return ["https://example.com/news"] if "https://" in result else []

            def _is_configured_receiver_event(self, event):
                return False

            def _remember_event_adapter(self, event):
                return None

        self.host = ToolHost()

    async def test_member_can_query_current_session_news_link(self):
        result = await self.host._news_link_tool_impl(_Event(role="member"), index="5")

        self.assertIn("https://example.com/news", result)
        self.assertEqual(self.host.task_manager.calls[0][0], "aiocqhttp:FriendMessage:10001")

    async def test_news_link_ignores_source_without_explicit_flag(self):
        await self.host._news_link_tool_impl(_Event(role="member"), index="2", source="zhihu")

        self.assertIsNone(self.host.task_manager.calls[0][1]["source_key"])

    async def test_news_link_uses_source_with_explicit_flag(self):
        await self.host._news_link_tool_impl(
            _Event(role="member"),
            index="2",
            source="zhihu",
            source_explicit=True,
        )

        self.assertEqual(self.host.task_manager.calls[0][1]["source_key"], "zhihu")

    async def test_news_link_accepts_tool_context_wrapper(self):
        result = await self.host._news_link_tool_impl(_ContextWrapper(_Event(role="member")), index="6")

        self.assertIn("https://example.com/news", result)
        self.assertEqual(self.host.task_manager.calls[0][0], "aiocqhttp:FriendMessage:10001")

    async def test_member_cannot_query_qzone_news_link(self):
        result = await self.host._news_link_tool_impl(_Event(role="member"), to_qzone=True)

        self.assertEqual(result, "QQ空间新闻链接仅管理员可查询。")
        self.assertEqual(self.host.task_manager.calls, [])


if __name__ == "__main__":
    unittest.main()

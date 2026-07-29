import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "daily_share_panel_server_testpkg"
PANEL_PACKAGE_NAME = f"{PACKAGE_NAME}.core.panel"


class _Logger:
    def exception(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None


class _Response:
    def __init__(self, payload):
        self.payload = payload
        self.status_code = 200
        self.headers = {}


def _load_server_module():
    for name in list(sys.modules):
        if name.startswith(PACKAGE_NAME) or name in {"astrbot", "astrbot.api"}:
            sys.modules.pop(name, None)

    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(ROOT)]
    sys.modules[PACKAGE_NAME] = package

    core_package = types.ModuleType(f"{PACKAGE_NAME}.core")
    core_package.__path__ = [str(ROOT / "core")]
    sys.modules[core_package.__name__] = core_package

    panel_package = types.ModuleType(PANEL_PACKAGE_NAME)
    panel_package.__path__ = [str(ROOT / "core" / "panel")]
    sys.modules[PANEL_PACKAGE_NAME] = panel_package

    common_module = types.ModuleType(f"{PANEL_PACKAGE_NAME}.common")
    common_module._PAGE_MEDIA_CACHE_SECONDS = 60
    common_module._PAGE_PREFERENCES_DEFAULTS = {"sakura_enabled": True}
    common_module._quart_jsonify = _Response
    common_module._quart_request = None
    sys.modules[common_module.__name__] = common_module

    astrbot_module = types.ModuleType("astrbot")
    astrbot_api_module = types.ModuleType("astrbot.api")
    astrbot_api_module.logger = _Logger()
    sys.modules["astrbot"] = astrbot_module
    sys.modules["astrbot.api"] = astrbot_api_module

    module_name = f"{PANEL_PACKAGE_NAME}.server"
    spec = importlib.util.spec_from_file_location(
        module_name,
        ROOT / "core" / "panel" / "server.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class PanelServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.module = _load_server_module()
        runtime = types.SimpleNamespace()
        self.service = self.module.DashboardBaseService(runtime)
        runtime.server = self.service

    async def test_page_json_returns_200_for_success(self):
        async def callback():
            return {"ok": True}

        response = await self.service._page_json(callback)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload, {"ok": True})

    async def test_page_json_returns_422_for_business_exception(self):
        async def callback():
            raise RuntimeError("测试异常")

        response = await self.service._page_json(callback)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.payload["error"]["message"], "测试异常")

    async def test_page_json_keeps_500_for_unknown_exception(self):
        async def callback():
            raise AttributeError("内部属性异常")

        response = await self.service._page_json(callback)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.payload["error"]["message"], "内部属性异常")

    async def test_page_json_maps_expected_request_errors(self):
        cases = (
            (ValueError("参数错误"), 400),
            (PermissionError("没有权限"), 403),
            (FileNotFoundError("记录不存在"), 404),
            (BlockingIOError("任务忙碌"), 409),
        )
        for error, expected_status in cases:

            async def callback(error=error):
                raise error

            with self.subTest(error=type(error).__name__):
                response = await self.service._page_json(callback)
                self.assertEqual(response.status_code, expected_status)


if __name__ == "__main__":
    unittest.main()

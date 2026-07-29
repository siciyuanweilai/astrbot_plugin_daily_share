import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "daily_share_content_testpkg"
CORE_PACKAGE_NAME = f"{PACKAGE_NAME}.core"
CONFIG_MODULE_NAME = f"{CORE_PACKAGE_NAME}.config"
CONTENT_MODULE_NAME = f"{CORE_PACKAGE_NAME}.content"


class _Logger:
    def debug(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None


class _Db:
    def __init__(self):
        self.recorded = []

    async def get_used_topics(self, target_id, category, days_limit=60):
        return []

    async def record_topic(self, target_id, category, keyword):
        self.recorded.append((target_id, category, keyword))


class _NewsService:
    async def get_baike_info(self, keyword):
        return f"{keyword} 的百科资料"


class _EmptyNewsService:
    async def get_baike_info(self, keyword):
        return ""


def _clear_modules():
    for name in list(sys.modules):
        if name.startswith(PACKAGE_NAME) or name in {
            "astrbot",
            "astrbot.api",
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
    package_locations = [str(path.parent)] if path.name == "__init__.py" else None
    spec = importlib.util.spec_from_file_location(
        name, path, submodule_search_locations=package_locations
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _load_content_module():
    _clear_modules()

    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(ROOT)]
    sys.modules[PACKAGE_NAME] = package

    core_package = types.ModuleType(CORE_PACKAGE_NAME)
    core_package.__path__ = [str(ROOT / "core")]
    sys.modules[CORE_PACKAGE_NAME] = core_package

    _install_stub_module("astrbot")
    _install_stub_module("astrbot.api", logger=_Logger())
    _install_stub_module("aiofiles")
    _install_stub_module("aiohttp")

    _load_module(CONFIG_MODULE_NAME, ROOT / "core" / "config.py")
    return _load_module(CONTENT_MODULE_NAME, ROOT / "core" / "content" / "__init__.py")


def _ctx():
    return {
        "target_id": "test_target",
        "system_prompt": "测试系统提示",
        "is_group": False,
        "nickname": "",
        "detect_name": "",
        "persona": "测试人格",
        "period_label": "下午",
        "date_str": "2026年05月31日",
        "time_str": "15:00",
        "life_hint": "",
        "structured_history_hint": "",
        "recent_dynamics": "",
    }


def _config(**content_library):
    return {
        "content_library": {
            "knowledge_cats": ["科学小发现: 蜂蜜"],
            "rec_cats": ["好物: 电脑"],
            **content_library,
        },
        "news_conf": {"enable_web_search": False},
        "basic_conf": {"data_retention_days": 60},
        "context_conf": {},
    }


def _service(response: str, news_service=None, **content_library):
    content_module = _load_content_module()
    calls = []

    async def call_llm(prompt, system_prompt="", **kwargs):
        calls.append({"prompt": prompt, "system_prompt": system_prompt})
        return response

    service = content_module.ContentService(
        _config(**content_library),
        call_llm,
        context=None,
        db_manager=_Db(),
        news_service=news_service or _NewsService(),
    )
    service.llm_calls = calls

    async def brainstorm(category_type, sub_category, target_id):
        return "电脑" if category_type == "好物" else "蜂蜜"

    service.topic._agent_brainstorm_topic = brainstorm
    return service


class ContentPrefixSwitchesTests(unittest.IsolatedAsyncioTestCase):
    async def test_news_uses_daily_life_search_only_for_missing_summary(self):
        service = _service("测试输出")
        service.news_conf["enable_web_search"] = True
        calls = []

        class Bridge:
            async def search_evidence(self, query, **kwargs):
                calls.append((query, kwargs))
                return {"status": "ok", "content": "联网证据"}

        service.daily_life_bridge = Bridge()
        result = await service.news._collect_news_backgrounds(
            [
                {
                    "title": "有摘要",
                    "description": "这是来自新闻接口且足够长的真实摘要内容。",
                },
                {"title": "无摘要", "description": ""},
            ],
            source_name="测试热搜",
            enable_web_search=True,
            target_umo="bot-test:GroupMessage:group-test-a",
        )

        self.assertEqual(result[0][1], "这是来自新闻接口且足够长的真实摘要内容。")
        self.assertEqual(result[1][1], "联网证据")
        self.assertEqual(
            calls,
            [
                (
                    "无摘要",
                    {
                        "category": "news",
                        "target_umo": "bot-test:GroupMessage:group-test-a",
                    },
                )
            ],
        )

    async def test_reference_keeps_baike_when_daily_life_search_is_unavailable(self):
        service = _service("测试输出")
        service.news_conf["enable_web_search"] = True

        class Bridge:
            async def search_evidence(self, query, **kwargs):
                return {"status": "unavailable", "content": ""}

        service.daily_life_bridge = Bridge()
        result = await service.recommendation._fetch_content_reference(
            "测试主题",
            search_kind="knowledge",
            target_umo="bot-test:FriendMessage:user-test-a",
            heading="参考资料",
            baike_label="百科",
            web_label="联网",
        )

        self.assertIn("百科：测试主题 的百科资料", result)
        self.assertNotIn("联网：", result)

    def test_default_content_library_survives_missing_schema_defaults(self):
        content_module = _load_content_module()

        async def call_llm(prompt, system_prompt="", **kwargs):
            return ""

        service = content_module.ContentService(
            {"news_conf": {}, "basic_conf": {}, "context_conf": {}},
            call_llm,
            context=None,
            db_manager=_Db(),
            news_service=_NewsService(),
        )

        self.assertTrue(service.knowledge_cats)
        self.assertTrue(service.rec_cats)
        self.assertIn("有趣的冷知识", service.knowledge_cats)
        self.assertIn("书籍", service.rec_cats)

    async def test_knowledge_prefix_is_enabled_by_default(self):
        service = _service("【蜂蜜】不会轻易变质。$$happy$$")

        text = await service.knowledge._gen_knowledge(_ctx())

        self.assertTrue(text.startswith("知识类型: 科学小发现 - 蜂蜜\n\n"))

    async def test_knowledge_prefix_can_be_hidden(self):
        service = _service(
            "【蜂蜜】不会轻易变质。$$happy$$",
            show_knowledge_type_prefix=False,
        )

        text = await service.knowledge._gen_knowledge(_ctx())

        self.assertEqual(text, "【蜂蜜】不会轻易变质。$$happy$$")

    async def test_recommendation_prefix_is_enabled_by_default(self):
        service = _service("推荐【电脑】作为效率工具。$$happy$$")

        text = await service.recommendation._gen_rec(_ctx())

        self.assertTrue(text.startswith("推荐类型: 好物 - 电脑\n\n"))

    async def test_recommendation_prefix_can_be_hidden(self):
        service = _service(
            "推荐【电脑】作为效率工具。$$happy$$",
            show_rec_type_prefix=False,
        )

        text = await service.recommendation._gen_rec(_ctx())

        self.assertEqual(text, "推荐【电脑】作为效率工具。$$happy$$")

    async def test_knowledge_without_external_material_cancels(self):
        service = _service(
            "【蜂蜜】不会轻易变质。$$happy$$", news_service=_EmptyNewsService()
        )

        text = await service.knowledge._gen_knowledge(_ctx())

        self.assertIsNone(text)
        self.assertEqual(service.llm_calls, [])

    async def test_recommendation_without_external_material_cancels(self):
        service = _service(
            "推荐【电脑】作为效率工具。$$happy$$", news_service=_EmptyNewsService()
        )

        text = await service.recommendation._gen_rec(_ctx())

        self.assertIsNone(text)
        self.assertEqual(service.llm_calls, [])


if __name__ == "__main__":
    unittest.main()

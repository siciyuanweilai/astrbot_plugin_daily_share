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
    async def test_all_qzone_content_types_use_life_expression_without_legacy_templates(
        self,
    ):
        service = _service("【自然段落】公开动态正文。")
        service.qzone_conf["qzone_share_output_format"] = "旧说说格式"
        service.basic_conf["share_output_format"] = "普通分享格式"
        config_module = sys.modules[CONFIG_MODULE_NAME]
        style_calls = []

        class Bridge:
            async def get_share_chat_style_prompt(self, *, scene=""):
                style_calls.append(scene)
                return "【daily_life 聊天表达参考】自然分段，按内容展开。"

            async def search_evidence(self, query, **kwargs):
                return {"status": "unavailable", "content": ""}

        service.daily_life_bridge = Bridge()
        for stype in config_module.ShareType:
            for period in (
                config_module.TimePeriod.MORNING,
                config_module.TimePeriod.LATE_NIGHT,
            ):
                with self.subTest(stype=stype, period=period):
                    result = await service.generate(
                        stype,
                        period,
                        "qzone_broadcast",
                        False,
                        "真实生活状态",
                        news_data=(
                            [
                                {
                                    "title": "真实新闻",
                                    "description": "资料中的事实来自接口提供且长度足够的真实新闻摘要。",
                                }
                            ],
                            "zhihu",
                        ),
                        recent_dynamics="以前的长篇文艺说说不要再作为示例",
                        recent_post_contents=["另一条已发的动态"],
                    )
                    self.assertEqual(result, "【自然段落】公开动态正文。")
                    prompt = service.llm_calls[-1]["prompt"]
                    self.assertIn("自然分段，按内容展开。", prompt)
                    self.assertIn("真实生活状态", prompt)
                    self.assertIn("隐私边界", prompt)
                    self.assertIn("事实边界", prompt)
                    self.assertIn("随手发一条", prompt)
                    self.assertNotRegex(prompt, r"\d+-\d+字")
                    for value in (
                        "旧说说格式",
                        "普通分享格式",
                        "用【】",
                        "开头必须",
                        "文案开头必须",
                        "必须在正文最后",
                        "【深夜表达规则】",
                        "私聊可以详细展开",
                        "类型:",
                        "随想",
                        "小感悟",
                        "可感知的情绪、画面",
                        "基于当前真实时间感悟",
                        "以前的长篇文艺说说不要再作为示例",
                        "另一条已发的动态",
                    ):
                        self.assertNotIn(value, prompt)
                    if stype == config_module.ShareType.NEWS:
                        self.assertIn("资料中的事实", prompt)
                    if stype == config_module.ShareType.KNOWLEDGE:
                        self.assertIn("蜂蜜 的百科资料", prompt)
                    if stype == config_module.ShareType.RECOMMENDATION:
                        self.assertIn("电脑 的百科资料", prompt)
        self.assertEqual(style_calls, ["qzone_post"] * 10)
        self.assertEqual(
            service.db.recorded,
            [("qzone_broadcast", "knowledge", "蜂蜜")] * 2
            + [("qzone_broadcast", "rec", "电脑")] * 2,
        )

    async def test_qzone_post_repeat_check_does_not_send_history_or_retry_the_model(
        self,
    ):
        service = _service("糖水喝完了。\n又打包了双皮奶。")
        config_module = sys.modules[CONFIG_MODULE_NAME]
        result = await service.generate(
            config_module.ShareType.MOOD,
            config_module.TimePeriod.AFTERNOON,
            "qzone_broadcast",
            False,
            "当前在往回走",
            recent_post_contents=["糖水喝完了。\n\n又打包了双皮奶。"],
        )
        self.assertIsNone(result)
        self.assertEqual(len(service.llm_calls), 1)
        self.assertNotIn("又打包了双皮奶", service.llm_calls[0]["prompt"])
        service.qzone_conf["qzone_follow_life_chat_style"] = False
        self.assertIsNone(
            await service.generate(
                config_module.ShareType.MOOD,
                config_module.TimePeriod.AFTERNOON,
                "qzone_broadcast",
                False,
                "当前在往回走",
                recent_post_contents=["糖水喝完了。\n又打包了双皮奶。"],
            )
        )
        self.assertEqual(len(service.llm_calls), 2)
        self.assertEqual(
            await service.generate(
                config_module.ShareType.MOOD,
                config_module.TimePeriod.AFTERNOON,
                "private-target",
                False,
                "当前在往回走",
                recent_post_contents=["糖水喝完了。\n又打包了双皮奶。"],
            ),
            "糖水喝完了。\n又打包了双皮奶。",
        )

    async def test_removed_qzone_switch_does_not_restore_legacy_type_templates(self):
        service = _service("【蜂蜜】正文")
        service.qzone_conf["qzone_follow_life_chat_style"] = False
        service.qzone_conf["qzone_share_output_format"] = "保存的旧说说格式"
        service.basic_conf["share_output_format"] = "普通分享格式"
        config_module = sys.modules[CONFIG_MODULE_NAME]
        for stype, marker in (
            (config_module.ShareType.GREETING, "文案开头必须"),
            (config_module.ShareType.MOOD, "100-120字"),
            (config_module.ShareType.NEWS, "用【】标注热搜标题"),
            (config_module.ShareType.KNOWLEDGE, "用【】将核心关键词"),
            (config_module.ShareType.RECOMMENDATION, "务必用【】将推荐目标"),
        ):
            with self.subTest(stype=stype):
                result = await service.generate(
                    stype,
                    config_module.TimePeriod.MORNING,
                    "qzone_broadcast",
                    False,
                    "",
                    news_data=([{"title": "新闻"}], "zhihu"),
                )
                prompt = service.llm_calls[-1]["prompt"]
                self.assertNotIn("保存的旧说说格式", prompt)
                self.assertNotIn("普通分享格式", prompt)
                self.assertNotIn(marker, prompt)
                self.assertNotRegex(prompt, r"\d+-\d+字")
                self.assertIn("【本次 QQ 空间状态】", prompt)
                self.assertIn("【QQ 空间说说表达】", prompt)
                self.assertEqual(result, "【蜂蜜】正文")

    async def test_other_targets_keep_all_type_templates_and_formats(self):
        service = _service("【蜂蜜】正文")
        service.basic_conf["share_output_format"] = "普通分享格式"
        config_module = sys.modules[CONFIG_MODULE_NAME]
        for target, is_group in (
            ("private-target", False),
            ("group-target", True),
        ):
            for stype, marker in (
                (config_module.ShareType.GREETING, "文案开头必须"),
                (config_module.ShareType.MOOD, "你的随想"),
                (config_module.ShareType.NEWS, "用【】标注热搜标题"),
                (config_module.ShareType.KNOWLEDGE, "用【】将核心关键词"),
                (config_module.ShareType.RECOMMENDATION, "务必用【】将推荐目标"),
            ):
                with self.subTest(target=target, stype=stype):
                    result = await service.generate(
                        stype,
                        config_module.TimePeriod.MORNING,
                        target,
                        is_group,
                        "",
                        news_data=([{"title": "新闻"}], "zhihu"),
                    )
                    prompt = service.llm_calls[-1]["prompt"]
                    self.assertIn(marker, prompt)
                    self.assertRegex(prompt, r"\d+-\d+字")
                    self.assertIn("普通分享格式", prompt)
                    self.assertNotIn("【本次 QQ 空间状态】", prompt)
                    if stype == config_module.ShareType.KNOWLEDGE:
                        self.assertTrue(result.startswith("知识类型:"))
                    if stype == config_module.ShareType.RECOMMENDATION:
                        self.assertTrue(result.startswith("推荐类型:"))

    async def test_news_uses_daily_life_search_only_for_missing_summary(self):
        service = _service("测试输出")
        service.news_conf["enable_web_search"] = False
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
        service.news_conf["enable_web_search"] = False

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

    async def test_news_search_failure_statuses_do_not_fabricate_background(self):
        service = _service("测试输出")
        for status in ("disabled", "unavailable", "error", "empty"):
            calls = []

            class Bridge:
                async def search_evidence(self, query, **kwargs):
                    calls.append(query)
                    return {"status": status, "content": "失败响应的正文不能作为证据"}

            service.daily_life_bridge = Bridge()
            result = await service.news._collect_news_backgrounds(
                [{"title": "无摘要"}], source_name="测试", target_umo="target"
            )
            self.assertEqual(calls, ["无摘要"])
            self.assertEqual(result, [("无摘要", "")])

    async def test_news_complete_api_summaries_do_not_call_search(self):
        service = _service("测试输出")

        class Bridge:
            async def search_evidence(self, *args, **kwargs):
                raise AssertionError("摘要足够时不应申请检索")

        service.daily_life_bridge = Bridge()
        result = await service.news._collect_news_backgrounds(
            [
                {
                    "title": "有摘要",
                    "description": "这是来自新闻接口且足够长的真实摘要内容。",
                }
            ],
            source_name="测试",
            target_umo="target",
        )
        self.assertEqual(result[0][1], "这是来自新闻接口且足够长的真实摘要内容。")

    async def test_reference_ignores_legacy_search_switch_and_keeps_life_evidence(self):
        service = _service("测试输出")
        service.news_conf["enable_web_search"] = False
        calls = []

        class Bridge:
            async def search_evidence(self, query, **kwargs):
                calls.append((query, kwargs))
                return {"status": "ok", "content": "有效联网证据"}

        service.daily_life_bridge = Bridge()
        result = await service.recommendation._fetch_content_reference(
            "测试主题",
            search_kind="recommendation",
            target_umo="target",
            heading="参考资料",
            baike_label="百科",
            web_label="联网",
        )
        self.assertEqual(
            calls,
            [("测试主题", {"category": "recommendation", "target_umo": "target"})],
        )
        self.assertIn("百科：测试主题 的百科资料", result)
        self.assertIn("联网：有效联网证据", result)

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

    async def test_empty_knowledge_categories_cancel_without_index_error(self):
        service = _service("测试输出")
        service.knowledge_cats = {}

        self.assertIsNone(await service.knowledge._gen_knowledge(_ctx()))

    async def test_empty_recommendation_categories_cancel_without_index_error(self):
        service = _service("测试输出")
        service.rec_cats = {"好物": []}

        self.assertIsNone(await service.recommendation._gen_rec(_ctx()))

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

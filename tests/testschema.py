import json
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_config_module():
    spec = importlib.util.spec_from_file_location("daily_share_schema_config", ROOT / "core" / "config.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _load_constants_module(config_module):
    import sys
    import types

    package_name = "daily_share_schema_pkg"
    core_package_name = f"{package_name}.core"
    config_module_name = f"{core_package_name}.config"
    constants_module_name = f"{core_package_name}.constants"

    for name in (constants_module_name, config_module_name, core_package_name, package_name):
        sys.modules.pop(name, None)

    package = types.ModuleType(package_name)
    package.__path__ = [str(ROOT)]
    sys.modules[package_name] = package

    core_package = types.ModuleType(core_package_name)
    core_package.__path__ = [str(ROOT / "core")]
    sys.modules[core_package_name] = core_package
    sys.modules[config_module_name] = config_module

    spec = importlib.util.spec_from_file_location(constants_module_name, ROOT / "core" / "constants.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[constants_module_name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _load_dashboard_validation_module(config_module):
    import sys
    import types

    package_name = "daily_share_schema_pkg"
    core_package_name = f"{package_name}.core"
    dashboard_package_name = f"{core_package_name}.dashboard"
    config_module_name = f"{core_package_name}.config"
    constants_module_name = f"{core_package_name}.constants"
    common_module_name = f"{dashboard_package_name}.common"
    validation_module_name = f"{dashboard_package_name}.validation"

    for name in (
        validation_module_name,
        common_module_name,
        dashboard_package_name,
        constants_module_name,
        config_module_name,
        core_package_name,
        package_name,
    ):
        sys.modules.pop(name, None)

    package = types.ModuleType(package_name)
    package.__path__ = [str(ROOT)]
    sys.modules[package_name] = package

    core_package = types.ModuleType(core_package_name)
    core_package.__path__ = [str(ROOT / "core")]
    sys.modules[core_package_name] = core_package
    sys.modules[config_module_name] = config_module

    dashboard_package = types.ModuleType(dashboard_package_name)
    dashboard_package.__path__ = [str(ROOT / "core" / "dashboard")]
    sys.modules[dashboard_package_name] = dashboard_package

    if "astrbot.api" not in sys.modules:
        astrbot = types.ModuleType("astrbot")
        astrbot_api = types.ModuleType("astrbot.api")
        astrbot_api.logger = type("_Logger", (), {"__getattr__": lambda self, name: (lambda *args, **kwargs: None)})()
        astrbot.api = astrbot_api
        sys.modules["astrbot"] = astrbot
        sys.modules["astrbot.api"] = astrbot_api

    constants = _load_constants_module(config_module)
    sys.modules[constants_module_name] = constants

    common_spec = importlib.util.spec_from_file_location(common_module_name, ROOT / "core" / "dashboard" / "common.py")
    common = importlib.util.module_from_spec(common_spec)
    sys.modules[common_module_name] = common
    assert common_spec and common_spec.loader
    common_spec.loader.exec_module(common)

    spec = importlib.util.spec_from_file_location(validation_module_name, ROOT / "core" / "dashboard" / "validation.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[validation_module_name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ConfigSchemaTests(unittest.TestCase):
    def test_weixin_image_size_config_exists(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        image_items = schema["image_conf"]["items"]

        self.assertIn("weixin_image_max_size_kb", image_items)

    def test_news_image_cleanup_config_exists(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        image_items = schema["image_conf"]["items"]

        self.assertIn("news_image_cleanup_max_count", image_items)
        self.assertEqual(image_items["news_image_cleanup_max_count"]["default"], 200)

    def test_dashboard_dynamic_days_config_exists(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        basic_items = schema["basic_conf"]["items"]

        self.assertIn("dashboard_dynamic_days", basic_items)
        self.assertEqual(basic_items["dashboard_dynamic_days"]["default"], 60)

    def test_schedule_modes_use_current_qzone_auto_interaction_fields(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        basic_items = schema["basic_conf"]["items"]
        briefing_items = schema["extra_shares"]["items"]
        qzone_items = schema["qzone_conf"]["items"]

        for items, mode_key in (
            (basic_items, "trigger_mode"),
            (briefing_items, "briefing_schedule_mode"),
            (qzone_items, "qzone_trigger_mode"),
        ):
            with self.subTest(mode_key=mode_key):
                self.assertNotIn("interval", items[mode_key]["options"])

        self.assertNotIn("interval_minutes", basic_items)
        self.assertNotIn("briefing_interval_minutes", briefing_items)
        self.assertNotIn("qzone_interval_minutes", qzone_items)
        self.assertNotIn("qzone_auto_comment_schedule_mode", qzone_items)
        self.assertNotIn("qzone_auto_reply_schedule_mode", qzone_items)
        self.assertIn("qzone_enable_auto_interaction", qzone_items)
        self.assertIn("qzone_enable_auto_like", qzone_items)
        self.assertIn("qzone_auto_like_limit", qzone_items)
        self.assertIn("qzone_auto_interaction_interval_minutes", qzone_items)
        self.assertIn("qzone_auto_interaction_cron", qzone_items)
        self.assertEqual(qzone_items["qzone_auto_interaction_interval_minutes"]["default"], 45)
        self.assertEqual(qzone_items["qzone_auto_interaction_rate_limit_policy"]["default"], "record_only")
        self.assertEqual(qzone_items["qzone_auto_interaction_rate_limit_cooldown_seconds"]["default"], 600)

    def test_qzone_api_timeout_config_exists(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        qzone_items = schema["qzone_conf"]["items"]

        self.assertIn("qzone_api_timeout_seconds", qzone_items)
        self.assertEqual(qzone_items["qzone_api_timeout_seconds"]["default"], 120)
        self.assertEqual(qzone_items["qzone_api_timeout_seconds"]["slider"]["max"], 300)

    def test_qzone_video_config_exists(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        qzone_items = schema["qzone_conf"]["items"]

        self.assertIn("qzone_enable_video", qzone_items)
        self.assertIn("qzone_video_enabled_types", qzone_items)
        self.assertFalse(qzone_items["qzone_enable_video"]["default"])
        self.assertEqual(qzone_items["qzone_video_enabled_types"]["default"], ["问候", "心情"])

    def test_media_uses_daily_life_without_tool_config(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        image_items = schema["image_conf"]["items"]
        tts_items = schema["tts_conf"]["items"]

        self.assertNotIn("image_tool_name", image_items)
        self.assertNotIn("video_tool_name", image_items)
        self.assertNotIn("tts_tool_name", tts_items)
        self.assertNotIn("use_gitee_selfie_ref", image_items)
        self.assertIn("astrbot_plugin_daily_life", image_items["enable_ai_image"]["hint"])
        self.assertIn("astrbot_plugin_daily_life", image_items["enable_ai_video"]["hint"])
        self.assertIn("astrbot_plugin_daily_life", tts_items["enable_tts"]["hint"])

    def test_news_source_options_follow_runtime_map(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        news_items = schema["news_conf"]["items"]
        config = _load_config_module()
        expected = set(config.NEWS_SOURCE_MAP)

        self.assertIn("kuaishou", expected)
        self.assertEqual(set(news_items["news_api_source"]["options"]), expected)
        self.assertEqual(set(news_items["news_random_sources"]["items"]["options"]), expected)

        for period, prefs in config.NEWS_TIME_PREFERENCES.items():
            with self.subTest(period=period.value):
                self.assertEqual(set(prefs), expected)

    def test_dashboard_random_news_sources_accept_chinese_names(self):
        config = _load_config_module()
        validation = _load_dashboard_validation_module(config)
        validator = validation.DashboardConfigValidationMixin()

        result = validator._page_news_source_list_value(["知乎", "微博热搜", "bili", "知乎热搜"], "随机新闻源")

        self.assertEqual(result, ["zhihu", "weibo", "bili"])

    def test_log_labels_use_chinese_period_and_type(self):
        config = _load_config_module()
        constants = _load_constants_module(config)

        self.assertEqual(constants.period_label(config.TimePeriod.LATE_NIGHT), "深夜")
        self.assertEqual(constants.share_type_label(config.ShareType.MOOD), "心情")

if __name__ == "__main__":
    unittest.main()

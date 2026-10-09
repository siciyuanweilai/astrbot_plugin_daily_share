import importlib.util
import json
import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def _bind_panel_test_component(component):
    component.runtime.payload = component
    component.runtime.meta = component
    component.runtime.validation = component
    return component


def _load_config_module():
    spec = importlib.util.spec_from_file_location(
        "daily_share_schema_config", ROOT / "core" / "config.py"
    )
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

    for name in (
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

    spec = importlib.util.spec_from_file_location(
        constants_module_name, ROOT / "core" / "constants.py"
    )
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
    dashboard_package_name = f"{core_package_name}.panel"
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
    dashboard_package.__path__ = [str(ROOT / "core" / "panel")]
    sys.modules[dashboard_package_name] = dashboard_package

    if "astrbot.api" not in sys.modules:
        astrbot = types.ModuleType("astrbot")
        astrbot_api = types.ModuleType("astrbot.api")
        astrbot_api.logger = type(
            "_Logger",
            (),
            {"__getattr__": lambda self, name: lambda *args, **kwargs: None},
        )()
        astrbot.api = astrbot_api
        sys.modules["astrbot"] = astrbot
        sys.modules["astrbot.api"] = astrbot_api
    if not callable(getattr(sys.modules["astrbot.api"].logger, "debug", None)):
        sys.modules["astrbot.api"].logger = type(
            "_Logger",
            (),
            {"__getattr__": lambda self, name: lambda *args, **kwargs: None},
        )()

    constants = _load_constants_module(config_module)
    sys.modules[constants_module_name] = constants

    common_spec = importlib.util.spec_from_file_location(
        common_module_name, ROOT / "core" / "panel" / "common.py"
    )
    common = importlib.util.module_from_spec(common_spec)
    sys.modules[common_module_name] = common
    assert common_spec and common_spec.loader
    common_spec.loader.exec_module(common)

    spec = importlib.util.spec_from_file_location(
        validation_module_name, ROOT / "core" / "panel" / "validation.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[validation_module_name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _load_dashboard_config_modules(config_module):
    import sys
    import types

    package_name = "daily_share_schema_pkg"
    core_package_name = f"{package_name}.core"
    dashboard_package_name = f"{core_package_name}.panel"
    apply_package_name = f"{dashboard_package_name}.apply"
    config_module_name = f"{core_package_name}.config"

    for name in list(sys.modules):
        if name.startswith(package_name):
            sys.modules.pop(name, None)

    package = types.ModuleType(package_name)
    package.__path__ = [str(ROOT)]
    sys.modules[package_name] = package

    core_package = types.ModuleType(core_package_name)
    core_package.__path__ = [str(ROOT / "core")]
    sys.modules[core_package_name] = core_package
    sys.modules[config_module_name] = config_module

    dashboard_package = types.ModuleType(dashboard_package_name)
    dashboard_package.__path__ = [str(ROOT / "core" / "panel")]
    sys.modules[dashboard_package_name] = dashboard_package

    apply_package = types.ModuleType(apply_package_name)
    apply_package.__path__ = [str(ROOT / "core" / "panel" / "apply")]
    sys.modules[apply_package_name] = apply_package

    if "astrbot.api" not in sys.modules:
        astrbot = types.ModuleType("astrbot")
        astrbot_api = types.ModuleType("astrbot.api")
        astrbot_api.logger = type(
            "_Logger",
            (),
            {"__getattr__": lambda self, name: lambda *args, **kwargs: None},
        )()
        astrbot.api = astrbot_api
        sys.modules["astrbot"] = astrbot
        sys.modules["astrbot.api"] = astrbot_api
    if not callable(getattr(sys.modules["astrbot.api"].logger, "debug", None)):
        sys.modules["astrbot.api"].logger = type(
            "_Logger",
            (),
            {"__getattr__": lambda self, name: lambda *args, **kwargs: None},
        )()

    modules = {}
    for module_name, path in (
        (f"{dashboard_package_name}.common", ROOT / "core" / "panel" / "common.py"),
        (
            f"{dashboard_package_name}.validation",
            ROOT / "core" / "panel" / "validation.py",
        ),
        (f"{dashboard_package_name}.meta", ROOT / "core" / "panel" / "meta.py"),
        (f"{dashboard_package_name}.payload", ROOT / "core" / "panel" / "payload.py"),
        (f"{apply_package_name}.field", ROOT / "core" / "panel" / "apply" / "field.py"),
        (
            f"{apply_package_name}.section",
            ROOT / "core" / "panel" / "apply" / "section.py",
        ),
        (
            f"{apply_package_name}.zonectl",
            ROOT / "core" / "panel" / "apply" / "zonectl.py",
        ),
        (
            f"{apply_package_name}.submission",
            ROOT / "core" / "panel" / "apply" / "submission.py",
        ),
    ):
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        assert spec and spec.loader
        spec.loader.exec_module(module)
        modules[module_name.rsplit(".", 1)[-1]] = module

    return modules


class ConfigSchemaTests(unittest.TestCase):
    def test_model_config_is_in_basic_group_without_persona_overrides(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        basic_items = schema["basic_conf"]["items"]

        self.assertNotIn("llm_conf", schema)
        self.assertEqual(basic_items["llm_provider_id"]["_special"], "select_provider")
        self.assertEqual(basic_items["llm_timeout"]["default"], 120)
        self.assertNotIn("use_persona", basic_items)
        self.assertNotIn("persona_id", basic_items)

    def test_weixin_image_size_config_exists(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        image_items = schema["image_conf"]["items"]

        self.assertIn("weixin_image_max_size_kb", image_items)

    def test_news_image_cleanup_config_exists(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        image_items = schema["image_conf"]["items"]

        self.assertIn("news_image_cleanup_max_count", image_items)
        self.assertEqual(image_items["news_image_cleanup_max_count"]["default"], 200)

    def test_onebot_api_timeout_config_is_not_exposed(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        self.assertNotIn("onebot_api_timeout_seconds", schema["context_conf"]["items"])

    def test_news_image_download_limit_config_is_removed(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        news_items = schema["news_conf"]["items"]

        self.assertNotIn("news_image_max_size_mb", news_items)

    def test_dashboard_dynamic_days_config_exists(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        basic_items = schema["basic_conf"]["items"]

        self.assertIn("dashboard_dynamic_days", basic_items)
        self.assertEqual(basic_items["dashboard_dynamic_days"]["default"], 60)

    def test_non_qzone_output_format_configs_remain(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        basic_items = schema["basic_conf"]["items"]
        qzone_items = schema["qzone_conf"]["items"]

        self.assertIn("share_output_format", basic_items)
        self.assertNotIn("qzone_share_output_format", qzone_items)
        self.assertEqual(basic_items["share_output_format"]["type"], "text")
        self.assertEqual(basic_items["share_output_format"]["default"], "")
        self.assertIn("不影响 QQ 空间说说", basic_items["share_output_format"]["hint"])
        self.assertNotIn("xiaohongshu_conf", schema)

    def test_qzone_life_chat_style_switch_and_legacy_prompts_are_removed(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        items = schema["qzone_conf"]["items"]
        for key in (
            "qzone_follow_life_chat_style",
            "qzone_share_output_format",
            "qzone_auto_comment_prompt",
            "qzone_auto_reply_prompt",
        ):
            self.assertNotIn(key, items)
        html = (ROOT / "pages/dashboard/index.html").read_text(encoding="utf-8")
        mapping = (ROOT / "pages/dashboard/ui/schemamap.js").read_text(encoding="utf-8")
        elements = (ROOT / "pages/dashboard/ui/elements.js").read_text(encoding="utf-8")
        prefs = (ROOT / "pages/dashboard/ui/prefs.js").read_text(encoding="utf-8")
        for element_id in (
            "cfgQzoneLifeChatStyle",
            "cfgQzoneShareOutputFormat",
            "cfgQzoneAutoCommentPrompt",
            "cfgQzoneAutoReplyPrompt",
        ):
            for source in (html, mapping, elements, prefs):
                self.assertNotIn(element_id, source)

    def test_dashboard_qzone_settings_do_not_submit_removed_style_controls(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("未安装 Node.js，跳过设置页交互验证")
        script = textwrap.dedent(
            """
            import assert from 'node:assert/strict';
            import { createSettingsConfig } from './pages/dashboard/ui/prefs.js';
            import {
                settingsSchemaBindings, settingsPayloadGroups, writeBoundSchemaFields,
            } from './pages/dashboard/ui/schema.js';

            globalThis.document = { getElementById: () => null };
            globalThis.window = { clearTimeout: () => {}, setTimeout: () => 1 };
            globalThis.HTMLSelectElement = class {};
            globalThis.HTMLInputElement = class {};
            const noop = () => {};
            const state = { configChangeSeq: 0 };
            const elements = {
                cfgQzoneImage: { type: 'checkbox', checked: false },
                configForm: { querySelector: () => null, querySelectorAll: () => [] },
            };
            const data = {
                sections: {},
                schema_values: { sections: { qzone_conf: {
                    qzone_share_output_format: '保存的旧格式',
                    qzone_follow_life_chat_style: true,
                    qzone_enable_image: true,
                } } },
            };
            const settings = createSettingsConfig({
                state, elements, bridge: true, apiGet: async () => data,
                setNotice: noop, syncSettingSlider: noop, syncSweetSelect: noop,
                syncSweetSelects: noop, applySettingsSchemaEnhancements: noop,
            });
            assert.equal(await settings.loadConfig({ quiet: true }), true);
            const toggle = elements.cfgQzoneImage;
            assert.equal(toggle.checked, true);
            for (const id of ['cfgQzoneShareOutputFormat', 'cfgQzoneLifeChatStyle']) {
                assert.equal(id in settingsSchemaBindings(), false);
                assert.equal(settingsPayloadGroups.qzone.includes(id), false);
            }

            for (const enabled of [false, true, false]) {
                toggle.checked = enabled;
                settings.handleConfigChanged({ type: 'change', target: toggle });
                const payload = { sections: {}, schema_extra: { root: {}, sections: {} } };
                writeBoundSchemaFields(payload, 'qzone', settingsPayloadGroups.qzone,
                    { configData: data, elements });
                assert.equal('qzone_share_output_format' in payload.sections.qzone, false);
                assert.equal('qzone_follow_life_chat_style' in payload.sections.qzone, false);
                assert.equal(payload.sections.qzone.qzone_enable_image, enabled);
            }
            assert.equal(state.configChangeSeq, 3);
            """
        )
        result = subprocess.run(
            [node, "--input-type=module", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_redundant_life_switches_removed_without_removing_privacy_or_media_controls(
        self,
    ):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        for section, key in (
            ("context_conf", "enable_life_context"),
            ("context_conf", "life_context_in_group"),
            ("news_conf", "enable_web_search"),
        ):
            self.assertNotIn(key, schema[section]["items"])
        for key in (
            "group_share_schedule",
            "enable_chat_history",
            "record_share_to_memory",
        ):
            self.assertIn(key, schema["context_conf"]["items"])
        self.assertIn("enable_ai_image", schema["image_conf"]["items"])
        self.assertIn("qzone_enable_auto_interaction", schema["qzone_conf"]["items"])
        for path in (
            "pages/dashboard/index.html",
            "pages/dashboard/ui/elements.js",
            "pages/dashboard/ui/schemamap.js",
            "pages/dashboard/ui/prefs.js",
        ):
            source = (ROOT / path).read_text(encoding="utf-8")
            for element_id in (
                "cfgLifeContext",
                "cfgLifeContextGroup",
                "cfgNewsWebSearch",
            ):
                self.assertNotIn(element_id, source)

    def test_dashboard_life_sections_ignore_legacy_switch_submissions(self):
        modules = _load_dashboard_config_modules(_load_config_module())

        class Plugin(
            modules["section"].DashboardApplySectionService,
            modules["field"].DashboardApplyFieldService,
            modules["validation"].DashboardConfigValidationService,
        ):
            pass

        runtime = SimpleNamespace(config={})
        plugin = Plugin(runtime)
        runtime.fields = plugin
        runtime.validation = plugin
        for enabled in (False, True):
            plugin._page_apply_context_section(
                {
                    "context": {
                        "enable_life_context": enabled,
                        "life_context_in_group": enabled,
                        "group_share_schedule": enabled,
                    }
                }
            )
            plugin._page_apply_news_section(
                {
                    "news": {
                        "enable_web_search": enabled,
                        "enable_news_api": enabled,
                    }
                }
            )
            self.assertEqual(
                plugin.config["context_conf"], {"group_share_schedule": enabled}
            )
            self.assertEqual(plugin.config["news_conf"], {"enable_news_api": enabled})

    def test_dashboard_life_settings_do_not_submit_legacy_fields(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("未安装 Node.js，跳过设置页交互验证")
        script = textwrap.dedent(
            """
            import assert from 'node:assert/strict';
            import { settingsSchemaBindings, settingsPayloadGroups, writeBoundSchemaFields }
                from './pages/dashboard/ui/schema.js';
            globalThis.document = { getElementById: () => null };
            const data = { schema_values: { sections: {
                context_conf: { enable_life_context: false, life_context_in_group: false },
                news_conf: { enable_web_search: false },
            } } };
            const elements = {
                cfgGroupSchedule: { type: 'checkbox', checked: true },
                cfgNewsApiEnabled: { type: 'checkbox', checked: true },
            };
            for (const [group, ids] of [
                ['context', ['cfgLifeContext', 'cfgLifeContextGroup']],
                ['news', ['cfgNewsWebSearch']],
            ]) {
                for (const id of ids) {
                    assert.equal(id in settingsSchemaBindings(), false);
                    assert.equal(settingsPayloadGroups[group].includes(id), false);
                }
                const payload = { sections: {}, schema_extra: { root: {}, sections: {} } };
                writeBoundSchemaFields(payload, group, settingsPayloadGroups[group],
                    { configData: data, elements });
                for (const key of ['enable_life_context', 'life_context_in_group', 'enable_web_search']) {
                    assert.equal(key in payload.sections[group], false);
                }
                assert.equal(payload.sections[group][group === 'context' ? 'group_share_schedule' : 'enable_news_api'], true);
            }
            """
        )
        result = subprocess.run(
            [node, "--input-type=module", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_dashboard_qzone_apply_ignores_removed_switch_and_prompt_payloads(self):
        modules = _load_dashboard_config_modules(_load_config_module())

        class Plugin(
            modules["zonectl"].DashboardApplyQzoneService,
            modules["field"].DashboardApplyFieldService,
            modules["validation"].DashboardConfigValidationService,
        ):
            pass

        runtime = SimpleNamespace(config={"qzone_conf": {}})
        plugin = Plugin(runtime)
        runtime.fields = plugin
        runtime.qzone_apply = plugin
        runtime.validation = plugin
        runtime.schedule_apply = SimpleNamespace(
            _page_apply_schedule_fields=lambda *args: None
        )
        for enabled in (True, False):
            plugin._page_apply_qzone_section(
                {
                    "qzone": {
                        "qzone_follow_life_chat_style": enabled,
                        "qzone_share_output_format": "旧页面提交的说说格式",
                        "qzone_auto_comment_prompt": "旧页面提交的评论风格",
                        "qzone_auto_reply_prompt": "旧页面提交的回评风格",
                    }
                }
            )
            self.assertEqual(plugin.config["qzone_conf"], {})

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
        self.assertIn("qzone_auto_interaction_active_hours", qzone_items)
        self.assertIn("qzone_enable_auto_like", qzone_items)
        self.assertIn("qzone_auto_like_limit", qzone_items)
        self.assertIn("qzone_auto_interaction_cron", qzone_items)
        self.assertEqual(
            qzone_items["qzone_auto_interaction_active_hours"]["default"], 24
        )
        self.assertEqual(
            qzone_items["qzone_auto_interaction_active_hours"]["slider"]["min"], 0
        )
        self.assertEqual(
            qzone_items["qzone_auto_interaction_active_hours"]["slider"]["max"], 168
        )
        self.assertNotIn("qzone_auto_interaction_interval_minutes", qzone_items)
        self.assertNotIn("qzone_auto_interaction_rate_limit_policy", qzone_items)
        self.assertNotIn(
            "qzone_auto_interaction_rate_limit_cooldown_seconds", qzone_items
        )

    def test_qzone_api_timeout_config_exists(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        qzone_items = schema["qzone_conf"]["items"]

        self.assertIn("qzone_api_timeout_seconds", qzone_items)
        self.assertEqual(qzone_items["qzone_api_timeout_seconds"]["default"], 120)
        self.assertEqual(qzone_items["qzone_api_timeout_seconds"]["slider"]["max"], 300)

    def test_qzone_random_delay_config_is_independent(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        qzone_items = schema["qzone_conf"]["items"]

        delay = qzone_items["qzone_cron_random_delay"]
        self.assertEqual(delay["default"], 0)
        self.assertEqual(delay["slider"]["min"], 0)
        self.assertEqual(delay["slider"]["max"], 60)

    def test_qzone_adapter_config_exists(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        qzone_items = schema["qzone_conf"]["items"]

        self.assertIn("qzone_adapter_id", qzone_items)
        self.assertEqual(qzone_items["qzone_adapter_id"]["default"], "")
        self.assertEqual(qzone_items["qzone_adapter_id"]["_special"], "select_adapter")

    def test_qzone_video_config_removed(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        qzone_items = schema["qzone_conf"]["items"]

        self.assertNotIn("qzone_enable_video", qzone_items)
        self.assertNotIn("qzone_video_enabled_types", qzone_items)

    def test_qzone_auto_comment_image_vision_config_exists(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        qzone_items = schema["qzone_conf"]["items"]

        self.assertIn("qzone_enable_auto_comment_image_vision", qzone_items)
        self.assertIn("qzone_auto_comment_image_vision_limit", qzone_items)
        self.assertIn("qzone_auto_comment_image_vision_provider", qzone_items)
        self.assertFalse(
            qzone_items["qzone_enable_auto_comment_image_vision"]["default"]
        )
        self.assertEqual(
            qzone_items["qzone_auto_comment_image_vision_limit"]["default"], 1
        )
        self.assertEqual(
            qzone_items["qzone_auto_comment_image_vision_limit"]["slider"]["max"], 9
        )

    def test_dashboard_payload_exposes_schema_values_for_extra_fields(self):
        config = _load_config_module()
        modules = _load_dashboard_config_modules(config)

        class Plugin(
            modules["payload"].DashboardConfigPayloadService,
            modules["meta"].DashboardConfigMetaService,
            modules["validation"].DashboardConfigValidationService,
        ):
            pass

        plugin = _bind_panel_test_component(Plugin(SimpleNamespace()))
        plugin.config = {
            "basic_conf": {
                "share_output_format": "使用两行短句。",
            },
            "qzone_conf": {
                "qzone_enable_auto_comment_image_vision": True,
                "qzone_auto_interaction_active_hours": 12,
                "qzone_share_output_format": "像说说一样分行。",
                "qzone_follow_life_chat_style": True,
                "qzone_auto_comment_prompt": "残留评论风格",
                "qzone_auto_reply_prompt": "残留回评风格",
            },
            "context_conf": {
                "enable_life_context": False,
                "life_context_in_group": False,
            },
            "news_conf": {"enable_web_search": False},
        }
        plugin.context = type("_Context", (), {"get_config": lambda self: {}})()
        plugin._page_config_schema_raw_cache = modules[
            "meta"
        ].DashboardConfigMetaService._read_page_config_schema_sync()
        plugin._page_config_schema_raw_version = None
        plugin._page_config_schema_meta_cache = None
        plugin._page_config_schema_meta_version = None
        plugin._page_category_lines = modules[
            "validation"
        ].DashboardConfigValidationService._page_category_lines

        payload = plugin._page_config_payload()
        for section, group, keys in (
            (
                "context_conf",
                "context",
                ("enable_life_context", "life_context_in_group"),
            ),
            ("news_conf", "news", ("enable_web_search",)),
        ):
            for values in (
                payload["schema_values"]["sections"][section],
                payload["schema_meta"]["sections"][section]["fields"],
                payload["sections"][group],
            ):
                for key in keys:
                    self.assertNotIn(key, values)
        basic_values = payload["schema_values"]["sections"]["basic_conf"]
        qzone_values = payload["schema_values"]["sections"]["qzone_conf"]
        qzone_meta = payload["schema_meta"]["sections"]["qzone_conf"]["fields"]

        self.assertEqual(basic_values["share_output_format"], "使用两行短句。")
        self.assertTrue(qzone_values["qzone_enable_auto_comment_image_vision"])
        self.assertEqual(qzone_values["qzone_auto_interaction_active_hours"], 12)
        for key in (
            "qzone_follow_life_chat_style",
            "qzone_share_output_format",
            "qzone_auto_comment_prompt",
            "qzone_auto_reply_prompt",
        ):
            for values in (qzone_values, qzone_meta, payload["sections"]["qzone"]):
                self.assertNotIn(key, values)
        self.assertNotIn("qzone_auto_interaction_rate_limit_policy", qzone_values)
        self.assertNotIn(
            "qzone_auto_interaction_rate_limit_cooldown_seconds", qzone_values
        )
        self.assertEqual(
            qzone_meta["qzone_auto_comment_image_vision_provider"]["_special"],
            "select_provider",
        )

    def test_dashboard_payload_exposes_adapter_options(self):
        config = _load_config_module()
        modules = _load_dashboard_config_modules(config)

        class Meta:
            def __init__(self, adapter_id, name):
                self.id = adapter_id
                self.name = name
                self.support_proactive_message = True

        class Platform:
            def __init__(self, adapter_id, name):
                self._meta = Meta(adapter_id, name)

            def meta(self):
                return self._meta

        class PlatformManager:
            def get_insts(self):
                return [Platform("V", "aiocqhttp"), Platform("Swan", "napcat")]

        class Plugin(
            modules["payload"].DashboardConfigPayloadService,
            modules["meta"].DashboardConfigMetaService,
            modules["validation"].DashboardConfigValidationService,
        ):
            pass

        plugin = _bind_panel_test_component(Plugin(SimpleNamespace()))
        plugin.config = {"qzone_conf": {"qzone_adapter_id": "Swan"}}
        plugin.context = type(
            "_Context",
            (),
            {
                "get_config": lambda self: {},
                "platform_manager": PlatformManager(),
            },
        )()
        plugin._page_config_schema_raw_cache = modules[
            "meta"
        ].DashboardConfigMetaService._read_page_config_schema_sync()
        plugin._page_config_schema_raw_version = None
        plugin._page_config_schema_meta_cache = None
        plugin._page_config_schema_meta_version = None
        plugin._page_category_lines = modules[
            "validation"
        ].DashboardConfigValidationService._page_category_lines

        payload = plugin._page_config_payload()
        adapter_values = [item["value"] for item in payload["options"]["adapters"]]
        adapter_meta = payload["schema_meta"]["sections"]["qzone_conf"]["fields"][
            "qzone_adapter_id"
        ]

        self.assertEqual(
            payload["schema_values"]["sections"]["qzone_conf"]["qzone_adapter_id"],
            "Swan",
        )
        self.assertEqual(adapter_values, ["", "V", "Swan"])
        self.assertEqual(adapter_meta["_special"], "select_adapter")
        self.assertEqual(adapter_meta["options"][0]["label"], "自动选择唯一实例")

    def test_dashboard_payload_distinguishes_same_id_across_platforms(self):
        config = _load_config_module()
        modules = _load_dashboard_config_modules(config)

        class Meta:
            def __init__(self, adapter_id, name):
                self.id = adapter_id
                self.name = name
                self.support_proactive_message = True

        class Platform:
            def __init__(self, name):
                self._meta = Meta("duplicate-id", name)

            def meta(self):
                return self._meta

        class Plugin(
            modules["payload"].DashboardConfigPayloadService,
            modules["meta"].DashboardConfigMetaService,
            modules["validation"].DashboardConfigValidationService,
        ):
            pass

        plugin = _bind_panel_test_component(Plugin(SimpleNamespace()))
        plugin.config = {"qzone_conf": {}}
        plugin.context = type(
            "_Context",
            (),
            {
                "get_config": lambda self: {},
                "platform_manager": type(
                    "_Manager",
                    (),
                    {
                        "get_insts": lambda self: [
                            Platform("aiocqhttp"),
                            Platform("webchat"),
                        ]
                    },
                )(),
            },
        )()

        options = plugin._page_adapter_options()
        self.assertEqual(len(options), 3)
        self.assertEqual(
            [item["value"] for item in options[1:]],
            ["aiocqhttp!duplicate-id", "webchat!duplicate-id"],
        )
        self.assertTrue(all(not item.get("conflicted") for item in options[1:]))
        self.assertNotIn("实例 ID 冲突", options[1]["label"])

    def test_dashboard_payload_marks_same_platform_duplicate_as_conflict(self):
        config = _load_config_module()
        modules = _load_dashboard_config_modules(config)

        class Meta:
            id = "duplicate-id"
            name = "aiocqhttp"
            support_proactive_message = True

        class Platform:
            def meta(self):
                return Meta()

        class Plugin(
            modules["payload"].DashboardConfigPayloadService,
            modules["meta"].DashboardConfigMetaService,
            modules["validation"].DashboardConfigValidationService,
        ):
            pass

        plugin = _bind_panel_test_component(Plugin(SimpleNamespace()))
        plugin.config = {"qzone_conf": {}}
        plugin.context = type(
            "_Context",
            (),
            {
                "get_config": lambda self: {},
                "platform_manager": type(
                    "_Manager",
                    (),
                    {"get_insts": lambda self: [Platform(), Platform()]},
                )(),
            },
        )()

        options = plugin._page_adapter_options()
        self.assertTrue(all(item.get("conflicted") for item in options[1:]))
        self.assertIn("实例 ID 冲突", options[1]["label"])

    def test_dashboard_payload_labels_non_conflicted_webchat_instance(self):
        config = _load_config_module()
        modules = _load_dashboard_config_modules(config)

        class Meta:
            id = "webchat-main"
            name = "webchat"
            support_proactive_message = True

        class Platform:
            def meta(self):
                return Meta()

        class Plugin(
            modules["payload"].DashboardConfigPayloadService,
            modules["meta"].DashboardConfigMetaService,
            modules["validation"].DashboardConfigValidationService,
        ):
            pass

        plugin = _bind_panel_test_component(Plugin(SimpleNamespace()))
        plugin.config = {"qzone_conf": {}}
        plugin.context = type(
            "_Context",
            (),
            {
                "get_config": lambda self: {},
                "platform_manager": type(
                    "_Manager",
                    (),
                    {"get_insts": lambda self: [Platform()]},
                )(),
            },
        )()

        options = plugin._page_adapter_options()

        self.assertEqual(options[1]["value"], "webchat-main")
        self.assertEqual(options[1]["label"], "网页聊天 · webchat-main")
        self.assertFalse(options[1]["conflicted"])

    def test_dashboard_schema_extra_updates_uncovered_fields(self):
        config = _load_config_module()
        modules = _load_dashboard_config_modules(config)

        class Plugin(
            modules["submission"].DashboardApplyPayloadService,
            modules["field"].DashboardApplyFieldService,
            modules["meta"].DashboardConfigMetaService,
            modules["validation"].DashboardConfigValidationService,
        ):
            def _page_apply_target_section(self, sections):
                return None

            def _page_apply_basic_section(self, sections):
                return None

            def _page_apply_briefing_section(self, sections):
                return None

            def _page_apply_qzone_section(self, sections):
                return None

            def _page_apply_content_section(self, sections):
                return None

            def _page_apply_media_section(self, sections):
                return None

            def _page_apply_context_section(self, sections):
                return None

            def _page_apply_news_section(self, sections):
                return None

            def _page_apply_llm_section(self, sections):
                return None

        runtime = SimpleNamespace()
        plugin = Plugin(runtime)
        runtime.general_apply = plugin
        runtime.qzone_apply = plugin
        runtime.sections = plugin
        runtime.fields = plugin
        runtime.meta = plugin
        runtime.validation = plugin
        runtime.config = {"qzone_conf": {}}
        runtime.contact_aliases = []
        runtime._page_config_schema_raw_cache = modules[
            "meta"
        ].DashboardConfigMetaService._read_page_config_schema_sync()
        runtime._page_config_schema_meta_cache = None
        plugin._apply_page_config_payload(
            {
                "schema_extra": {
                    "sections": {
                        "basic_conf": {
                            "share_output_format": "第一句写状态，第二句写感受。",
                        },
                        "qzone_conf": {
                            "qzone_cron_random_delay": 999,
                            "qzone_enable_auto_comment_image_vision": True,
                            "qzone_auto_comment_image_vision_limit": 9,
                            "qzone_auto_interaction_active_hours": 999,
                            "qzone_share_output_format": "像 QQ 空间说说一样自然分行。",
                            "qzone_follow_life_chat_style": True,
                            "qzone_auto_comment_prompt": "旧页面提交的评论风格",
                            "qzone_auto_reply_prompt": "旧页面提交的回评风格",
                        },
                    }
                }
            }
        )

        basic = plugin.config["basic_conf"]
        qzone = plugin.config["qzone_conf"]
        self.assertEqual(basic["share_output_format"], "第一句写状态，第二句写感受。")
        self.assertEqual(qzone["qzone_cron_random_delay"], 60)
        self.assertTrue(qzone["qzone_enable_auto_comment_image_vision"])
        self.assertNotIn("qzone_follow_life_chat_style", qzone)
        self.assertNotIn("qzone_auto_comment_prompt", qzone)
        self.assertNotIn("qzone_auto_reply_prompt", qzone)
        self.assertEqual(qzone["qzone_auto_comment_image_vision_limit"], 9)
        self.assertEqual(qzone["qzone_auto_interaction_active_hours"], 168)
        self.assertNotIn("qzone_share_output_format", qzone)
        self.assertNotIn("qzone_auto_interaction_rate_limit_policy", qzone)
        self.assertNotIn("qzone_auto_interaction_rate_limit_cooldown_seconds", qzone)

    def test_dashboard_schema_extra_keeps_contact_alias_validation(self):
        config = _load_config_module()
        modules = _load_dashboard_config_modules(config)

        class Plugin(
            modules["submission"].DashboardApplyPayloadService,
            modules["field"].DashboardApplyFieldService,
            modules["meta"].DashboardConfigMetaService,
            modules["validation"].DashboardConfigValidationService,
        ):
            def _page_apply_target_section(self, sections):
                return None

            def _page_apply_basic_section(self, sections):
                return None

            def _page_apply_briefing_section(self, sections):
                return None

            def _page_apply_qzone_section(self, sections):
                return None

            def _page_apply_content_section(self, sections):
                return None

            def _page_apply_media_section(self, sections):
                return None

            def _page_apply_context_section(self, sections):
                return None

            def _page_apply_news_section(self, sections):
                return None

            def _page_apply_llm_section(self, sections):
                return None

        runtime = SimpleNamespace()
        plugin = Plugin(runtime)
        runtime.general_apply = plugin
        runtime.qzone_apply = plugin
        runtime.sections = plugin
        runtime.fields = plugin
        runtime.meta = plugin
        runtime.validation = plugin
        runtime.config = {}
        runtime.contact_aliases = []
        runtime._page_config_schema_raw_cache = modules[
            "meta"
        ].DashboardConfigMetaService._read_page_config_schema_sync()
        runtime._page_config_schema_meta_cache = None
        plugin._apply_page_config_payload(
            {
                "schema_extra": {
                    "root": {
                        "contact_aliases": ["10001:测试用户甲"],
                    }
                }
            }
        )

        self.assertEqual(plugin.config["contact_aliases"], ["10001:测试用户甲"])
        self.assertEqual(plugin.contact_aliases, ["10001:测试用户甲"])
        with self.assertRaises(RuntimeError):
            plugin._apply_page_config_payload(
                {"schema_extra": {"root": {"contact_aliases": ["bad-format"]}}}
            )

    def test_media_uses_daily_life_without_tool_config(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        image_items = schema["image_conf"]["items"]
        tts_items = schema["tts_conf"]["items"]

        self.assertNotIn("image_tool_name", image_items)
        self.assertNotIn("video_tool_name", image_items)
        self.assertNotIn("tts_tool_name", tts_items)
        self.assertNotIn("use_gitee_selfie_ref", image_items)
        self.assertNotIn("daily_life_image_model", image_items)
        self.assertNotIn("appearance_prompt", image_items)
        for key in (
            "daily_life_text_image_model",
            "daily_life_edit_image_model",
        ):
            self.assertNotIn(key, image_items)
        self.assertIn("第一个可用生图通道", image_items["enable_ai_image"]["hint"])
        self.assertIn(
            "astrbot_plugin_daily_life", image_items["enable_ai_image"]["hint"]
        )
        self.assertIn(
            "astrbot_plugin_daily_life", image_items["enable_ai_video"]["hint"]
        )
        self.assertIn("astrbot_plugin_daily_life", tts_items["enable_tts"]["hint"])

    def test_news_source_options_follow_runtime_map(self):
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        news_items = schema["news_conf"]["items"]
        config = _load_config_module()
        expected = set(config.NEWS_SOURCE_MAP)

        self.assertIn("kuaishou", expected)
        self.assertEqual(set(news_items["news_api_source"]["options"]), expected)
        self.assertEqual(
            set(news_items["news_random_sources"]["items"]["options"]), expected
        )

        for period, prefs in config.NEWS_TIME_PREFERENCES.items():
            with self.subTest(period=period.value):
                self.assertEqual(set(prefs), expected)

    def test_dashboard_random_news_sources_accept_chinese_names(self):
        config = _load_config_module()
        validation = _load_dashboard_validation_module(config)
        validator = _bind_panel_test_component(
            validation.DashboardConfigValidationService(SimpleNamespace())
        )

        result = validator._page_news_source_list_value(
            ["知乎", "微博热搜", "bili", "知乎热搜"], "随机新闻源"
        )

        self.assertEqual(result, ["zhihu", "weibo", "bili"])

    def test_log_labels_use_chinese_period_and_type(self):
        config = _load_config_module()
        constants = _load_constants_module(config)

        self.assertEqual(constants.period_label(config.TimePeriod.LATE_NIGHT), "深夜")
        self.assertEqual(constants.share_type_label(config.ShareType.MOOD), "心情")


if __name__ == "__main__":
    unittest.main()

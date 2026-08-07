import asyncio
import subprocess
import sys
import textwrap
import types
import unittest
from pathlib import Path
from unittest.mock import patch

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from astrbot_plugin_daily_share.core.integrations import (  # noqa: E402
    dailylife as dailylife_module,
)

DailyLifeBridge = dailylife_module.DailyLifeBridge


class _Logger:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


class _Runtime:
    def __init__(self, label: str):
        self.label = label
        self.context_targets = []
        self.activities = []
        self.searches = []

    async def get_life_context(self, target_umo: str = ""):
        self.context_targets.append(target_umo)
        return {"schedule": self.label, "target": target_umo}

    async def record_external_activity(self, target_umo, content, **kwargs):
        self.activities.append((target_umo, content, kwargs))
        return True

    async def search_share_evidence(self, query, **kwargs):
        self.searches.append((query, kwargs))
        return {
            "status": "ok",
            "query": query,
            "content": f"{query} 的联网证据",
            "sources": [],
        }


class _PublicPlugin:
    def __init__(self, label: str):
        self.runtime = _Runtime(label)

    async def get_life_context(self, target_umo=""):
        return await self.runtime.get_life_context(target_umo)

    async def record_external_activity(self, target_umo, content, **kwargs):
        return await self.runtime.record_external_activity(
            target_umo, content, **kwargs
        )

    async def search_share_evidence(self, query, **kwargs):
        return await self.runtime.search_share_evidence(query, **kwargs)

    async def generate_share_image(self, event, prompt, *, contains_character=False):
        return f"image:{prompt}:{contains_character}"

    async def generate_share_video(self, event, prompt, *, reference_image=""):
        return f"video:{prompt}:{reference_image}"

    async def generate_share_voice(self, text, *, emotion="", emotion_category=""):
        return f"voice:{text}:{emotion}:{emotion_category}"


def _life_plugin(label: str) -> _PublicPlugin:
    return _PublicPlugin(label)


def _metadata(plugin, *, activated=True, plugin_id="astrbot_plugin_daily_life"):
    return types.SimpleNamespace(
        name=plugin_id,
        root_dir_name=plugin_id,
        activated=activated,
        star_cls=plugin,
    )


class DailyLifeBridgeIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.logger_patcher = patch.object(dailylife_module, "logger", _Logger())
        self.logger_patcher.start()

    def tearDown(self):
        self.logger_patcher.stop()

    def test_bridge_calls_real_daily_life_plugin_entry_in_isolated_runtime(self):
        script = textwrap.dedent(
            f"""
            import asyncio
            import importlib.util
            import sys
            import types

            sys.path.insert(0, {str(WORKSPACE / "astrbot_plugin_daily_life" / "tests")!r})
            import support
            sys.path.insert(0, {str(WORKSPACE)!r})

            from astrbot_plugin_daily_life.main import DailyLifePlugin

            package = types.ModuleType('daily_share_contract')
            package.__path__ = [{str(WORKSPACE / "astrbot_plugin_daily_share")!r}]
            sys.modules['daily_share_contract'] = package
            core_package = types.ModuleType('daily_share_contract.core')
            core_package.__path__ = [{str(WORKSPACE / "astrbot_plugin_daily_share" / "core")!r}]
            sys.modules['daily_share_contract.core'] = core_package
            integrations_package = types.ModuleType('daily_share_contract.core.integrations')
            integrations_package.__path__ = [{str(WORKSPACE / "astrbot_plugin_daily_share" / "core" / "integrations")!r}]
            sys.modules['daily_share_contract.core.integrations'] = integrations_package
            spec = importlib.util.spec_from_file_location(
                'daily_share_contract.core.integrations.dailylife',
                {str(WORKSPACE / "astrbot_plugin_daily_share" / "core" / "integrations" / "dailylife.py")!r},
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            DailyLifeBridge = module.DailyLifeBridge

            class Runtime:
                async def get_life_context(self, target_umo=''):
                    return {{'target': target_umo}}

                async def record_external_activity(self, target_umo, content, **kwargs):
                    return target_umo.endswith('user-test-a') and content == '测试分享内容'

                class Search:
                    async def search_external_evidence(self, query, **kwargs):
                        return {{
                            'status': 'ok',
                            'query': query,
                            'content': '跨插件搜索证据',
                            'sources': [],
                            'category': kwargs['category'],
                        }}

                search = Search()

                class Voice:
                    async def synthesize(self, text, **kwargs):
                        return types.SimpleNamespace(path=f'voice://{{text}}')

                media = types.SimpleNamespace(voice=Voice())

                async def generate_life_image_asset(self, event, prompt, *args, **kwargs):
                    return types.SimpleNamespace(path=f'image://{{prompt}}')

                async def generate_life_video_asset(self, event, prompt, reference_image=''):
                    return types.SimpleNamespace(url=f'video://{{prompt}}')

            async def run():
                plugin = DailyLifePlugin(types.SimpleNamespace(), {{}})
                plugin.runtime = Runtime()
                plugin.commands = object()
                metadata = types.SimpleNamespace(
                    name='astrbot_plugin_daily_life',
                    root_dir_name='astrbot_plugin_daily_life',
                    activated=True,
                    star_cls=plugin,
                )
                bridge = DailyLifeBridge(
                    types.SimpleNamespace(get_all_stars=lambda: [metadata])
                )
                target = 'bot-test:FriendMessage:user-test-a'
                assert (await bridge.get_life_context(target))['target'] == target
                assert await bridge.record_external_activity(
                    target,
                    '测试分享内容',
                    reason='每日分享记录',
                    sync_memory=True,
                )
                evidence = await bridge.search_evidence(
                    '测试新闻',
                    category='news',
                    target_umo=target,
                )
                assert evidence['content'] == '跨插件搜索证据'
                assert await bridge.generate_image(None, '配图提示词') == 'image://配图提示词'
                assert await bridge.generate_video(
                    None,
                    '视频提示词',
                    reference_image='image://first-frame',
                ) == 'video://视频提示词'
                assert await bridge.generate_voice(
                    '语音文本',
                    emotion='自然讲述',
                    emotion_category='neutral',
                ) == 'voice://语音文本'

            asyncio.run(run())
            """
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    async def test_bridge_calls_real_daily_life_public_entry_with_target(self):
        plugin = _life_plugin("实例一")
        context = types.SimpleNamespace(get_all_stars=lambda: [_metadata(plugin)])
        bridge = DailyLifeBridge(context)

        target = "bot-test:FriendMessage:user-test-a"
        result = await bridge.get_life_context(target)
        recorded = await bridge.record_external_activity(
            target,
            "测试分享内容",
            reason="每日分享记录",
            sync_memory=True,
        )

        self.assertEqual(result["target"], target)
        self.assertEqual(plugin.runtime.context_targets, [target])
        self.assertTrue(recorded)
        self.assertEqual(plugin.runtime.activities[0][0], target)

    async def test_bridge_search_passes_category_and_target(self):
        plugin = _life_plugin("实例一")
        bridge = DailyLifeBridge(
            types.SimpleNamespace(get_all_stars=lambda: [_metadata(plugin)])
        )
        target = "bot-test:FriendMessage:user-test-a"

        result = await bridge.search_evidence(
            "测试作品",
            category="recommendation",
            target_umo=target,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["content"], "测试作品 的联网证据")
        self.assertEqual(
            plugin.runtime.searches,
            [
                (
                    "测试作品",
                    {"category": "recommendation", "target_umo": target},
                )
            ],
        )

    async def test_bridge_search_degrades_when_plugin_is_missing(self):
        bridge = DailyLifeBridge(types.SimpleNamespace(get_all_stars=lambda: []))

        result = await bridge.search_evidence("测试新闻", category="news")

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["content"], "")

    async def test_bridge_search_preserves_disabled_status(self):
        class Plugin:
            async def search_share_evidence(self, query, **kwargs):
                return {
                    "status": "disabled",
                    "query": query,
                    "content": "",
                    "error": "联网搜索未启用",
                }

        bridge = DailyLifeBridge(
            types.SimpleNamespace(get_all_stars=lambda: [_metadata(Plugin())])
        )

        result = await bridge.search_evidence("测试新闻", category="news")

        self.assertEqual(result["status"], "disabled")
        self.assertEqual(result["content"], "")

    async def test_bridge_search_contains_plugin_failure(self):
        class Plugin:
            async def search_share_evidence(self, query, **kwargs):
                raise RuntimeError("模拟搜索失败")

        bridge = DailyLifeBridge(
            types.SimpleNamespace(get_all_stars=lambda: [_metadata(Plugin())])
        )

        result = await bridge.search_evidence("测试新闻", category="news")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["content"], "")
        self.assertIn("模拟搜索失败", result["error"])

    async def test_bridge_ignores_disabled_and_similarly_named_plugins(self):
        plugin = _life_plugin("不应调用")
        stars = [
            _metadata(plugin, activated=False),
            _metadata(plugin, plugin_id="astrbot_plugin_daily_life_extra"),
        ]
        bridge = DailyLifeBridge(types.SimpleNamespace(get_all_stars=lambda: stars))

        self.assertEqual(
            await bridge.get_life_context("bot-test:FriendMessage:user-test-a"),
            {},
        )
        self.assertEqual(plugin.runtime.context_targets, [])

    async def test_bridge_resolves_new_instance_after_reload(self):
        first = _life_plugin("旧实例")
        second = _life_plugin("新实例")
        stars = [_metadata(first)]
        bridge = DailyLifeBridge(
            types.SimpleNamespace(get_all_stars=lambda: list(stars))
        )

        first_result = await bridge.get_life_context(
            "bot-test:FriendMessage:user-test-a"
        )
        stars[:] = [_metadata(second)]
        second_result = await bridge.get_life_context(
            "bot-test:FriendMessage:user-test-b"
        )

        self.assertEqual(first_result["schedule"], "旧实例")
        self.assertEqual(second_result["schedule"], "新实例")
        self.assertEqual(
            first.runtime.context_targets, ["bot-test:FriendMessage:user-test-a"]
        )
        self.assertEqual(
            second.runtime.context_targets, ["bot-test:FriendMessage:user-test-b"]
        )

    def test_bridge_reports_media_entry_availability(self):
        plugin = _life_plugin("实例一")
        bridge = DailyLifeBridge(
            types.SimpleNamespace(get_all_stars=lambda: [_metadata(plugin)])
        )

        self.assertTrue(bridge.media_available("image"))
        self.assertTrue(bridge.media_available("video"))
        self.assertTrue(bridge.media_available("audio"))
        self.assertFalse(bridge.media_available("unknown"))

    async def test_bridge_records_media_call_outcomes(self):
        class Plugin:
            async def generate_share_image(
                self, event, prompt, *, contains_character=False
            ):
                if prompt == "重载":
                    raise RuntimeError("日常生活插件尚未就绪或正在终止")
                if prompt == "空结果":
                    return ""
                return f"image:{prompt}"

        bridge = DailyLifeBridge(
            types.SimpleNamespace(get_all_stars=lambda: [_metadata(Plugin())])
        )

        self.assertEqual(await bridge.generate_image(None, "成功"), "image:成功")
        self.assertEqual(bridge.media_result("image"), ("ok", ""))

        self.assertEqual(await bridge.generate_image(None, "空结果"), "")
        status, reason = bridge.media_result("image")
        self.assertEqual(status, "empty")
        self.assertIn("未返回有效结果", reason)

        self.assertEqual(await bridge.generate_image(None, "重载"), "")
        status, reason = bridge.media_result("image")
        self.assertEqual(status, "unavailable")
        self.assertIn("重载", reason)

    async def test_bridge_records_missing_media_entry_as_unavailable(self):
        bridge = DailyLifeBridge(types.SimpleNamespace(get_all_stars=lambda: []))

        self.assertEqual(await bridge.generate_image(None, "测试"), "")
        status, reason = bridge.media_result("image")

        self.assertEqual(status, "unavailable")
        self.assertIn("未安装", reason)

    async def test_bridge_media_results_are_isolated_between_tasks(self):
        class Plugin:
            async def generate_share_image(
                self, event, prompt, *, contains_character=False
            ):
                if prompt == "失败":
                    raise RuntimeError("模拟接口失败")
                return f"image:{prompt}"

        bridge = DailyLifeBridge(
            types.SimpleNamespace(get_all_stars=lambda: [_metadata(Plugin())])
        )
        completed = []
        both_completed = asyncio.Event()

        async def invoke(prompt):
            await bridge.generate_image(None, prompt)
            completed.append(prompt)
            if len(completed) == 2:
                both_completed.set()
            await both_completed.wait()
            return bridge.media_result("image")

        success, failure = await asyncio.gather(invoke("成功"), invoke("失败"))

        self.assertEqual(success, ("ok", ""))
        self.assertEqual(failure[0], "error")
        self.assertIn("调用失败", failure[1])


if __name__ == "__main__":
    unittest.main()

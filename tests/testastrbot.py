import importlib.util
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(
    importlib.util.find_spec("astrbot"),
    "需要安装 AstrBot 4.26.6 才能执行真实契约测试",
)
class AstrBotContractTests(unittest.TestCase):
    def test_real_astrbot_426_plugin_lifecycle(self):
        script = textwrap.dedent(
            """
            import asyncio
            import importlib.metadata
            import tempfile
            from pathlib import Path

            from astrbot.api import AstrBotConfig
            from astrbot.api.star import Context, StarTools
            from astrbot_plugin_daily_share.main import DailySharePlugin
            from astrbot_plugin_daily_share.core.panel.revision import (
                settings_config_revision,
                target_config_revision,
            )


            class Platform:
                def meta(self):
                    return type(
                        "Meta",
                        (),
                        {
                            "id": "bot-main",
                            "name": "aiocqhttp",
                            "support_proactive_message": True,
                        },
                    )()

                def get_client(self):
                    return None


            class PlatformManager:
                def get_insts(self):
                    return [Platform()]


            async def run():
                version = importlib.metadata.version("astrbot")
                major, minor, *_ = (int(part) for part in version.split("."))
                assert (major, minor) >= (4, 26), version

                with tempfile.TemporaryDirectory() as temp_dir:
                    StarTools.get_data_dir = staticmethod(
                        lambda _name=None: Path(temp_dir)
                    )
                    context = Context(
                        asyncio.Queue(),
                        {},
                        None,
                        None,
                        PlatformManager(),
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                    )
                    context.registered_web_apis.clear()
                    config = AstrBotConfig(
                        config_path=str(Path(temp_dir) / "daily-share-config.json"),
                        default_config={},
                    )
                    plugin = DailySharePlugin(context, config)

                    assert len(context.registered_web_apis) == 0
                    assert plugin.db.db_path.name == "daily_share.db"
                    await plugin.initialize()
                    assert len(context.registered_web_apis) == 23
                    assert plugin._is_initialized
                    assert plugin._runtime_state == "ready"
                    assert plugin.runtime_service.runtime_status()["ready"]

                    runtime = plugin.dashboard_service.operations

                    target_body = {
                        "target_revision": target_config_revision(plugin.config),
                        "groups": [
                            {
                                "id": "",
                                "session_id": "group-test-001",
                                "adapter_id": "bot-main",
                            }
                        ],
                        "users": [],
                        "briefing_groups": [
                            {
                                "id": "group-test-001",
                                "session_id": "group-test-001",
                                "adapter_id": "",
                            }
                        ],
                        "briefing_users": [],
                    }

                    async def targets_body():
                        return target_body

                    async def direct_page_json(callback, headers=None):
                        return await callback()

                    async def empty_status():
                        return {"ok": True, "data": {"targets": {}}}

                    runtime.server._page_json_body = targets_body
                    runtime.server._page_json = direct_page_json
                    runtime.status_routes._build_page_status = empty_status
                    result = await runtime.target_routes.page_targets_update()
                    assert result["ok"], result
                    expected = "bot-main:GroupMessage:group-test-001"
                    assert plugin.receiver_conf["groups"] == [expected]
                    assert plugin.extra_shares_conf["briefing_groups"] == [expected]

                    stale_target_revision = target_body["target_revision"]
                    target_body = {
                        "target_revision": stale_target_revision,
                        "groups": [],
                        "users": [],
                        "briefing_groups": [],
                        "briefing_users": [],
                    }
                    try:
                        await runtime.target_routes.page_targets_update()
                    except RuntimeError as exc:
                        assert "目标配置已在其他页面或运行过程中更新" in str(exc)
                    else:
                        raise AssertionError("旧目标配置版本未被拒绝")
                    assert plugin.receiver_conf["groups"] == [expected]

                    target_body["target_revision"] = target_config_revision(
                        plugin.config
                    )
                    result = await runtime.target_routes.page_targets_update()
                    assert result["ok"], result
                    assert plugin.receiver_conf == {"groups": [], "users": []}

                    initial_settings_revision = settings_config_revision(plugin.config)
                    config_body = {
                        "settings_revision": initial_settings_revision,
                        "sections": {"basic": {"llm_timeout": 90}},
                    }

                    async def config_page_body():
                        return config_body

                    runtime.server._page_json_body = config_page_body
                    result = await runtime.config_routes.page_config()
                    assert result["ok"], result
                    assert plugin.basic_conf["llm_timeout"] == 90

                    config_body = {
                        "settings_revision": initial_settings_revision,
                        "sections": {"basic": {"llm_timeout": 91}},
                    }
                    try:
                        await runtime.config_routes.page_config()
                    except RuntimeError as exc:
                        assert "设置已在其他页面或运行过程中更新" in str(exc)
                    else:
                        raise AssertionError("旧设置版本未被拒绝")
                    assert plugin.basic_conf["llm_timeout"] == 90

                    await plugin.terminate()
                    assert len(context.registered_web_apis) == 0
                    assert plugin._is_terminated
                    assert plugin._runtime_state == "terminated"
                    assert not plugin._bg_tasks


            asyncio.run(run())
            """
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT.parent,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

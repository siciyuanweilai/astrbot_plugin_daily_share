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

            from astrbot.api.star import Context, StarTools
            from astrbot_plugin_daily_share.main import DailySharePlugin


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
                    plugin = DailySharePlugin(context, {})

                    assert len(context.registered_web_apis) == 0
                    assert plugin.db.db_path.name == "daily_share.db"
                    await plugin.initialize()
                    assert len(context.registered_web_apis) == 23
                    assert plugin._is_initialized
                    assert plugin._runtime_state == "ready"
                    assert plugin.runtime_service.runtime_status()["ready"]

                    runtime = plugin.dashboard_service.operations

                    target_body = {
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

                    target_body = {
                        "groups": [],
                        "users": [],
                        "briefing_groups": [],
                        "briefing_users": [],
                    }
                    result = await runtime.target_routes.page_targets_update()
                    assert result["ok"], result
                    assert plugin.receiver_conf == {"groups": [], "users": []}

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

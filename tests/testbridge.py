import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from astrbot_plugin_daily_share.bridge.server import (
    BridgeConfig,
    BridgeError,
    CliRunner,
    _json_output,
)


class BridgeHelpersTests(unittest.TestCase):
    def test_json_output_accepts_json_after_cli_logs(self):
        self.assertEqual(
            _json_output('日志\n{"code": 0, "data": {"id": "note-1"}}'),
            {"code": 0, "data": {"id": "note-1"}},
        )

    def test_json_output_rejects_non_json(self):
        with self.assertRaisesRegex(BridgeError, "无效 JSON"):
            _json_output("cli failed")

    def test_runner_builds_video_arguments_from_single_path(self):
        with tempfile.TemporaryDirectory() as directory:
            scripts = Path(directory) / "scripts"
            scripts.mkdir()
            (scripts / "cli.py").write_text("", encoding="utf-8")
            runner = CliRunner(BridgeConfig(Path(directory)))
            with patch.object(runner, "_run", return_value={"code": 0}) as run:
                runner.publish_video(
                    {
                        "title": "标题",
                        "content": "正文",
                        "video": "/tmp/demo.mp4",
                        "tags": ["日常"],
                        "visibility": "公开可见",
                    }
                )
            args = run.call_args.args
            self.assertEqual(args[0], "publish-video")
            self.assertIn("--video", args[1])
            self.assertIn("/tmp/demo.mp4", args[1])
            visibility_index = args[1].index("--visibility")
            self.assertEqual(args[1][visibility_index + 1], "公开可见")

    def test_runner_requires_cli_directory(self):
        with self.assertRaisesRegex(BridgeError, "未找到小红书 CLI"):
            CliRunner(BridgeConfig(Path("/tmp/not-a-daily-share-cli")))


if __name__ == "__main__":
    unittest.main()

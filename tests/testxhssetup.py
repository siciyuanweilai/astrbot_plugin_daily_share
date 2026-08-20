from __future__ import annotations

import importlib.util
import unittest
from argparse import Namespace
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "bridge" / "xhssetup.py"
SPEC = importlib.util.spec_from_file_location("xhssetup", SCRIPT)
assert SPEC and SPEC.loader
SETUP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SETUP)


class XiaohongshuSetupTests(unittest.TestCase):
    def test_reports_all_missing_system_requirements(self) -> None:
        with patch.object(SETUP.shutil, "which", return_value=None), patch.object(
            SETUP, "_browser", return_value=None
        ), patch.object(SETUP, "_uv_path", return_value=None):
            self.assertEqual(
                SETUP._missing_system_requirements(),
                ["git", "xvfb", "browser", "venv"],
            )

    def test_system_install_dry_run_does_not_call_sudo(self) -> None:
        manager = ("dnf", SETUP.PACKAGE_MANAGERS["dnf"])
        with patch.object(SETUP, "_missing_system_requirements", return_value=["git", "xvfb"]), patch.object(
            SETUP, "_package_manager", return_value=manager
        ), patch.object(SETUP, "_command") as command:
            self.assertEqual(
                SETUP._install_system_packages(dry_run=True),
                ["通过 dnf 安装系统依赖: git xorg-x11-server-Xvfb"],
            )
            command.assert_not_called()

    def test_uv_install_dry_run_does_not_download(self) -> None:
        with patch.object(SETUP, "_command") as command:
            self.assertEqual(SETUP._install_uv(dry_run=True), "在专用 Python 虚拟环境中安装 uv")
            command.assert_not_called()

    def test_login_waits_only_when_login_is_required(self) -> None:
        required = CompletedProcess([], 1, stdout='{"logged_in": false}\n', stderr="")
        completed = CompletedProcess([], 0, stdout='{"logged_in": true}\n', stderr="")
        with patch.object(SETUP, "_cli_call", side_effect=[required, completed]) as cli_call:
            self.assertEqual(SETUP._login(Namespace()), 0)
            self.assertEqual(cli_call.call_args_list[0].args[1], "check-login")
            self.assertEqual(cli_call.call_args_list[1].args[1], "wait-login")


if __name__ == "__main__":
    unittest.main()

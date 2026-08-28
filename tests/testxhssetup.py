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
    def test_apparmor_profile_grants_only_userns_for_selected_browser(self) -> None:
        profile = SETUP._apparmor_profile("/srv/xhs chrome/chrome")

        self.assertIn(
            "profile daily-share-xhs-chromium /srv/xhs\\x20chrome/chrome", profile
        )
        self.assertIn("flags=(unconfined)", profile)
        self.assertIn("    userns,", profile)

    def test_unit_working_directories_are_systemd_paths_not_argv_quotes(self) -> None:
        units = SETUP._units(
            {
                "plugin_dir": "/srv/daily share",
                "skills_dir": "/srv/xhs skills",
                "uv": "/usr/bin/uv",
                "listen_host": "172.18.0.1",
                "port": 18061,
                "allowed_clients": ["172.18.0.3"],
                "browser": "/usr/bin/chromium",
                "profile_dir": "/srv/xhs profile",
            }
        )

        self.assertIn(
            "WorkingDirectory=/srv/daily\\x20share", units[SETUP.BRIDGE_SERVICE]
        )
        self.assertIn(
            "WorkingDirectory=/srv/xhs\\x20skills", units[SETUP.BROWSER_SERVICE]
        )
        self.assertNotIn("--no-sandbox", units[SETUP.BROWSER_SERVICE])
        self.assertIn('"--allow-client" "172.18.0.3"', units[SETUP.BRIDGE_SERVICE])

    def test_bootstrap_defaults_to_pinned_upstream_revision(self) -> None:
        args = SETUP._parser().parse_args(["bootstrap"])

        self.assertEqual(args.ref, SETUP.DEFAULT_SKILLS_REF)

    def test_reports_all_missing_system_requirements(self) -> None:
        with (
            patch.object(SETUP.shutil, "which", return_value=None),
            patch.object(SETUP, "_browser", return_value=None),
            patch.object(SETUP, "_uv_path", return_value=None),
        ):
            self.assertEqual(
                SETUP._missing_system_requirements(),
                ["git", "xvfb", "browser", "venv"],
            )

    def test_system_install_dry_run_does_not_call_sudo(self) -> None:
        manager = ("dnf", SETUP.PACKAGE_MANAGERS["dnf"])
        with (
            patch.object(
                SETUP, "_missing_system_requirements", return_value=["git", "xvfb"]
            ),
            patch.object(SETUP, "_package_manager", return_value=manager),
            patch.object(SETUP, "_command") as command,
        ):
            self.assertEqual(
                SETUP._install_system_packages(dry_run=True),
                ["通过 dnf 安装系统依赖: git xorg-x11-server-Xvfb"],
            )
            command.assert_not_called()

    def test_uv_install_dry_run_does_not_download(self) -> None:
        with patch.object(SETUP, "_command") as command:
            self.assertEqual(
                SETUP._install_uv(dry_run=True), "在专用 Python 虚拟环境中安装 uv"
            )
            command.assert_not_called()

    def test_login_waits_only_when_login_is_required(self) -> None:
        required = CompletedProcess([], 1, stdout='{"logged_in": false}\n', stderr="")
        completed = CompletedProcess([], 0, stdout='{"logged_in": true}\n', stderr="")
        with patch.object(
            SETUP, "_cli_call", side_effect=[required, completed]
        ) as cli_call:
            self.assertEqual(SETUP._login(Namespace()), 0)
            self.assertEqual(cli_call.call_args_list[0].args[1], "check-login")
            self.assertEqual(cli_call.call_args_list[1].args[1], "wait-login")


if __name__ == "__main__":
    unittest.main()

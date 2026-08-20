#!/usr/bin/env python3
"""Inspect, install, and verify Daily Share's local Xiaohongshu services."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

BRIDGE_SERVICE = "daily-share-xhs.service"
BROWSER_SERVICE = "daily-share-xhs-browser.service"
DEFAULT_PORT = 18061
DEFAULT_SKILLS_REPOSITORY = "https://github.com/autoclaw-cc/xiaohongshu-skills.git"
MANAGED_UV_PATH = Path.home() / ".local" / "share" / "daily-share-xhs" / "uv" / "bin" / "uv"
PACKAGE_MANAGERS: dict[str, dict[str, Any]] = {
    "apt-get": {
        "display": "apt",
        "refresh": ["update"],
        "install": ["install", "-y"],
        "packages": {
            "git": "git",
            "xvfb": "xvfb",
            "browser": "chromium-browser",
            "venv": "python3-venv",
        },
    },
    "dnf": {
        "display": "dnf",
        "refresh": [],
        "install": ["install", "-y"],
        "packages": {
            "git": "git",
            "xvfb": "xorg-x11-server-Xvfb",
            "browser": "chromium",
            "venv": "python3",
        },
    },
    "yum": {
        "display": "yum",
        "refresh": [],
        "install": ["install", "-y"],
        "packages": {
            "git": "git",
            "xvfb": "xorg-x11-server-Xvfb",
            "browser": "chromium",
            "venv": "python3",
        },
    },
    "pacman": {
        "display": "pacman",
        "refresh": [],
        "install": ["--noconfirm", "-S"],
        "packages": {
            "git": "git",
            "xvfb": "xorg-server-xvfb",
            "browser": "chromium",
            "venv": "python",
        },
    },
    "zypper": {
        "display": "zypper",
        "refresh": [],
        "install": ["--non-interactive", "install"],
        "packages": {
            "git": "git",
            "xvfb": "xorg-x11-server",
            "browser": "chromium",
            "venv": "python3",
        },
    },
    "apk": {
        "display": "apk",
        "refresh": [],
        "install": ["add"],
        "packages": {
            "git": "git",
            "xvfb": "xvfb",
            "browser": "chromium",
            "venv": "py3-virtualenv",
        },
    },
}


def _command(
    args: list[str], *, check: bool = False, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=check, cwd=cwd)


def _uv_path(value: str) -> Path | None:
    if value:
        path = Path(value).expanduser().resolve()
        if path.is_file() and os.access(path, os.X_OK):
            return path
    found = shutil.which("uv")
    if found:
        return Path(found).resolve()
    local = Path.home() / ".local" / "bin" / "uv"
    if local.is_file() and os.access(local, os.X_OK):
        return local.resolve()
    return (
        MANAGED_UV_PATH.resolve()
        if MANAGED_UV_PATH.is_file() and os.access(MANAGED_UV_PATH, os.X_OK)
        else None
    )


def _command_error(label: str, completed: subprocess.CompletedProcess[str]) -> RuntimeError:
    detail = (completed.stderr or completed.stdout).strip()
    if detail:
        return RuntimeError(f"{label}失败: {detail}")
    return RuntimeError(f"{label}失败，退出码 {completed.returncode}")


def _missing_system_requirements() -> list[str]:
    requirements: list[str] = []
    if not shutil.which("git"):
        requirements.append("git")
    if not shutil.which("xvfb-run"):
        requirements.append("xvfb")
    if not _browser(""):
        requirements.append("browser")
    if not _uv_path(""):
        requirements.append("venv")
    return requirements


def _package_manager() -> tuple[str, dict[str, Any]] | None:
    for command, definition in PACKAGE_MANAGERS.items():
        if shutil.which(command):
            return command, definition
    return None


def _package_names(manager: dict[str, Any], requirements: list[str]) -> list[str]:
    mapping = manager["packages"]
    return [str(mapping[item]) for item in requirements]


def _install_system_packages(*, dry_run: bool) -> list[str]:
    requirements = _missing_system_requirements()
    if not requirements:
        return []
    manager = _package_manager()
    if not manager:
        supported = "、".join(item.replace("apt-get", "apt") for item in PACKAGE_MANAGERS)
        raise RuntimeError(f"未找到受支持的包管理器（{supported}）")
    command, definition = manager
    packages = _package_names(definition, requirements)
    action = f"通过 {definition['display']} 安装系统依赖: {' '.join(packages)}"
    if dry_run:
        return [action]
    prefix: list[str] = []
    if getattr(os, "geteuid", lambda: 1)() != 0:
        sudo = shutil.which("sudo")
        if not sudo:
            raise RuntimeError("未以管理员身份运行且未找到 sudo，无法自动安装系统依赖")
        authenticated = _command([sudo, "-v"])
        if authenticated.returncode != 0:
            raise _command_error("获取 sudo 权限", authenticated)
        prefix = [sudo]
    refresh = definition["refresh"]
    if refresh:
        updated = _command([*prefix, command, *refresh])
        if updated.returncode != 0:
            raise _command_error(f"更新 {definition['display']} 软件包索引", updated)
    installed = _command([*prefix, command, *definition["install"], *packages])
    if installed.returncode != 0:
        raise _command_error("安装系统依赖", installed)
    return [action]


def _install_uv(*, dry_run: bool) -> str:
    action = "在专用 Python 虚拟环境中安装 uv"
    if dry_run:
        return action
    python = shutil.which("python3") or sys.executable
    environment = MANAGED_UV_PATH.parent.parent
    created = _command([python, "-m", "venv", str(environment)])
    if created.returncode != 0:
        raise _command_error("创建 uv 专用虚拟环境", created)
    installer = environment / "bin" / "python"
    completed = _command(
        [str(installer), "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "uv"]
    )
    if completed.returncode != 0:
        raise _command_error("安装 uv", completed)
    return action


def _valid_plugin(path: Path | None) -> bool:
    return bool(path and (path / "bridge" / "server.py").is_file())


def _valid_skills(path: Path | None) -> bool:
    return bool(
        path
        and (path / "scripts" / "cli.py").is_file()
        and (path / "extension" / "manifest.json").is_file()
    )


def _first_valid(candidates: list[Path], validator) -> Path | None:
    seen: set[Path] = set()
    for candidate in candidates:
        path = candidate.expanduser().resolve()
        if path in seen:
            continue
        seen.add(path)
        if validator(path):
            return path
    return None


def _plugin_dir(value: str) -> Path | None:
    if value:
        path = Path(value).expanduser().resolve()
        return path if _valid_plugin(path) else None
    env = os.environ.get("DAILY_SHARE_PLUGIN_DIR", "")
    candidates = [
        Path(env) if env else Path.cwd(),
        Path.cwd(),
        Path.cwd() / "astrbot_plugin_daily_share",
        Path.home()
        / "astrbot-docker"
        / "data"
        / "astrbot"
        / "plugins"
        / "astrbot_plugin_daily_share",
        Path("/AstrBot/data/plugins/astrbot_plugin_daily_share"),
    ]
    return _first_valid(candidates, _valid_plugin)


def _skills_dir(value: str) -> Path | None:
    if value:
        path = Path(value).expanduser().resolve()
        return path if _valid_skills(path) else None
    env = os.environ.get("XHS_SKILLS_DIR", "")
    candidates = [
        Path(env) if env else Path.cwd(),
        Path.cwd(),
        Path.cwd() / "xiaohongshu-skills",
        Path.home() / "xiaohongshu-skills",
    ]
    return _first_valid(candidates, _valid_skills)


def _browser(value: str) -> Path | None:
    if value:
        path = Path(value).expanduser().resolve()
        return path if path.is_file() and os.access(path, os.X_OK) else None
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return Path(found).resolve()
    cache = Path.home() / ".cache" / "ms-playwright"
    matches = sorted(
        cache.glob("chromium-*/chrome-linux*/chrome"),
        key=lambda item: item.stat().st_mtime if item.exists() else 0,
        reverse=True,
    )
    return matches[0].resolve() if matches else None


def _docker_info(container: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": bool(shutil.which("docker")),
        "container": container,
        "exists": False,
        "running": False,
        "gateway": "",
        "data_source": "",
        "data_destination": "",
    }
    if not result["available"] or not container:
        return result
    completed = _command(["docker", "inspect", container])
    if completed.returncode != 0:
        return result
    try:
        item = json.loads(completed.stdout)[0]
    except (json.JSONDecodeError, IndexError, TypeError):
        return result
    result["exists"] = True
    result["running"] = bool(item.get("State", {}).get("Running"))
    networks = item.get("NetworkSettings", {}).get("Networks", {})
    for network in networks.values() if isinstance(networks, dict) else []:
        gateway = str(network.get("Gateway", "") or "").strip()
        if gateway:
            result["gateway"] = gateway
            break
    mounts = item.get("Mounts", [])
    preferred = None
    for mount in mounts if isinstance(mounts, list) else []:
        destination = str(mount.get("Destination", "") or "").rstrip("/")
        if destination == "/AstrBot/data":
            preferred = mount
            break
    if preferred:
        result["data_source"] = str(preferred.get("Source", "") or "")
        result["data_destination"] = str(preferred.get("Destination", "") or "")
    return result


def _service_state(name: str) -> dict[str, str]:
    if not shutil.which("systemctl"):
        return {"active": "unknown", "enabled": "unknown"}
    active = _command(["systemctl", "--user", "is-active", name])
    enabled = _command(["systemctl", "--user", "is-enabled", name])
    return {
        "active": (active.stdout or active.stderr).strip() or "unknown",
        "enabled": (enabled.stdout or enabled.stderr).strip() or "unknown",
    }


def _linger_state() -> str:
    if not shutil.which("loginctl"):
        return "unknown"
    completed = _command(["loginctl", "show-user", str(os.getuid()), "-p", "Linger", "--value"])
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _inspect(args: argparse.Namespace) -> dict[str, Any]:
    plugin = _plugin_dir(args.plugin_dir)
    skills = _skills_dir(args.skills_dir)
    browser = _browser(args.browser)
    docker = _docker_info(args.container)
    uv = _uv_path(args.uv)
    host = args.host.strip() if args.host else ""
    if not host:
        host = docker["gateway"] if docker["exists"] else "127.0.0.1"
    source = docker["data_destination"] if docker["data_source"] else ""
    target = docker["data_source"] if docker["data_source"] else ""
    issues: list[str] = []
    if not plugin:
        issues.append("未找到包含 bridge/server.py 的 Daily Share 插件目录")
    if not skills:
        issues.append("未找到包含 scripts/cli.py 和 extension/manifest.json 的小红书 CLI 目录")
    if not uv:
        issues.append("未找到 uv")
    if not browser:
        issues.append("未找到可执行的 Chromium 或 Chrome")
    if not shutil.which("xvfb-run"):
        issues.append("未找到 xvfb-run")
    if not shutil.which("systemctl"):
        issues.append("未找到 systemctl，无法安装用户级后台服务")
    if host in {"0.0.0.0", "::"}:
        issues.append("拒绝使用会暴露公网的监听地址")
    if docker["exists"] and not docker["gateway"]:
        issues.append("AstrBot 容器存在，但未探测到 Docker 网关")
    server_url = f"http://{host}:{args.port}/api"
    return {
        "ready": not issues,
        "issues": issues,
        "plugin_dir": str(plugin) if plugin else "",
        "skills_dir": str(skills) if skills else "",
        "uv": str(uv) if uv else "",
        "browser": str(browser) if browser else "",
        "profile_dir": str(Path(args.profile_dir).expanduser().resolve()),
        "listen_host": host,
        "port": args.port,
        "docker": docker,
        "services": {
            BRIDGE_SERVICE: _service_state(BRIDGE_SERVICE),
            BROWSER_SERVICE: _service_state(BROWSER_SERVICE),
        },
        "linger": _linger_state(),
        "recommended_config": {
            "server_url": server_url,
            "media_path_source": source,
            "media_path_target": target,
        },
    }


def _bootstrap(args: argparse.Namespace) -> int:
    """Install the upstream CLI into a chosen directory without overwriting it."""
    target = Path(args.target_dir).expanduser()
    target_display = str(target.resolve())
    cloned = False
    if target.exists():
        if not target.is_dir():
            raise RuntimeError(f"小红书 CLI 目标不是目录: {target_display}")
        if not _valid_skills(target):
            raise RuntimeError(
                f"目标目录已存在但不是完整的小红书 CLI，拒绝覆盖: {target_display}"
            )
    else:
        cloned = True

    system_actions = _install_system_packages(dry_run=args.dry_run) if args.install_system_deps else []
    git = shutil.which("git")
    uv = _uv_path(args.uv)
    uv_action = ""
    if not git and not args.install_system_deps:
        raise RuntimeError("未找到 git；使用 --install-system-deps 自动安装后再试")
    if not uv and not args.install_system_deps:
        raise RuntimeError("未找到 uv；使用 --install-system-deps 自动安装后再试")
    if not uv and args.install_system_deps:
        uv_action = _install_uv(dry_run=args.dry_run)
        if not args.dry_run:
            uv = _uv_path(args.uv)
    if args.dry_run:
        actions = [
            *system_actions,
            *([uv_action] if uv_action else []),
            f"{'克隆' if cloned else '复用'}小红书 CLI: {target_display}",
            "执行 uv sync",
        ]
    else:
        if not git:
            raise RuntimeError("系统依赖安装完成后仍未找到 git")
        if not uv:
            raise RuntimeError("uv 安装完成后仍未找到可执行文件")
        actions = [
            *system_actions,
            *([uv_action] if uv_action else []),
            f"{'克隆' if cloned else '复用'}小红书 CLI: {target_display}",
            "执行 uv sync",
        ]
    if args.dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "skills_dir": target_display,
                    "repository": args.repo,
                    "actions": actions,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if cloned:
        target.parent.mkdir(parents=True, exist_ok=True)
        clone_args = [git, "clone", "--depth", "1"]
        if args.ref:
            clone_args.extend(["--branch", args.ref])
        clone_args.extend([args.repo, str(target)])
        completed = _command(clone_args)
        if completed.returncode != 0:
            raise _command_error("克隆小红书 CLI", completed)

    completed = _command([str(uv), "sync"], cwd=target)
    if completed.returncode != 0:
        raise _command_error("安装小红书 CLI 依赖", completed)

    print(
        json.dumps(
            {
                "ok": True,
                "skills_dir": target_display,
                "installed": cloned,
                "dependencies_synced": True,
                "system_dependencies_installed": bool(system_actions),
                "next": "运行 inspect 确认浏览器和服务依赖，再运行 install",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _unit_arg(value: str | Path) -> str:
    text = str(value).replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _units(info: dict[str, Any]) -> dict[str, str]:
    python = shutil.which("python3") or sys.executable
    bridge_args = [
        python,
        "-u",
        "-m",
        "bridge.server",
        "--skills-dir",
        info["skills_dir"],
        "--uv",
        info["uv"],
        "--host",
        info["listen_host"],
        "--port",
        str(info["port"]),
    ]
    browser_args = [
        shutil.which("xvfb-run") or "xvfb-run",
        "--auto-servernum",
        info["browser"],
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={info['profile_dir']}",
        f"--load-extension={Path(info['skills_dir']) / 'extension'}",
        "https://www.xiaohongshu.com",
    ]
    bridge = f"""[Unit]
Description=Daily Share local Xiaohongshu bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={_unit_arg(info['plugin_dir'])}
ExecStart={' '.join(_unit_arg(item) for item in bridge_args)}
Restart=always
RestartSec=5
PrivateTmp=true

[Install]
WantedBy=default.target
"""
    browser = f"""[Unit]
Description=Daily Share Xiaohongshu browser session
Requires={BRIDGE_SERVICE}
After={BRIDGE_SERVICE} network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={_unit_arg(info['skills_dir'])}
ExecStart={' '.join(_unit_arg(item) for item in browser_args)}
Restart=always
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=15
PrivateTmp=true

[Install]
WantedBy=default.target
"""
    return {BRIDGE_SERVICE: bridge, BROWSER_SERVICE: browser}


def _write_unit(path: Path, content: str, *, force: bool) -> str:
    if path.exists():
        old = path.read_text(encoding="utf-8")
        if old == content:
            return "unchanged"
        if not force:
            raise RuntimeError(f"服务文件已存在且内容不同，使用 --force 才能备份并替换: {path}")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = path.with_name(f"{path.name}.bak.{stamp}")
        shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(content)
        temp = Path(handle.name)
    temp.chmod(0o600)
    temp.replace(path)
    return "written"


def _install(args: argparse.Namespace) -> int:
    info = _inspect(args)
    if not info["ready"]:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 2
    units = _units(info)
    if args.dry_run:
        print(json.dumps({"inspection": info, "units": units}, ensure_ascii=False, indent=2))
        return 0
    profile = Path(info["profile_dir"])
    profile.mkdir(parents=True, exist_ok=True)
    profile.chmod(0o700)
    unit_dir = Path(args.unit_dir).expanduser().resolve()
    changes = {
        name: _write_unit(unit_dir / name, content, force=args.force)
        for name, content in units.items()
    }
    _command(["systemctl", "--user", "daemon-reload"], check=True)
    _command(
        ["systemctl", "--user", "enable", BRIDGE_SERVICE, BROWSER_SERVICE],
        check=True,
    )
    _command(["systemctl", "--user", "restart", BRIDGE_SERVICE], check=True)
    _command(["systemctl", "--user", "restart", BROWSER_SERVICE], check=True)
    result = {
        "installed": True,
        "changes": changes,
        "linger": _linger_state(),
        "recommended_config": info["recommended_config"],
        "next": "运行 verify；若未登录，再执行 CLI 登录流程",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _setup(args: argparse.Namespace) -> int:
    result = _bootstrap(args)
    if result != 0:
        return result
    args.skills_dir = str(Path(args.target_dir).expanduser().resolve())
    return _install(args)


def _cli_call(args: argparse.Namespace, command: str) -> subprocess.CompletedProcess[str]:
    skills = _skills_dir(args.skills_dir)
    uv = _uv_path(args.uv)
    if not skills:
        raise RuntimeError("未找到小红书 CLI；请先运行 setup")
    if not uv:
        raise RuntimeError("未找到 uv；请先运行 setup")
    completed = _command([str(uv), "run", "python", "scripts/cli.py", command], cwd=skills)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    return completed


def _login(args: argparse.Namespace) -> int:
    checked = _cli_call(args, "check-login")
    if checked.returncode == 0:
        return 0
    if checked.returncode != 1:
        raise _command_error("检查小红书登录状态", checked)
    waited = _cli_call(args, "wait-login")
    if waited.returncode != 0:
        raise _command_error("等待小红书扫码登录", waited)
    return 0


def _http_json(url: str, *, method: str = "GET", timeout: int = 15) -> dict[str, Any]:
    body = b"{}" if method == "POST" else None
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw else {}
            return {"ok": True, "status": response.status, "data": data}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data: Any = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = raw
        return {"ok": False, "status": exc.code, "data": data}
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"ok": False, "status": 0, "error": str(exc)}


def _container_health(container: str, url: str) -> dict[str, Any]:
    docker = _docker_info(container)
    if not docker["exists"]:
        return {"ok": True, "skipped": True, "reason": "未使用已知 AstrBot 容器"}
    code = (
        "import sys,urllib.request;"
        "r=urllib.request.urlopen(sys.argv[1],timeout=10);"
        "print(r.status);print(r.read().decode())"
    )
    completed = _command(["docker", "exec", container, "python3", "-c", code, url])
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _verify(args: argparse.Namespace) -> int:
    info = _inspect(args)
    base = args.url.strip().rstrip("/") if args.url else info["recommended_config"]["server_url"]
    if not base:
        print(json.dumps({"ok": False, "error": "无法确定发布服务地址"}, ensure_ascii=False, indent=2))
        return 2
    health = _http_json(f"{base}/health")
    login = _http_json(f"{base}/check-login", method="POST", timeout=args.timeout)
    container = _container_health(args.container, f"{base}/health") if args.container else {
        "ok": True,
        "skipped": True,
        "reason": "未指定容器",
    }
    login_data = login.get("data") if isinstance(login.get("data"), dict) else {}
    logged_in = bool(login_data.get("logged_in")) if isinstance(login_data, dict) else False
    services = info["services"]
    service_ok = all(item.get("active") == "active" for item in services.values())
    mapping_target = info["recommended_config"].get("media_path_target", "")
    mapping_ok = not mapping_target or Path(mapping_target).is_dir()
    ok = bool(health.get("ok") and container.get("ok") and service_ok and mapping_ok and logged_in)
    result = {
        "ok": ok,
        "url": base,
        "services": services,
        "host_health": health,
        "container_health": container,
        "login": login,
        "logged_in": logged_in,
        "media_mapping_target_exists": mapping_ok,
        "recommended_config": info["recommended_config"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if ok:
        return 0
    if health.get("ok") and container.get("ok") and service_ok and mapping_ok and not logged_in:
        return 1
    return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--plugin-dir", default="")
    common.add_argument("--skills-dir", default="")
    common.add_argument("--browser", default="")
    common.add_argument("--profile-dir", default=str(Path.home() / "xhs-profile"))
    common.add_argument("--uv", default="")
    common.add_argument("--container", default="astrbot")
    common.add_argument("--host", default="")
    common.add_argument("--port", type=int, default=DEFAULT_PORT)
    bootstrap_common = argparse.ArgumentParser(add_help=False)
    bootstrap_common.add_argument("--target-dir", default=str(Path.home() / "xiaohongshu-skills"))
    bootstrap_common.add_argument("--repo", default=DEFAULT_SKILLS_REPOSITORY)
    bootstrap_common.add_argument("--ref", default="")
    bootstrap_common.add_argument("--install-system-deps", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    bootstrap = sub.add_parser(
        "bootstrap", parents=[bootstrap_common], help="下载小红书 CLI 并安装其 Python 依赖"
    )
    bootstrap.add_argument("--uv", default="")
    bootstrap.add_argument("--dry-run", action="store_true")
    sub.add_parser("inspect", parents=[common], help="只读检查环境并给出推荐配置")
    install = sub.add_parser("install", parents=[common], help="安装并启动用户级 systemd 服务")
    install.add_argument("--unit-dir", default=str(Path.home() / ".config" / "systemd" / "user"))
    install.add_argument("--force", action="store_true")
    install.add_argument("--dry-run", action="store_true")
    setup = sub.add_parser(
        "setup", parents=[common, bootstrap_common], help="自动安装依赖并启动小红书后台服务"
    )
    setup.add_argument("--unit-dir", default=str(Path.home() / ".config" / "systemd" / "user"))
    setup.add_argument("--force", action="store_true")
    setup.add_argument("--dry-run", action="store_true")
    sub.add_parser("login", parents=[common], help="显示二维码并等待小红书扫码登录")
    verify = sub.add_parser("verify", parents=[common], help="验证服务、容器连通和登录状态")
    verify.add_argument("--url", default="")
    verify.add_argument("--timeout", type=int, default=30)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command != "bootstrap" and (args.port < 1 or args.port > 65535):
        raise SystemExit("端口必须在 1 到 65535 之间")
    if args.command == "inspect":
        print(json.dumps(_inspect(args), ensure_ascii=False, indent=2))
        return 0
    if args.command == "bootstrap":
        return _bootstrap(args)
    if args.command == "install":
        return _install(args)
    if args.command == "setup":
        return _setup(args)
    if args.command == "login":
        return _login(args)
    return _verify(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(2) from exc

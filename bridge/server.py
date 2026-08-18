"""通过本地小红书 CLI 提供兼容 daily_share 的 REST 接口。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

MAX_BODY_BYTES = 4 * 1024 * 1024
DEFAULT_PORT = 18061
DEFAULT_TIMEOUT_SECONDS = 180


class BridgeError(RuntimeError):
    """本地桥接服务可直接返回给调用方的错误。"""


@dataclass(frozen=True)
class BridgeConfig:
    skills_dir: Path
    uv_command: str = "uv"
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    @property
    def cli_path(self) -> Path:
        return self.skills_dir / "scripts" / "cli.py"

    def validate(self) -> None:
        if not self.cli_path.is_file():
            raise BridgeError(f"未找到小红书 CLI: {self.cli_path}")


def _json_output(stdout: str) -> dict[str, Any]:
    text = str(stdout or "").strip()
    if not text:
        return {"success": True}
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = None
        for line in reversed(text.splitlines()):
            try:
                value = json.loads(line.strip())
                break
            except json.JSONDecodeError:
                continue
        if value is None:
            raise BridgeError("小红书 CLI 返回了无效 JSON")
    if isinstance(value, dict):
        return value
    return {"data": value}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in (_text(item) for item in value) if item]


def _media_list(value: Any, *, single: bool = False) -> list[str]:
    if single:
        item = _text(value)
        return [item] if item else []
    return _list(value)


def _visibility(value: Any) -> str:
    text = _text(value)
    return text or "公开可见"


class CliRunner:
    """把 REST 请求转换成 CLI 调用，不保存 Cookie 或媒体副本。"""

    def __init__(self, config: BridgeConfig):
        config.validate()
        self.config = config

    def _run(self, command: str, args: list[str]) -> dict[str, Any]:
        argv = [
            self.config.uv_command,
            "run",
            "python",
            "scripts/cli.py",
            command,
            *args,
        ]
        try:
            completed = subprocess.run(
                argv,
                cwd=self.config.skills_dir,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise BridgeError(f"未找到命令: {self.config.uv_command}") from exc
        except subprocess.TimeoutExpired as exc:
            raise BridgeError("小红书 CLI 执行超时") from exc

        if completed.returncode != 0:
            message = _text(completed.stderr) or _text(completed.stdout)
            raise BridgeError(message or f"小红书 CLI 退出码: {completed.returncode}")
        return _json_output(completed.stdout)

    def check_login(self) -> dict[str, Any]:
        return self._run("check-login", [])

    def publish(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._publish("publish", payload, "images")

    def publish_video(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._publish("publish-video", payload, "video")

    def _publish(
        self, command: str, payload: dict[str, Any], media_key: str
    ) -> dict[str, Any]:
        title = _text(payload.get("title"))
        content = _text(payload.get("content"))
        if not content:
            raise BridgeError("小红书正文不能为空")

        media = _media_list(payload.get(media_key), single=media_key == "video")
        if media_key == "video":
            if len(media) != 1:
                raise BridgeError("小红书视频路径必须恰好有一个")
        elif not media:
            raise BridgeError("小红书图文至少需要一张图片")

        tags = _list(payload.get("tags"))
        visibility = _visibility(payload.get("visibility"))
        with tempfile.TemporaryDirectory(prefix="daily-share-xhs-") as temp_dir:
            temp = Path(temp_dir)
            title_file = temp / "title.txt"
            content_file = temp / "content.txt"
            title_file.write_text(title, encoding="utf-8")
            content_file.write_text(content, encoding="utf-8")
            args = [
                "--title-file",
                str(title_file),
                "--content-file",
                str(content_file),
            ]
            if media_key == "video":
                args.extend(["--video", media[0]])
            else:
                args.extend(["--images", *media])
            if tags:
                args.extend(["--tags", *tags])
            if visibility:
                args.extend(["--visibility", visibility])
            return self._run(command, args)


def _json_request(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    raw_length = handler.headers.get("Content-Length", "0")
    try:
        length = int(raw_length)
    except ValueError as exc:
        raise BridgeError("请求体长度无效") from exc
    if length < 0 or length > MAX_BODY_BYTES:
        raise BridgeError("请求体过大")
    body = handler.rfile.read(length) if length else b"{}"
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeError("请求体不是有效 JSON") from exc
    if not isinstance(value, dict):
        raise BridgeError("请求体必须是 JSON 对象")
    return value


def _write_json(handler: BaseHTTPRequestHandler, status: int, value: Any) -> None:
    if status == HTTPStatus.NO_CONTENT:
        handler.send_response(status)
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        handler.send_header("Access-Control-Allow-Headers", "Content-Type")
        handler.end_headers()
        return
    body = json.dumps(value, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(body)


def make_handler(runner: CliRunner):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            print(f"[小红书桥接] {format % args}")

        def do_OPTIONS(self) -> None:  # noqa: N802
            _write_json(self, HTTPStatus.NO_CONTENT, {})

        def do_GET(self) -> None:  # noqa: N802
            if self.path in {"/health", "/api/health"}:
                _write_json(self, HTTPStatus.OK, {"status": "ok"})
                return
            _write_json(self, HTTPStatus.NOT_FOUND, {"error": "接口不存在"})

        def do_POST(self) -> None:  # noqa: N802
            endpoint = self.path.removeprefix("/api/").strip("/")
            try:
                if endpoint == "check-login":
                    result = runner.check_login()
                elif endpoint == "publish":
                    result = runner.publish(_json_request(self))
                elif endpoint == "publish-video":
                    result = runner.publish_video(_json_request(self))
                else:
                    _write_json(self, HTTPStatus.NOT_FOUND, {"error": "接口不存在"})
                    return
            except BridgeError as exc:
                _write_json(
                    self,
                    HTTPStatus.BAD_REQUEST,
                    {"success": False, "error": str(exc)},
                )
                return
            _write_json(self, HTTPStatus.OK, result)

    return Handler


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="启动 daily_share 小红书本地桥接服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="监听端口")
    parser.add_argument(
        "--skills-dir",
        default=os.environ.get("XHS_SKILLS_DIR", ""),
        help="包含 scripts/cli.py 的小红书 CLI 目录",
    )
    parser.add_argument(
        "--uv", default=os.environ.get("XHS_UV", "uv"), dest="uv_command"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="单次 CLI 调用超时秒数",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not args.skills_dir:
        raise SystemExit("请通过 --skills-dir 或 XHS_SKILLS_DIR 指定 CLI 目录")
    config = BridgeConfig(
        skills_dir=Path(args.skills_dir).expanduser().resolve(),
        uv_command=args.uv_command,
        timeout_seconds=max(10, min(args.timeout, 600)),
    )
    runner = CliRunner(config)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(runner))
    print(f"[小红书桥接] 监听 http://{args.host}:{args.port}/api")
    print(f"[小红书桥接] CLI 目录: {config.skills_dir}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[小红书桥接] 已停止")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

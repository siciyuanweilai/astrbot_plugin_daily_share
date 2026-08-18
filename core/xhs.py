from __future__ import annotations

import asyncio
import json
from pathlib import Path, PureWindowsPath
from urllib.parse import urlparse

import aiohttp


def normalize_xiaohongshu_visibility(value: str | None) -> str:
    """规范化小红书发布服务使用的中文可见范围。"""
    text = str(value or "").strip()
    return text or "公开可见"


class XiaohongshuPublishError(RuntimeError):
    """小红书发布服务返回的可读错误。"""


class XiaohongshuClient:
    """调用兼容 REST 接口的小红书发布服务。"""

    def __init__(self, config: dict | None = None) -> None:
        self.config = config if isinstance(config, dict) else {}

    def _base_url(self) -> str:
        value = str(self.config.get("server_url", "") or "").strip().rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise XiaohongshuPublishError("小红书发布服务地址无效")
        return value

    def _timeout(self) -> aiohttp.ClientTimeout:
        try:
            seconds = int(self.config.get("timeout_seconds", 120) or 120)
        except (TypeError, ValueError):
            seconds = 120
        return aiohttp.ClientTimeout(total=max(10, min(seconds, 600)))

    def _headers(self) -> dict[str, str]:
        cookie = str(self.config.get("cookie", "") or "").strip()
        return {"X-Xhs-Cookie": cookie} if cookie else {}

    def _media_path(self, value: str) -> str:
        path = str(value or "").strip()
        source = str(self.config.get("media_path_source", "") or "").strip()
        target = str(self.config.get("media_path_target", "") or "").strip()
        source_root = source.rstrip("/\\")
        if (
            source_root
            and target
            and (
                path == source_root
                or path.startswith(f"{source_root}/")
                or path.startswith(f"{source_root}\\")
            )
        ):
            suffix = path[len(source_root) :].lstrip("/\\")
            separator = "\\" if "\\" in target and "/" not in target else "/"
            if separator == "\\":
                suffix = suffix.replace("/", "\\")
            path = target.rstrip("/\\")
            if suffix:
                path = f"{path}{separator}{suffix}"
        return path

    @staticmethod
    def _is_absolute_media_path(value: str) -> bool:
        return Path(value).is_absolute() or PureWindowsPath(value).is_absolute()

    def _media_values(self, values: list[str] | None) -> list[str]:
        result = []
        for value in values or []:
            text = str(value or "").strip()
            if not text:
                continue
            if not text.startswith(("http://", "https://", "data:")):
                text = self._media_path(text)
                if not self._is_absolute_media_path(text):
                    raise XiaohongshuPublishError(f"媒体路径不是绝对路径: {text}")
            result.append(text)
        return result

    @staticmethod
    def _response_error(data, status: int) -> str:
        if isinstance(data, dict):
            nested = data.get("data") if isinstance(data.get("data"), dict) else {}
            if data.get("success") is False:
                return str(
                    data.get("error") or data.get("message") or "发布服务返回失败"
                )
            if data.get("ok") is False:
                return str(
                    data.get("error") or data.get("message") or "发布服务返回失败"
                )
            if data.get("error") or nested.get("error"):
                return str(data.get("error") or nested.get("error"))
            if data.get("code") not in (None, 0, "0", 200, "200"):
                return str(
                    data.get("message")
                    or data.get("msg")
                    or nested.get("message")
                    or nested.get("msg")
                    or f"服务返回码 {data['code']}"
                )
        if status >= 400:
            return f"发布服务 HTTP {status}"
        return ""

    async def _request(self, endpoint: str, payload: dict) -> dict:
        url = f"{self._base_url()}/{endpoint.lstrip('/')}"
        try:
            async with aiohttp.ClientSession(timeout=self._timeout()) as session:
                async with session.post(
                    url, json=payload, headers=self._headers()
                ) as response:
                    text = await response.text()
                    try:
                        data = json.loads(text) if text else {}
                    except json.JSONDecodeError as exc:
                        raise XiaohongshuPublishError(
                            "发布服务返回了无效 JSON"
                        ) from exc
                    error = self._response_error(data, response.status)
                    if error:
                        raise XiaohongshuPublishError(error)
                    if not isinstance(data, dict):
                        return {"data": data}
                    return data
        except asyncio.TimeoutError as exc:
            raise XiaohongshuPublishError("小红书发布服务请求超时") from exc
        except aiohttp.ClientError as exc:
            raise XiaohongshuPublishError(f"小红书发布服务连接失败: {exc}") from exc

    async def check_login(self) -> dict:
        return await self._request("check-login", {})

    async def publish(
        self,
        *,
        title: str,
        content: str,
        images: list[str] | None = None,
        tags: list[str] | None = None,
        visibility: str = "公开可见",
    ) -> dict:
        payload = {
            "title": str(title or "").strip(),
            "content": str(content or "").strip(),
            "images": self._media_values(images),
            "tags": [str(item).strip() for item in (tags or []) if str(item).strip()],
            "visibility": normalize_xiaohongshu_visibility(visibility),
        }
        if not payload["content"]:
            raise XiaohongshuPublishError("小红书正文不能为空")
        return await self._request("publish", payload)

    async def publish_video(
        self,
        *,
        title: str,
        content: str,
        video: str,
        tags: list[str] | None = None,
        visibility: str = "公开可见",
    ) -> dict:
        media = self._media_values([video])
        if not media:
            raise XiaohongshuPublishError("小红书视频路径不能为空")
        payload = {
            "title": str(title or "").strip(),
            "content": str(content or "").strip(),
            "video": media[0],
            "tags": [str(item).strip() for item in (tags or []) if str(item).strip()],
            "visibility": normalize_xiaohongshu_visibility(visibility),
        }
        if not payload["content"]:
            raise XiaohongshuPublishError("小红书正文不能为空")
        return await self._request("publish-video", payload)


__all__ = [
    "XiaohongshuClient",
    "XiaohongshuPublishError",
    "normalize_xiaohongshu_visibility",
]

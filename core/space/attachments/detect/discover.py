from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import aiohttp

from astrbot.api import logger

from ...models import QzoneContext


class QzoneAlbumProbeQueryMixin:
    """执行相册视频公开性探测请求。"""

    async def _probe_public_album_video_url(self, url: str) -> dict[str, Any]:
        target = str(url or "").strip()
        parsed = urlparse(target)
        if (parsed.scheme or "").lower() not in {"http", "https"}:
            return {"state": "missing_url", "reason": "unsupported_url"}
        host = (parsed.hostname or "").lower()
        if not any(marker in host for marker in self.APPID4_PUBLIC_VIDEO_URL_MARKERS):
            return {"state": "missing_url", "reason": "not_qzone_public_video_url"}
        timeout = aiohttp.ClientTimeout(total=max(5, min(self._api_timeout_seconds(), 15)))
        try:
            async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar(), timeout=timeout) as session:
                async with session.get(
                    target,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
                        "Accept": "video/*,*/*;q=0.8",
                        "Range": "bytes=0-2047",
                    },
                    allow_redirects=False,
                ) as resp:
                    content_type = str(resp.headers.get("Content-Type") or "").lower()
                    status = int(resp.status or 0)
        except Exception as exc:
            return {"state": "error", "reason": exc.__class__.__name__}
        if status in self.APPID4_PUBLIC_VIDEO_URL_STATUS_CODES and (
            not content_type or "video" in content_type or "octet-stream" in content_type
        ):
            return {"state": "success", "status_code": status, "content_type": content_type}
        if status in {301, 302, 303, 307, 308, 401, 403, 404, 410} or status >= 400:
            return {"state": "denied", "status_code": status, "content_type": content_type}
        return {"state": "error", "reason": "unexpected_response", "status_code": status, "content_type": content_type}

    async def _album_video_public_probes(
        self,
        ctx: QzoneContext,
        album_id: str,
        photo_key: str,
    ) -> list[tuple[str, Any]]:
        probes: list[tuple[str, Any]] = []
        if album_id and photo_key:
            try:
                probes.append(("floatview", await self._query_qzone_photo_floatview(ctx, album_id, photo_key)))
            except Exception as exc:
                logger.debug(f"[每日分享] QQ 空间相册视频浮层视图接口探测失败: {exc}")
        if album_id:
            try:
                probes.append(("photo_list", await self._query_qzone_album_photos(ctx, album_id, count=20)))
            except Exception as exc:
                logger.debug(f"[每日分享] QQ 空间相册视频列表探测失败: {exc}")
            try:
                probes.append(("album_info", await self._query_qzone_album_info(ctx, album_id)))
            except Exception as exc:
                logger.debug(f"[每日分享] QQ 空间相册信息探测失败: {exc}")
        try:
            probes.append(("video_get_data", await self._query_qzone_video_library(ctx, start=0, count=20)))
        except Exception as exc:
            logger.debug(f"[每日分享] QQ 空间视频库探测失败: {exc}")
        return probes

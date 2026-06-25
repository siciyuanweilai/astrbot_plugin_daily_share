from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from astrbot.api import logger

from ..models import QzoneContext


class QzoneAlbumBaseMixin:
    """相册接口通用辅助。"""

    @staticmethod
    def _album_video_dynamic_failure(uploaded: dict[str, Any]) -> str:
        if not uploaded.get("cover_upload_result"):
            return "QQ 空间本地视频已上传，但未生成相册视频动态（缺少封面或封面上传失败）"
        return "QQ 空间本地视频已上传到相册，但未确认相册视频可公开展示"

    @staticmethod
    def _image_size(path: str | Path = "", data: bytes | None = None) -> tuple[int, int]:
        try:
            from PIL import Image

            if data is not None:
                import io

                with Image.open(io.BytesIO(data)) as image:
                    return int(image.width or 0), int(image.height or 0)
            if path:
                with Image.open(path) as image:
                    return int(image.width or 0), int(image.height or 0)
        except Exception:
            return 0, 0
        return 0, 0

    @staticmethod
    def _qzone_raw_uin(ctx: QzoneContext) -> str:
        return str(ctx.uin).removeprefix("o")

    @staticmethod
    def _qzone_cookie_uin(ctx: QzoneContext) -> str:
        return str(ctx.uin).removeprefix("o")

    def _qzone_photo_api_headers(
        self,
        ctx: QzoneContext,
        *,
        full: bool = False,
        cookie: str = "",
    ) -> dict[str, str]:
        return {
            "Cookie": cookie or (self._h5_cookie_header(ctx) if full else self._h5_minimal_cookie_header(ctx)),
            "Referer": f"{self.BASE_URL}/{ctx.uin}/photo",
            "Origin": self.BASE_URL,
            "User-Agent": self._headers(ctx).get("User-Agent", ""),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "max-age=0",
        }

    def _qzone_photo_minimal_api_headers(self, ctx: QzoneContext) -> dict[str, str]:
        return self._qzone_photo_api_headers(ctx)

    def _qzone_photo_api_header_variants(
        self,
        ctx: QzoneContext,
        *,
        prefer_full: bool = False,
    ) -> list[tuple[str, dict[str, str]]]:
        variants = [
            ("minimal", self._qzone_photo_api_headers(ctx)),
            ("full", self._qzone_photo_api_headers(ctx, full=True)),
            ("full-o", self._qzone_photo_api_headers(ctx, cookie=self._h5_cookie_header(ctx, o_prefix=True))),
            (
                "minimal-o",
                self._qzone_photo_api_headers(
                    ctx,
                    cookie=self._h5_minimal_cookie_header(ctx, o_prefix=True),
                ),
            ),
        ]
        if prefer_full:
            order = {"full": 0, "full-o": 1, "minimal": 2, "minimal-o": 3}
            variants.sort(key=lambda item: order.get(item[0], 99))
        unique: list[tuple[str, dict[str, str]]] = []
        seen: set[str] = set()
        for name, headers in variants:
            cookie = headers.get("Cookie", "")
            if cookie in seen:
                continue
            seen.add(cookie)
            unique.append((name, headers))
        return unique

    @classmethod
    def _qzone_login_retry_needed(cls, payload: dict[str, Any]) -> bool:
        try:
            status = int(payload.get("_http_status") or 0)
        except (TypeError, ValueError):
            status = 0
        if status in {401, 403} or payload.get("code") in {-100, -3000}:
            return True
        text = json.dumps(payload, ensure_ascii=False, default=str)
        return cls._h5_login_expired_message(text)

    async def _qzone_request_with_cookie_variants(
        self,
        ctx: QzoneContext,
        method: str,
        url: str,
        *,
        params_factory,
        data=None,
        retry_login: bool = True,
        prefer_full_cookie: bool = False,
    ) -> dict[str, Any]:
        attempts: list[tuple[QzoneContext, str, dict[str, str]]] = [
            (ctx, name, headers)
            for name, headers in self._qzone_photo_api_header_variants(ctx, prefer_full=prefer_full_cookie)
        ]
        refreshed = False
        last_payload: dict[str, Any] = {}
        while attempts:
            current_ctx, cookie_mode, headers = attempts.pop(0)
            params = params_factory(current_ctx) if callable(params_factory) else params_factory
            payload = await self._request(
                method,
                url,
                params=params,
                data=data,
                headers=headers,
                retry=False,
            )
            if not self._qzone_login_retry_needed(payload):
                if cookie_mode != "minimal":
                    logger.debug(f"[每日分享] QQ 空间接口已使用 {cookie_mode} 登录凭据通过登录校验。")
                return payload
            last_payload = payload
            if retry_login and not refreshed and not attempts:
                refreshed = True
                self.invalidate()
                fresh_ctx = await self.context()
                attempts.extend(
                    (fresh_ctx, name, headers)
                    for name, headers in self._qzone_photo_api_header_variants(
                        fresh_ctx,
                        prefer_full=prefer_full_cookie,
                    )
                )
        return last_payload

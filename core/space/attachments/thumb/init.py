from __future__ import annotations

from typing import Any

from astrbot.api import logger

from ...models import QzoneContext


class QzoneVideoCoverInitMixin:
    """初始化 QQ 空间视频封面上传会话。"""

    async def _init_video_cover_upload(
        self,
        ctx: QzoneContext,
        checksum: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        try:
            return await self._h5_post_json(
                ctx,
                f"{self.H5_FILE_BATCH_CONTROL_URL}/{checksum}",
                payload,
                params={"g_tk": ctx.gtk},
                label="cover-init",
                prefer_native_h2=True,
                headers=headers,
            )
        except Exception as exc:
            message = self._with_h5_phase(exc, "cover-init")
            if self._h5_login_expired_message(message):
                return {"ret": -3000, "msg": message}
            raise RuntimeError(message) from exc

    async def _init_video_cover_upload_with_cookie_variants(
        self,
        ctx: QzoneContext,
        checksum: str,
        payload: dict[str, Any],
    ) -> tuple[QzoneContext, dict[str, str], dict[str, Any]]:
        attempts: list[tuple[QzoneContext, str, dict[str, str]]] = [
            (ctx, name, headers) for name, headers in self._h5_cookie_variants(ctx)
        ]
        refreshed = False
        init: dict[str, Any] | None = None
        cover_headers: dict[str, str] | None = None
        cover_ctx = ctx
        last_login_error = ""
        while attempts:
            current_ctx, cookie_mode, request_headers = attempts.pop(0)
            cover_ctx = current_ctx
            cover_headers = request_headers
            init = await self._init_video_cover_upload(current_ctx, checksum, payload, request_headers)
            if self._h5_ok(init):
                if cookie_mode != "minimal":
                    logger.debug(f"[每日分享] QQ 空间视频封面上传已使用 {cookie_mode} 登录凭据通过登录校验。")
                break
            error_message = self._h5_error_message(init, "QQ 空间视频封面上传初始化失败")
            if not self._h5_login_expired(init):
                raise RuntimeError(error_message)
            last_login_error = error_message
            if not refreshed and not attempts:
                refreshed = True
                self.invalidate()
                fresh_ctx = await self.context()
                attempts.extend((fresh_ctx, name, headers) for name, headers in self._h5_cookie_variants(fresh_ctx))
        else:
            raise RuntimeError(last_login_error or "QQ 空间视频封面上传初始化失败")

        if init is None or cover_headers is None:
            raise RuntimeError("QQ 空间视频封面上传初始化失败")
        return cover_ctx, cover_headers, init

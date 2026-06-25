from __future__ import annotations

import asyncio
from typing import Any

from astrbot.api import logger

from ..models import QzoneContext
from ..parse import parse_qzone_response


class QzoneH5RequestMixin:
    """H5 请求发送。"""

    async def _h5_post_json(
        self,
        ctx: QzoneContext,
        url: str,
        payload: dict[str, Any],
        *,
        params: dict[str, Any] | None = None,
        label: str = "",
        prefer_native_h2: bool = False,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request_headers = headers or self._h5_headers(ctx)
        use_h2 = True
        if prefer_native_h2:
            try:
                logger.debug("[每日分享] QQ 空间视频封面上传将尝试原生 HTTP/2。")
                status, text = await self._h5_post_json_native_h2(ctx, url, payload, params=params, headers=request_headers)
                parsed = self._annotate_h5_response(
                    parse_qzone_response(text),
                    status=status,
                    text=text,
                    label=label,
                    transport="native HTTP/2",
                )
                if status in {401, 403}:
                    return parsed
                if self._h5_should_retry_same_transport(status):
                    logger.debug(
                        f"[每日分享] QQ 空间原生 HTTP/2 上传返回 {status}，改用 HTTP/1.1 重试: "
                        f"阶段={label or '-'}"
                    )
                    use_h2 = False
                elif parsed.get("code") != -1:
                    return parsed
                else:
                    logger.debug(
                        f"[每日分享] QQ 空间原生 HTTP/2 上传响应为空或不可解析，将改用备用请求客户端: "
                        f"阶段={label or '-'}，状态码={status}，字节数={len(text or '')}"
                    )
            except Exception as exc:
                logger.debug(
                    f"[每日分享] QQ 空间原生 HTTP/2 上传失败，将改用备用请求客户端: "
                    f"阶段={label or '-'}，错误={exc}"
                )

        body = self._h5_json_body(payload)
        return await self._h5_post_body(
            ctx,
            url,
            body,
            params=params,
            label=label,
            headers=request_headers,
            use_h2=use_h2,
        )

    async def _h5_post_bytes(
        self,
        ctx: QzoneContext,
        url: str,
        body: bytes,
        content_type: str,
        *,
        params: dict[str, Any] | None = None,
        label: str = "",
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request_headers = dict(headers or self._h5_headers(ctx))
        request_headers["Content-Type"] = content_type

        return await self._h5_post_body(
            ctx,
            url,
            body,
            params=params,
            label=label,
            headers=request_headers,
            use_h2=True,
        )

    async def _h5_post_body_once(
        self,
        ctx: QzoneContext,
        url: str,
        body: bytes,
        *,
        params: dict[str, Any] | None,
        headers: dict[str, str],
        use_h2: bool,
    ) -> tuple[int, str, str]:
        if use_h2:
            h2_session = await self._h2_http()
            if h2_session is not None:
                resp = await h2_session.post(url, params=params, content=body, headers=headers)
                return resp.status_code, resp.text, "HTTP/2"

        session = await self._http()
        async with session.post(
            url,
            params=params,
            data=body,
            headers={
                **self._h5_aiohttp_headers(ctx),
                **headers,
            },
        ) as resp:
            return resp.status, await resp.text(), "HTTP/1.1"

    async def _h5_post_body(
        self,
        ctx: QzoneContext,
        url: str,
        body: bytes,
        *,
        params: dict[str, Any] | None = None,
        label: str = "",
        headers: dict[str, str],
        use_h2: bool = True,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                status, text, transport = await self._h5_post_body_once(
                    ctx,
                    url,
                    body,
                    params=params,
                    headers=headers,
                    use_h2=use_h2,
                )
            except Exception as exc:
                mapped_error = self._h5_transport_error(exc, phase=label)
                if mapped_error is None:
                    raise
                last_error = mapped_error
            else:
                parsed = self._annotate_h5_response(
                    parse_qzone_response(text),
                    status=status,
                    text=text,
                    label=label,
                    transport=transport,
                )
                if parsed.get("code") == -1:
                    preview = str(text or "").strip().replace("\n", " ")[:160]
                    logger.debug(
                        f"[每日分享] QQ 空间 H5 上传响应不可解析: 阶段={label or '-'}，"
                        f"状态码={status}，字节数={len(text or '')}，传输={transport}，响应片段={preview}"
                    )
                if status in {401, 403}:
                    raise RuntimeError(f"QQ 空间 H5 上传登录态失效（HTTP {status}）")
                if self._h5_should_retry_http11(status, transport) and use_h2:
                    last_error = RuntimeError(self._h5_error_message(parsed, f"QQ 空间 H5 上传接口暂不可用（HTTP {status}）"))
                    logger.debug(
                        f"[每日分享] QQ 空间 H5 上传 HTTP/2 返回 {status}，改用 HTTP/1.1 重试: "
                        f"阶段={label or '-'}"
                    )
                    use_h2 = False
                elif self._h5_should_retry_same_transport(status):
                    last_error = RuntimeError(self._h5_error_message(parsed, f"QQ 空间 H5 上传接口暂不可用（HTTP {status}）"))
                else:
                    return parsed

            if attempt < 2:
                await asyncio.sleep(1)
        raise last_error or RuntimeError("QQ 空间 H5 上传请求失败")

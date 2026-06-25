from __future__ import annotations

import asyncio
import importlib.util
import time
from typing import Any

import aiohttp

try:
    import httpx
except Exception:  # pragma: no cover - ???????
    httpx = None

from astrbot.api import logger

from .models import QzoneContext
from .parse import parse_qzone_response
from .transport import QzoneHeaderMixin


class QzoneClientServiceMixin(QzoneHeaderMixin):
    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        if self._h2_session is not None:
            await self._h2_session.aclose()
        self._session = None
        self._h2_session = None
        self._session_timeout_seconds = None
        self._h2_timeout_seconds = None
        self._h5_transport = ""
        self._h5_transport_logged = False

    def invalidate(self) -> None:
        self._ctx = None
        self._ctx_at = 0.0

    def configured(self) -> bool:
        return bool(self._get_bot())

    async def status(self) -> dict:
        try:
            ctx = await self.context()
            return {
                "available": True,
                "configured": True,
                "uin": ctx.uin,
                "nickname": ctx.nickname or str(ctx.uin),
            }
        except Exception as exc:
            return {
                "available": False,
                "configured": bool(self._get_bot()),
                "uin": 0,
                "nickname": "",
                "error": str(exc),
            }

    async def context(self) -> QzoneContext:
        if self._ctx and time.monotonic() - self._ctx_at < self.COOKIE_TTL_SECONDS:
            return self._ctx

        cookie = await self._fetch_bot_cookie()
        ctx = await self._context_from_cookie(cookie)
        self._ctx = ctx
        self._ctx_at = time.monotonic()
        return ctx

    def _get_bot(self):
        adapter_id = str(getattr(self.plugin, "_cached_qq_adapter_id", "") or "")
        bot = self.plugin.ctx_service._get_bot_instance(adapter_id)
        if bot:
            return bot
        bot_map = getattr(self.plugin.ctx_service, "bot_map", {}) or {}
        onebot_bots = [
            item
            for key, item in bot_map.items()
            if self.plugin.ctx_service._is_onebot_platform(str(key))
        ]
        if len(onebot_bots) == 1:
            return onebot_bots[0]
        return self.plugin.ctx_service._get_onebot_bot(target_umo="0", adapter_id=adapter_id)

    async def _fetch_bot_cookie(self) -> str:
        bot = self._get_bot()
        if not bot:
            raise RuntimeError("没有可用的机器人客户端，无法自动获取 QQ 空间登录态")
        if not hasattr(bot, "get_cookies"):
            raise RuntimeError("当前机器人客户端不支持读取登录态")
        values: dict[str, str] = {}
        for domain in self.QZONE_COOKIE_DOMAINS:
            try:
                payload = await bot.get_cookies(domain=domain)
            except Exception as exc:
                logger.debug(f"[每日分享] 读取 QQ 空间登录凭据失败({domain}): {exc}")
                continue
            cookie = str(payload.get("cookies") or "").strip() if isinstance(payload, dict) else ""
            domain_values = self._cookie_values_from_header(cookie)
            if not domain_values:
                continue
            values.update(domain_values)
            logger.debug(
                f"[每日分享] QQ 空间登录凭据字段({domain}): "
                f"{','.join(sorted(domain_values))}"
            )
        if not values:
            raise RuntimeError("机器人客户端未返回 QQ 空间登录态，请确认账号已登录且适配器支持读取登录态")
        return self._cookie_header_from_values(values)

    async def _context_from_cookie(self, cookie: str) -> QzoneContext:
        values = self._cookie_values_from_header(cookie)
        uin_text = str(values.get("uin") or values.get("p_uin") or values.get("pt2gguin") or "0")
        uin_text = uin_text[1:] if uin_text.lower().startswith("o") else uin_text
        uin = int(uin_text) if uin_text.isdigit() else 0
        p_skey = values.get("p_skey") or values.get("skey") or ""
        skey = values.get("skey") or p_skey
        if not uin or not p_skey:
            raise RuntimeError("机器人客户端返回的 QQ 空间登录态缺少账号标识或密钥")
        nickname = await self._bot_nickname(str(uin))
        return QzoneContext(
            uin=uin,
            skey=skey,
            p_skey=p_skey,
            nickname=nickname,
            cookie_values=values,
        )

    async def _bot_nickname(self, fallback: str) -> str:
        bot = self._get_bot()
        if not bot or not hasattr(bot, "get_login_info"):
            return fallback
        try:
            info = await bot.get_login_info()
            return str(info.get("nickname") or fallback) if isinstance(info, dict) else fallback
        except Exception:
            return fallback

    async def _http(self) -> aiohttp.ClientSession:
        timeout_seconds = self._api_timeout_seconds()
        if (
            self._session
            and not self._session.closed
            and self._session_timeout_seconds != timeout_seconds
        ):
            await self._session.close()
            self._session = None
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout_seconds)
            )
            self._session_timeout_seconds = timeout_seconds
        return self._session

    async def _h2_http(self):
        if httpx is None or importlib.util.find_spec("h2") is None:
            if not self._h5_transport_logged:
                logger.warning("[每日分享] QQ 空间 H5 上传未启用 HTTP/2，已退回 HTTP/1.1；视频封面接口可能返回为空。")
                self._h5_transport_logged = True
            self._h5_transport = "HTTP/1.1"
            return None
        timeout_seconds = self._api_timeout_seconds()
        if self._h2_session is not None and self._h2_timeout_seconds != timeout_seconds:
            await self._h2_session.aclose()
            self._h2_session = None
            self._h2_timeout_seconds = None
        if self._h2_session is None:
            try:
                self._h2_session = httpx.AsyncClient(
                    http2=True,
                    timeout=timeout_seconds,
                    headers={"accept-encoding": "gzip"},
                )
                self._h2_timeout_seconds = timeout_seconds
            except ImportError:
                self._h5_transport = "HTTP/1.1"
                return None
        if not self._h5_transport_logged:
            logger.info("[每日分享] QQ 空间 H5 上传已启用 HTTP/2。")
            self._h5_transport_logged = True
        self._h5_transport = "HTTP/2"
        return self._h2_session

    def _api_timeout_seconds(self) -> int:
        conf = getattr(self.plugin, "qzone_conf", {}) or {}
        try:
            value = int(conf.get("qzone_api_timeout_seconds", self.API_TIMEOUT_SECONDS))
        except (TypeError, ValueError):
            value = self.API_TIMEOUT_SECONDS
        return max(self.API_TIMEOUT_MIN_SECONDS, min(value, self.API_TIMEOUT_MAX_SECONDS))

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params=None,
        data=None,
        headers=None,
        retry=True,
        retry_parse_error=True,
    ) -> dict[str, Any]:
        ctx = await self.context()
        session = await self._http()
        request_headers = headers or self._headers(ctx)
        request_cookies = None if self._has_cookie_header(request_headers) else ctx.cookies
        try:
            async with session.request(
                method,
                url,
                params=params,
                data=data,
                headers=request_headers,
                cookies=request_cookies,
            ) as resp:
                text = await resp.text()
                status = resp.status
        except asyncio.TimeoutError as exc:
            raise RuntimeError(f"QQ 空间请求超时（{self._api_timeout_seconds()}秒）") from exc
        except aiohttp.ClientError as exc:
            raise RuntimeError(f"QQ 空间网络请求失败: {exc}") from exc
        payload = parse_qzone_response(text)
        payload["_http_status"] = status
        payload["_raw_length"] = len(text or "")
        retryable_parse_error = (
            retry_parse_error
            and payload.get("code") == -1
            and str(payload.get("message") or "").startswith("QQ 空间")
        )
        if retry and (status in {401, 403} or payload.get("code") in {-100, -3000} or retryable_parse_error):
            if retryable_parse_error:
                preview = str(text or "").strip().replace("\n", " ")[:120]
                logger.debug(f"[每日分享] QQ 空间返回暂不可解析，刷新登录态后重试。接口状态码 {status}，响应片段: {preview}")
            self.invalidate()
            return await self._request(
                method,
                url,
                params=params,
                data=data,
                headers=headers,
                retry=False,
                retry_parse_error=retry_parse_error,
            )
        return payload

    async def _request_text(
        self,
        method: str,
        url: str,
        *,
        params=None,
        data=None,
        headers=None,
        retry=True,
    ) -> str:
        ctx = await self.context()
        session = await self._http()
        request_headers = headers or self._headers(ctx)
        request_cookies = None if self._has_cookie_header(request_headers) else ctx.cookies
        try:
            async with session.request(
                method,
                url,
                params=params,
                data=data,
                headers=request_headers,
                cookies=request_cookies,
            ) as resp:
                text = await resp.text()
                status = resp.status
        except asyncio.TimeoutError as exc:
            raise RuntimeError(f"QQ 空间请求超时（{self._api_timeout_seconds()}秒）") from exc
        except aiohttp.ClientError as exc:
            raise RuntimeError(f"QQ 空间网络请求失败: {exc}") from exc
        if retry and status in {401, 403}:
            self.invalidate()
            return await self._request_text(
                method,
                url,
                params=params,
                data=data,
                headers=headers,
                retry=False,
            )
        if status >= 400:
            raise RuntimeError(f"QQ 空间请求失败，接口状态码: {status}")
        return text

    @staticmethod
    def _ok(payload: dict[str, Any], *, code_key: str = "code") -> bool:
        if not isinstance(payload, dict):
            return False
        for key in (code_key, "code", "ret"):
            if key not in payload or payload.get(key) in (None, ""):
                continue
            try:
                return int(payload.get(key) or 0) == 0
            except (TypeError, ValueError):
                return False
        return True

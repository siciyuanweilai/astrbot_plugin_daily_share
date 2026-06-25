from __future__ import annotations

import asyncio
import re
from typing import Any

import aiohttp

try:
    import httpx
except Exception:  # pragma: no cover - 可选运行时依赖
    httpx = None


class QzoneH5ErrorMixin:
    """H5 传输错误识别与格式化。"""

    def _h5_error_message(self, payload: dict[str, Any], fallback: str) -> str:
        try:
            status = int(payload.get("_http_status") or 0)
        except (TypeError, ValueError):
            status = 0
        code = payload.get("ret", payload.get("code"))
        if code == -1 and (status == 429 or status >= 500):
            message = fallback
        else:
            message = self._qzone_error_message(
                {
                    "code": code,
                    "message": payload.get("msg") or payload.get("message"),
                    "data": payload.get("data") if isinstance(payload.get("data"), dict) else {},
                },
                fallback,
            )
        detail = []
        if payload.get("_endpoint"):
            detail.append(f"阶段: {payload['_endpoint']}")
        if status:
            detail.append(f"HTTP {status}")
        if payload.get("_raw_length") is not None:
            detail.append(f"响应 {payload['_raw_length']} bytes")
        if payload.get("_transport"):
            detail.append(f"传输: {payload['_transport']}")
        return f"{message}（{'，'.join(detail)}）" if detail else message

    @classmethod
    def _h5_transient_or_unstructured_failure(cls, payload: dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        try:
            status = int(payload.get("_http_status") or 0)
        except (TypeError, ValueError):
            status = 0
        if status == 429 or status >= 500:
            return True
        if payload.get("code") == -1 and bool(payload.get("_raw_length")):
            return True
        return any(
            cls._h5_transient_or_unstructured_message(payload.get(key))
            for key in ("msg", "message", "error")
        )

    @staticmethod
    def _h5_transient_or_unstructured_message(message: Any) -> bool:
        text = str(message or "")
        if not text:
            return False
        if re.search(r"HTTP\s*(?:429|5\d\d)", text, flags=re.IGNORECASE):
            return True
        return any(
            token in text
            for token in (
                "H5 上传接口暂不可用",
                "返回内容不是结构化数据",
                "响应不可解析",
                "Gateway Time-out",
                "Gateway Timeout",
                "openresty",
            )
        )

    @staticmethod
    def _h5_login_expired_message(message: Any) -> bool:
        text = str(message or "")
        return any(token in text for token in ("尚未登录", "登录超时", "请先登录", "登录态失效"))

    @classmethod
    def _h5_login_expired(cls, payload: dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        try:
            status = int(payload.get("_http_status") or 0)
        except (TypeError, ValueError):
            status = 0
        if status in {401, 403}:
            return True
        return cls._h5_login_expired_message(
            payload.get("msg")
            or payload.get("message")
            or (
                payload.get("data", {}).get("msg")
                if isinstance(payload.get("data"), dict)
                else ""
            )
            or (
                payload.get("data", {}).get("message")
                if isinstance(payload.get("data"), dict)
                else ""
            )
        )

    def _with_h5_phase(self, message: Any, phase: str) -> str:
        text = str(message or "").strip() or "QQ 空间 H5 上传失败"
        if "阶段:" in text:
            return text
        detail = [f"阶段: {phase}"]
        if self._h5_transport:
            detail.append(f"传输: {self._h5_transport}")
        return f"{text}（{'，'.join(detail)}）"

    @staticmethod
    def _h5_should_retry_http11(status: int, transport: str) -> bool:
        return transport == "HTTP/2" and (status in {429, 502, 503, 504} or status >= 500)

    @staticmethod
    def _h5_should_retry_same_transport(status: int) -> bool:
        return status == 429 or status >= 500

    def _h5_transport_error(
        self,
        exc: BaseException,
        *,
        phase: str,
    ) -> RuntimeError | None:
        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
            return RuntimeError(f"QQ 空间 H5 上传请求超时（{self._api_timeout_seconds()}秒）")
        if httpx is not None and isinstance(exc, httpx.TimeoutException):
            return RuntimeError(f"QQ 空间 H5 上传请求超时（{self._api_timeout_seconds()}秒）")
        if httpx is not None and isinstance(exc, httpx.HTTPError):
            return RuntimeError(f"QQ 空间 H5 上传网络请求失败: {exc}")
        if isinstance(exc, aiohttp.ClientError):
            return RuntimeError(f"QQ 空间 H5 上传网络请求失败: {exc}")
        return None

from __future__ import annotations

from http.cookies import SimpleCookie
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import QzoneContext


class QzoneHeaderMixin:
    @staticmethod
    def _cookie_values_from_header(cookie: str) -> dict[str, str]:
        text = str(cookie or "").strip()
        if not text:
            return {}
        values: dict[str, str] = {}
        try:
            values.update({key: morsel.value for key, morsel in SimpleCookie(text).items()})
        except Exception:
            values = {}
        if values:
            return {key: value for key, value in values.items() if key and value not in (None, "")}

        for part in text.split(";"):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key and value:
                values[key] = value
        return values

    @staticmethod
    def _cookie_header_from_values(values: dict[str, str]) -> str:
        return ";".join(
            f"{key}={value}"
            for key, value in (values or {}).items()
            if str(key).strip() and value not in (None, "")
        )

    def _headers(self, ctx: "QzoneContext", **extra) -> dict[str, str]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "Referer": f"{self.BASE_URL}/{ctx.uin}",
            "Origin": self.BASE_URL,
        }
        headers.update({key: value for key, value in extra.items() if value})
        return headers

    def _pc_form_headers(self, ctx: "QzoneContext", *, referer: str = "") -> dict[str, str]:
        return self._headers(
            ctx,
            Referer=referer or f"{self.BASE_URL}/{ctx.uin}/main",
            Origin=self.BASE_URL,
            Accept="text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            **{
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cache-Control": "max-age=0",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-site",
            },
        )

    def _comment_h5_headers(self, ctx: "QzoneContext", *, referer: str = "") -> dict[str, str]:
        return self._headers(
            ctx,
            Referer=referer or f"{self.H5_ORIGIN}/{ctx.uin}",
            Origin=self.H5_ORIGIN,
            Accept="application/json, text/plain, */*",
            **{
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "X-Requested-With": "XMLHttpRequest",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-site",
            },
        )

    def _comment_sns_headers(self, ctx: "QzoneContext", *, referer: str = "") -> dict[str, str]:
        return self._headers(
            ctx,
            Referer=referer or f"{self.BASE_URL}/{ctx.uin}/main",
            Accept="text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            **{
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cache-Control": "max-age=0",
                "Sec-Fetch-Dest": "iframe",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-site",
            },
        )

    def _feeds3_headers(self, ctx: "QzoneContext") -> dict[str, str]:
        return self._headers(
            ctx,
            Referer=f"{self.BASE_URL}/{ctx.uin}/main",
            Accept="application/json, text/javascript, */*; q=0.01",
            **{
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "X-Requested-With": "XMLHttpRequest",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            },
        )

    @staticmethod
    def _has_cookie_header(headers: dict[str, str] | None) -> bool:
        return any(str(key).lower() == "cookie" for key in (headers or {}))

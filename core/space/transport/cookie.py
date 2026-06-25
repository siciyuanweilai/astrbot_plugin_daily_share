from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import QzoneContext


class QzoneH5CookieMixin:
    @staticmethod
    def _h5_cookie_uin(ctx: "QzoneContext") -> str:
        return str(ctx.uin).removeprefix("o")

    def _h5_minimal_cookie_header(self, ctx: "QzoneContext", *, o_prefix: bool = False) -> str:
        raw_uin = self._h5_cookie_uin(ctx)
        cookie_uin = f"o{raw_uin}" if o_prefix and not raw_uin.startswith("o") else raw_uin
        return f"uin={cookie_uin};p_skey={ctx.p_skey}"

    def _h5_cookie_header(self, ctx: "QzoneContext", *, o_prefix: bool = False) -> str:
        cookies = {
            key: str(value)
            for key, value in (ctx.cookie_values or {}).items()
            if str(key).strip() and value not in (None, "")
        }
        cookie_uin = self._h5_cookie_uin(ctx)
        cookie_o_uin = f"o{cookie_uin}"
        normalized_uin = cookie_o_uin if o_prefix else cookie_uin
        cookies.update(
            {
                "uin": normalized_uin,
                "p_uin": normalized_uin,
                "pt2gguin": cookie_o_uin,
                "p_skey": ctx.p_skey,
            }
        )
        if ctx.skey:
            cookies.setdefault("skey", ctx.skey)
        return self._cookie_header_from_values(cookies)

    def _h5_headers(self, ctx: "QzoneContext") -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Cookie": self._h5_cookie_header(ctx),
        }

    def _h5_minimal_headers(self, ctx: "QzoneContext", *, o_prefix: bool = False) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Cookie": self._h5_minimal_cookie_header(ctx, o_prefix=o_prefix),
        }

    def _h5_cookie_variants(self, ctx: "QzoneContext") -> list[tuple[str, dict[str, str]]]:
        variants: list[tuple[str, dict[str, str]]] = [
            ("minimal", self._h5_minimal_headers(ctx)),
            ("full", self._h5_headers(ctx)),
            ("full-o", {"Content-Type": "application/json", "Cookie": self._h5_cookie_header(ctx, o_prefix=True)}),
        ]
        raw_uin = self._h5_cookie_uin(ctx)
        if raw_uin:
            variants.append(("minimal-o", self._h5_minimal_headers(ctx, o_prefix=True)))

        unique: list[tuple[str, dict[str, str]]] = []
        seen: set[str] = set()
        for name, headers in variants:
            cookie = headers.get("Cookie", "")
            if cookie in seen:
                continue
            seen.add(cookie)
            unique.append((name, headers))
        return unique

    def _h5_aiohttp_headers(self, ctx: "QzoneContext") -> dict[str, str]:
        headers = self._h5_headers(ctx)
        headers.update(
            {
                "Referer": f"{self.H5_ORIGIN}/",
                "Origin": self.H5_ORIGIN,
                "Accept": "application/json, text/plain, */*",
            }
        )
        return headers

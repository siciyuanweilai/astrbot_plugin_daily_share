from __future__ import annotations

from typing import Any

from ..models import QzonePost
from ..parse import parse_feed_item


class QzoneFeedDetailMixin:
    """说说详情查询。"""

    async def detail(self, post_id: str) -> QzonePost:
        post = self._require_post(post_id)
        ctx = await self.context()
        referer = f"{self.BASE_URL}/{post.uin}/mood/{post.tid}"
        attempts = (
            (
                "POST",
                self.DETAIL_URL,
                {"g_tk": ctx.gtk2},
                {
                    "uin": post.uin,
                    "tid": post.tid,
                    "format": "json",
                    "hostuin": ctx.uin,
                    "qzreferrer": referer,
                },
            ),
            (
                "GET",
                self.DETAIL_URL,
                {
                    "g_tk": ctx.gtk2,
                    "uin": post.uin,
                    "tid": post.tid,
                    "format": "json",
                    "hostuin": ctx.uin,
                    "qzreferrer": referer,
                },
                None,
            ),
            (
                "GET",
                self.DETAIL_H5_URL,
                {
                    "uin": post.uin,
                    "tid": post.tid,
                    "num": 100,
                    "pos": 0,
                    "not_trunc_con": 1,
                    "format": "json",
                    "g_tk": ctx.gtk2,
                },
                None,
            ),
        )
        last_message = ""
        parsed = None
        for method, url, params, data in attempts:
            payload = await self._request(
                method,
                url,
                params=params,
                data=data,
                headers=self._headers(ctx, Referer=referer),
                retry_parse_error=False,
            )
            if not self._ok(payload):
                last_message = str(payload.get("message") or payload.get("msg") or "获取 QQ 空间详情失败")
                continue
            parsed = self._parse_detail_post(payload)
            if parsed:
                break
        if not parsed:
            raise RuntimeError(last_message or "QQ 空间详情解析失败")
        self._remember_posts([parsed])
        return parsed

    @staticmethod
    def _parse_detail_post(payload: dict[str, Any]) -> QzonePost | None:
        candidates: list[dict[str, Any]] = []

        def add(candidate: Any) -> None:
            if isinstance(candidate, dict):
                candidates.append(candidate)
            elif isinstance(candidate, list):
                for item in candidate:
                    if isinstance(item, dict):
                        candidates.append(item)
                        break

        data = payload.get("data") if isinstance(payload, dict) else None
        add(payload)
        add(data)
        if isinstance(data, dict):
            add(data.get("data"))
            add(data.get("detail"))
            add(data.get("msglist"))
        add(payload.get("detail") if isinstance(payload, dict) else None)
        add(payload.get("msglist") if isinstance(payload, dict) else None)

        for candidate in candidates:
            parsed = parse_feed_item(candidate)
            if parsed:
                return parsed
        return None

    async def _safe_post_detail(self, post: QzonePost) -> QzonePost | None:
        try:
            return await self.detail(post.key)
        except Exception:
            return None

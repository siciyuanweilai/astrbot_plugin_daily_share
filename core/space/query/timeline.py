from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

from ..models import QzoneContext, QzonePost


class QzoneFeedQueryMixin:
    def _recent_posts_params(self, ctx: QzoneContext, *, count: int, cursor: str = "") -> dict[str, Any]:
        params = {
            "uin": ctx.uin,
            "scope": 0,
            "view": 1,
            "filter": "all",
            "flag": 1,
            "applist": "all",
            "pagenum": 1,
            "aisortEndTime": 0,
            "aisortOffset": 0,
            "aisortBeginTime": 0,
            "begintime": 0,
            "format": "json",
            "g_tk": ctx.gtk2,
            "useutf8": 1,
            "outputhtmlfeed": 1,
        }
        if count > 0:
            params["count"] = count
        if cursor:
            cursor_params = parse_qs(str(cursor), keep_blank_values=True)
            page_values = cursor_params.get("pagenum") or []
            basetime_values = cursor_params.get("basetime") or []
            if page_values:
                params["pagenum"] = page_values[0]
            if basetime_values:
                params["begintime"] = basetime_values[0]
            params["externparam"] = cursor
        return params

    def _friend_feeds_params(self, ctx: QzoneContext, *, count: int, cursor: str = "") -> dict[str, Any]:
        return self._recent_posts_params(ctx, count=count, cursor=cursor)

    @staticmethod
    def _friend_feeds_next_cursor(payload: dict[str, Any]) -> str:
        data = payload.get("data") if isinstance(payload, dict) else {}
        main = data.get("main") if isinstance(data, dict) and isinstance(data.get("main"), dict) else {}
        for value in (
            main.get("externparam") if isinstance(main, dict) else "",
            data.get("externparam") if isinstance(data, dict) else "",
            payload.get("externparam") if isinstance(payload, dict) else "",
        ):
            text = str(value or "").strip()
            if text:
                return text
        return ""

    @staticmethod
    def _friend_feeds_has_more(payload: dict[str, Any], posts: list[QzonePost]) -> bool:
        data = payload.get("data") if isinstance(payload, dict) else {}
        main = data.get("main") if isinstance(data, dict) and isinstance(data.get("main"), dict) else {}
        if isinstance(main, dict) and "hasMoreFeeds" in main:
            return bool(main.get("hasMoreFeeds")) and bool(posts)
        if isinstance(data, dict) and "hasMoreFeeds" in data:
            return bool(data.get("hasMoreFeeds")) and bool(posts)
        return bool(posts)

    @staticmethod
    def _friend_feeds_payload_meta(payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else {}
        main = data.get("main") if isinstance(data, dict) and isinstance(data.get("main"), dict) else {}
        data_items = data.get("data") if isinstance(data, dict) else []
        feed_data_count = 0
        html_string_count = 0
        if isinstance(payload, dict):
            stack = [payload]
            while stack:
                value = stack.pop()
                if isinstance(value, dict):
                    stack.extend(value.values())
                elif isinstance(value, list):
                    stack.extend(value)
                elif isinstance(value, str) and "feed_data" in value:
                    html_string_count += 1
                    feed_data_count += value.count("feed_data")
        return {
            "payload_keys": sorted(str(key) for key in payload.keys())[:20] if isinstance(payload, dict) else [],
            "data_keys": sorted(str(key) for key in data.keys())[:30] if isinstance(data, dict) else [],
            "main_keys": sorted(str(key) for key in main.keys())[:30] if isinstance(main, dict) else [],
            "data_item_count": len(data_items) if isinstance(data_items, list) else 0,
            "feed_data_count": feed_data_count,
            "html_string_count": html_string_count,
        }

    @property
    def last_friend_feeds_meta(self) -> dict[str, Any]:
        return dict(self._last_friend_feeds_meta or {})

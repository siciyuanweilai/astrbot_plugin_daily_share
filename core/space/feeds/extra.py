from __future__ import annotations

import time
import re
from datetime import datetime
from typing import Any

from ..entry import parse_about_me, parse_favorites, parse_last_year, parse_message_board
from ..models import QzonePost
from ..parse import parse_recent_feed_list
from ..relation import parse_qzone_relations, parse_qzone_visit_stats


def _about_me_feed_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else {}
    items = data.get("data") if isinstance(data, dict) else []
    return [item for item in items if isinstance(item, dict)]


def _is_mention_feed_item(item: dict[str, Any], self_uin: int) -> bool:
    appid = str(item.get("appid") or "311").strip()
    if appid and appid != "311":
        return False
    html = str(item.get("html") or "")
    if not self_uin:
        return False
    body_pattern = re.compile(
        r'<(?:p|div)\b[^>]*class=(?P<quote>["\'])[^"\']*\b(?:txt-box-title|txt-box|content-box|qz_summary)\b[^"\']*(?P=quote)[^>]*>.*?</(?:p|div)>',
        re.I | re.S,
    )
    body_blocks = [match.group(0) for match in body_pattern.finditer(html)]
    if not body_blocks:
        return False
    pattern = re.compile(
        rf'<a\b[^>]*(?:link|href)=["\'][^"\']*nameCard_{int(self_uin)}\b[^"\']*["\'][^>]*>(.*?)</a>',
        re.I | re.S,
    )
    for block in body_blocks:
        for label in pattern.findall(block):
            if "@" in label:
                return True
    return False


class QzoneFeedExtraMixin:
    """空间附属页面查询。"""

    async def query_about_me(self, *, offset: int = 0, count: int = 10) -> dict[str, Any]:
        ctx = await self.context()
        limit = max(1, min(int(count or 10), 20))
        payload = await self._request(
            "GET",
            self.ABOUT_ME_URL,
            params={
                "uin": ctx.uin,
                "begin_time": 0,
                "end_time": 0,
                "getappnotification": 1,
                "getnotifi": 1,
                "has_get_key": 0,
                "offset": max(0, int(offset or 0)),
                "set": 0,
                "count": limit,
                "useutf8": 1,
                "outputhtmlfeed": 1,
                "grz": time.time(),
                "scope": 1,
                "g_tk": ctx.gtk,
            },
            headers=self._headers(ctx, Referer=f"{self.BASE_URL}/{ctx.uin}"),
        )
        if not self._ok(payload):
            raise RuntimeError(str(payload.get("message") or "获取 QQ 空间与我相关失败"))
        result = parse_about_me(payload)
        self._remember_posts(result.get("items") or [])
        return result

    async def query_mention_posts(
        self,
        *,
        offset: int = 0,
        count: int = 10,
        with_detail: bool = True,
    ) -> list[QzonePost]:
        ctx = await self.context()
        limit = max(1, min(int(count or 10), 20))
        payload = await self._request(
            "GET",
            self.ABOUT_ME_URL,
            params={
                "uin": ctx.uin,
                "begin_time": 0,
                "end_time": 0,
                "getappnotification": 1,
                "getnotifi": 1,
                "has_get_key": 0,
                "offset": max(0, int(offset or 0)),
                "set": 0,
                "count": limit,
                "useutf8": 1,
                "outputhtmlfeed": 1,
                "grz": time.time(),
                "scope": 1,
                "g_tk": ctx.gtk,
            },
            headers=self._headers(ctx, Referer=f"{self.BASE_URL}/{ctx.uin}"),
        )
        if not self._ok(payload):
            raise RuntimeError(str(payload.get("message") or "获取 QQ 空间提到我动态失败"))

        items = [
            item
            for item in _about_me_feed_items(payload)
            if _is_mention_feed_item(item, ctx.uin)
        ]
        posts = parse_recent_feed_list({"data": {"data": items}})
        detail = getattr(self, "_query_recent_post_details", None)
        if with_detail and callable(detail):
            posts = await detail(posts)
        self._remember_posts(posts)
        return posts

    async def query_last_year(self, *, year: int | None = None, count: int = 10) -> dict[str, Any]:
        ctx = await self.context()
        limit = max(1, min(int(count or 10), 20))
        payload = await self._request(
            "GET",
            self.LAST_YEAR_URL,
            params={
                "login_uin": ctx.uin,
                "mode": 1,
                "refer": "qzone",
                "useutf8": 1,
                "count": limit,
                "year": int(year or datetime.now().year - 1),
                "g_tk": ctx.gtk,
            },
            headers=self._headers(ctx, Referer=f"{self.BASE_URL}/{ctx.uin}"),
        )
        if not self._ok(payload):
            raise RuntimeError(str(payload.get("message") or "获取 QQ 空间那年今日失败"))
        result = parse_last_year(payload)
        self._remember_posts(result.get("items") or [])
        return result

    async def query_favorites(self, *, start: int = 0, num: int = 10, favorite_type: int = 0) -> dict[str, Any]:
        ctx = await self.context()
        offset = max(0, int(start or 0))
        limit = max(1, min(int(num or 10), 20))
        payload = await self._request(
            "GET",
            self.FAVORITE_URL,
            params={
                "uin": ctx.uin,
                "type": max(0, int(favorite_type or 0)),
                "start": offset,
                "num": limit,
                "inCharset": "utf-8",
                "outCharset": "utf-8",
                "need_nick": 1,
                "need_cnt": 1 if offset <= 0 else 0,
                "need_new_user": 1 if offset <= 0 else 0,
                "fupdate": 1,
                "callback": "_Callback",
                "random": time.time(),
                "g_tk": ctx.gtk,
            },
            headers=self._headers(ctx, Referer=f"{self.BASE_URL}/{ctx.uin}/myhome/favorite"),
        )
        if not self._ok(payload):
            raise RuntimeError(str(payload.get("message") or "获取 QQ 空间收藏失败"))
        result = parse_favorites(payload)
        result["has_more"] = offset + len(result.get("items") or []) < int(result.get("total") or 0)
        return result

    async def query_message_board(self, *, target_id: str = "", start: int = 0, num: int = 10) -> dict[str, Any]:
        ctx = await self.context()
        target = str(target_id or ctx.uin).strip() or str(ctx.uin)
        offset = max(0, int(start or 0))
        limit = max(1, min(int(num or 10), 20))
        payload = await self._request(
            "GET",
            self.MESSAGE_BOARD_URL,
            params={
                "uin": ctx.uin,
                "hostUin": target,
                "num": limit,
                "start": offset,
                "hostword": 0,
                "essence": 1,
                "r": time.time(),
                "iNotice": 0,
                "inCharset": "utf-8",
                "outCharset": "utf-8",
                "format": "jsonp",
                "ref": "qzone",
                "g_tk": ctx.gtk,
            },
            headers=self._headers(ctx, Referer=f"{self.BASE_URL}/{target}"),
        )
        if not self._ok(payload):
            raise RuntimeError(str(payload.get("message") or "获取 QQ 空间留言板失败"))
        return parse_message_board(payload, start=offset)

    async def query_relations(self, *, relation_type: str = "care") -> dict[str, Any]:
        ctx = await self.context()
        relation_key = str(relation_type or "care").strip().lower()
        do_type = 2 if relation_key in {"care_by", "careby", "by", "fans"} else 1
        payload = await self._request(
            "GET",
            self.RELATION_URL,
            params={
                "uin": ctx.uin,
                "do": do_type,
                "rd": time.time(),
                "fupdate": 1,
                "clean": 1,
                "g_tk": ctx.gtk,
            },
            headers=self._headers(ctx, Referer=f"{self.BASE_URL}/{ctx.uin}/myhome/friends"),
        )
        if not self._ok(payload):
            raise RuntimeError(str(payload.get("message") or "获取 QQ 空间在意好友失败"))
        return {
            "type": "care_by" if do_type == 2 else "care",
            "items": parse_qzone_relations(payload),
        }

    async def query_visit_stats(self) -> dict[str, Any]:
        ctx = await self.context()
        payload = await self._request(
            "GET",
            self.VISITOR_URL,
            params={
                "uin": ctx.uin,
                "mask": 2,
                "mod": 2,
                "fupdate": 1,
                "g_tk": ctx.gtk,
            },
            headers=self._headers(ctx, Referer=f"{self.BASE_URL}/{ctx.uin}/main"),
            retry_parse_error=False,
        )
        if not self._ok(payload):
            raise RuntimeError(str(payload.get("message") or "获取 QQ 空间浏览统计失败"))
        return parse_qzone_visit_stats(payload)

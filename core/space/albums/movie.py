from __future__ import annotations

from typing import Any

from astrbot.api import logger

from ..models import QzoneContext


class QzoneAlbumVideoMixin:
    """相册视频库确认。"""

    async def _query_qzone_video_library(
        self,
        ctx: QzoneContext,
        *,
        start: int = 0,
        count: int = 20,
        retry_login: bool = True,
    ) -> dict[str, Any]:
        payload = await self._qzone_request_with_cookie_variants(
            ctx,
            "GET",
            self.VIDEO_LIST_URL,
            params_factory=lambda current_ctx: {
                "g_tk": current_ctx.gtk,
                "uin": self._qzone_raw_uin(current_ctx),
                "hostUin": current_ctx.uin,
                "appid": 4,
                "getMethod": 2,
                "start": max(0, int(start or 0)),
                "count": max(1, min(int(count or 20), 50)),
                "need_old": 1,
                "getUserInfo": 1,
                "inCharset": "utf-8",
                "outCharset": "utf-8",
            },
            retry_login=retry_login,
        )
        if not self._ok(payload):
            raise RuntimeError(self._qzone_error_message(payload, "获取 QQ 空间视频列表失败"))
        return payload

    async def _uploaded_video_library_urls(self, ctx: QzoneContext, vid: str) -> list[str]:
        result = await self._confirm_uploaded_video_in_library(ctx, vid)
        return list(result.get("urls") or []) if result.get("confirmed") else []

    async def _confirm_uploaded_video_in_library(self, ctx: QzoneContext, vid: str) -> dict[str, Any]:
        expected_vid = str(vid or "").strip()
        if not expected_vid:
            return {"confirmed": False, "reason": "missing_vid"}
        try:
            payload = await self._query_qzone_video_library(ctx, start=0, count=20)
        except Exception as exc:
            logger.debug(f"[每日分享] 查询 QQ 空间视频库确认失败: {exc}")
            return {"confirmed": False, "reason": str(exc)}

        for item in self._walk_mappings(payload):
            values = {
                str(value or "").strip()
                for key, value in item.items()
                if str(key).lower() in {"vid", "videoid", "video_id", "svid"}
            }
            if expected_vid not in values:
                continue
            urls = self._http_video_urls(self._nested_urls(item))
            logger.info(
                f"[每日分享] 已在 QQ 空间视频库确认本地视频: 视频ID={expected_vid}, "
                f"视频地址={'有' if urls else '无'}"
            )
            return {"confirmed": True, "vid": expected_vid, "urls": urls}
        logger.debug(f"[每日分享] QQ 空间视频库未找到刚上传的视频: 视频ID={expected_vid}")
        return {"confirmed": False, "vid": expected_vid, "reason": "not_found"}

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from astrbot.api import logger

from ..models import QzoneContext


class QzoneAlbumListMixin:
    """相册列表、创建与选择。"""

    def _qzone_album_list_params(self, ctx: QzoneContext, *, response_format: str = "jsonp") -> dict[str, Any]:
        params: dict[str, Any] = {
            "g_tk": ctx.gtk,
            "hostUin": ctx.uin,
            "uin": self._qzone_raw_uin(ctx),
            "appid": 4,
            "inCharset": "utf-8",
            "outCharset": "utf-8",
            "source": "qzone",
            "plat": "qzone",
            "notice": 0,
        }
        if response_format == "json":
            params["format"] = "json"
            return params
        params.update(
            {
                "pageStart": 0,
                "pageNum": 50,
                "mode": 3,
                "needUserInfo": 1,
                "sortOrder": 1,
                "format": "jsonp",
                "json_esc": 1,
            }
        )
        return params

    @classmethod
    def _merge_qzone_album_payloads(cls, payloads: list[dict[str, Any]]) -> dict[str, Any]:
        if not payloads:
            return {"code": -1, "message": "QQ 空间相册列表为空"}
        if len(payloads) == 1:
            return payloads[0]
        albums: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for payload in payloads:
            for album in cls._qzone_album_candidates(payload):
                album_id, album_name = cls._album_identity(album)
                key = (album_id, album_name)
                if key == ("", "") or key in seen:
                    continue
                seen.add(key)
                albums.append(album)
        if albums:
            return {"code": 0, "data": {"albumList": albums}}
        return payloads[0]

    async def _qzone_album_list_payload(
        self,
        ctx: QzoneContext,
        *,
        retry_login: bool = True,
    ) -> dict[str, Any]:
        payloads: list[dict[str, Any]] = []
        last_payload: dict[str, Any] = {}
        attempts = (
            (self.ALBUM_LIST_URL, "jsonp"),
            (self.ALBUM_LIST_JSON_URL, "json"),
        )
        for url, response_format in attempts:
            payload = await self._qzone_request_with_cookie_variants(
                ctx,
                "GET",
                url,
                params_factory=lambda current_ctx, response_format=response_format: self._qzone_album_list_params(
                    current_ctx,
                    response_format=response_format,
                ),
                retry_login=retry_login,
            )
            last_payload = payload
            if not self._ok(payload):
                logger.debug(
                    "[每日分享] QQ 空间相册列表接口不可用: "
                    f"地址={urlsplit(url).path}, 状态码={payload.get('_http_status') or '-'}, "
                    f"字节数={payload.get('_raw_length') if payload.get('_raw_length') is not None else '-'}, "
                    f"消息={payload.get('message') or payload.get('msg') or '-'}"
                )
                continue
            payloads.append(payload)
        return self._merge_qzone_album_payloads(payloads) if payloads else last_payload

    def _qzone_create_album_payloads(
        self,
        ctx: QzoneContext,
        album_name: str,
        desc: str = "",
    ) -> tuple[tuple[str, dict[str, Any]], ...]:
        name = str(album_name or self.PUBLIC_VIDEO_ALBUM_NAME)
        base_data: dict[str, Any] = {
            "hostUin": ctx.uin,
            "uin": ctx.uin,
            "albumname": name,
            "albumdesc": str(desc or ""),
            "priv": "1",
            "format": "json",
            "qzreferrer": f"{self.BASE_URL}/{ctx.uin}/photo",
        }
        return (
            (self.ALBUM_CREATE_URL, base_data),
            (
                self.ALBUM_ADD_V2_URL,
                {
                    **base_data,
                    "album_type": "",
                    "albumclass": "100",
                    "question": "",
                    "answer": "",
                    "whiteList": "",
                    "bitmap": "10000000",
                    "appid": 4,
                    "inCharset": "utf-8",
                    "outCharset": "utf-8",
                    "source": "qzone",
                    "plat": "qzone",
                    "notice": 0,
                },
            ),
        )

    async def _create_public_video_album(self, ctx: QzoneContext, *, name: str = "") -> dict[str, Any]:
        album_name = str(name or self.PUBLIC_VIDEO_ALBUM_NAME)
        last_payload: dict[str, Any] = {}
        for url, data in self._qzone_create_album_payloads(ctx, album_name):
            payload = await self._qzone_request_with_cookie_variants(
                ctx,
                "POST",
                url,
                params_factory=lambda current_ctx: {"g_tk": current_ctx.gtk},
                data=data,
                retry_login=True,
                prefer_full_cookie=True,
            )
            last_payload = payload
            if self._ok(payload):
                logger.info(f"[每日分享] 已请求创建 QQ 空间公开视频相册: {album_name}")
                return payload
            logger.debug(
                "[每日分享] QQ 空间公开视频相册创建接口不可用: "
                f"路径={urlsplit(url).path}, 状态码={payload.get('_http_status') or '-'}, "
                f"字节数={payload.get('_raw_length') if payload.get('_raw_length') is not None else '-'}, "
                f"消息={payload.get('message') or payload.get('msg') or '-'}"
            )
        raise RuntimeError(self._qzone_error_message(last_payload, "QQ 空间公开视频相册创建失败"))

    async def _ensure_public_video_album(self, ctx: QzoneContext, *, name: str = "") -> dict[str, Any]:
        album_name = str(name or self.PUBLIC_VIDEO_ALBUM_NAME)
        payload = await self._qzone_album_list_payload(ctx, retry_login=True)
        if self._ok(payload):
            selected = self._select_public_video_album(payload, album_name=album_name)
            if selected:
                logger.info(f"[每日分享] QQ 空间将使用公开视频相册: {selected['name']}")
                return selected
        else:
            logger.debug(
                "[每日分享] 获取 QQ 空间相册列表失败，将尝试创建公开视频相册: "
                f"{self._qzone_error_message(payload, '获取 QQ 空间相册列表失败')}"
            )

        created = await self._create_public_video_album(ctx, name=album_name)
        selected = self._select_public_video_album(created, album_name=album_name)
        if selected:
            return selected
        created_album = self._created_public_video_album(created, album_name=album_name)
        if created_album:
            return created_album

        payload_after_create = await self._qzone_album_list_payload(ctx, retry_login=True)
        if self._ok(payload_after_create):
            selected = self._select_public_video_album(payload_after_create, album_name=album_name)
            if selected:
                logger.info(f"[每日分享] 已确认 QQ 空间公开视频相册: {selected['name']}")
                return selected
        raise RuntimeError("QQ 空间公开视频相册已请求创建，但未能确认可绑定的相册 ID")

    async def _qzone_album_for_video(
        self,
        ctx: QzoneContext,
        video: Any,
        *,
        retry_login: bool = True,
    ) -> dict[str, Any] | None:
        return await self._ensure_public_video_album(ctx)

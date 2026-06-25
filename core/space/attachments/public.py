from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlparse

from ..models import QzoneContext
from .debug import QzoneVideoDebugMixin
from .probe import QzoneAlbumProbeMixin


class QzoneAlbumPublicMixin(QzoneAlbumProbeMixin, QzoneVideoDebugMixin):
    @staticmethod
    def _album_video_key(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _album_video_context(cls, payload: Any) -> dict[str, str]:
        fields = {
            "album_id": {"sAlbumID", "albumid", "albumId", "album_id", "topicId", "topicid", "topic_id", "id"},
            "photo_id": {"sPhotoID", "photoid", "photoId", "photo_id", "picKey", "pickey", "pic_key", "lloc", "sloc", "sSloc"},
            "sloc": {"sSloc", "sloc", "picKey", "pickey", "pic_key", "lloc", "photoid", "photoId", "photo_id", "sPhotoID"},
            "cellid": {"cellid", "cellId", "fid", "tid", "key"},
            "video_share_h5": {"video_share_h5", "videoShareH5", "share_h5", "shareUrl", "share_url"},
            "busi_param_1": {"busi_param_1", "busiParam1", "busi_param", "busiparam"},
        }
        context = dict.fromkeys(fields, "")
        for item in cls._walk_mappings(payload):
            for key, value in item.items():
                key_text = str(key)
                for target, names in fields.items():
                    if not context[target] and key_text in names:
                        context[target] = cls._album_video_key(value)
            if context.get("video_share_h5"):
                parsed = urlparse(str(context["video_share_h5"]))
                query = dict(parse_qsl(parsed.query, keep_blank_values=True))
                if not context.get("cellid"):
                    context["cellid"] = cls._album_video_key(query.get("cellid"))
                if not context.get("album_id"):
                    context["album_id"] = cls._album_video_key(query.get("cellid"))
                if not context.get("busi_param_1"):
                    context["busi_param_1"] = cls._album_video_key(query.get("busi_param_1"))
        return {key: str(value or "").strip() for key, value in context.items()}

    @classmethod
    def _walk_mappings(cls, value: Any):
        if isinstance(value, dict):
            yield value
            for item in value.values():
                yield from cls._walk_mappings(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from cls._walk_mappings(item)

    async def _query_qzone_album_photos(
        self,
        ctx: QzoneContext,
        album_id: str,
        *,
        start: int = 0,
        count: int = 20,
        retry_login: bool = True,
    ) -> dict[str, Any]:
        album_id = str(album_id or "").strip()
        if not album_id:
            return {}
        payload = await self._qzone_request_with_cookie_variants(
            ctx,
            "GET",
            self.PHOTO_LIST_URL,
            params_factory=lambda current_ctx: {
                "g_tk": current_ctx.gtk,
                "hostUin": current_ctx.uin,
                "uin": self._qzone_raw_uin(current_ctx),
                "appid": 4,
                "pageStart": max(0, int(start or 0)),
                "pageNum": max(1, min(int(count or 20), 50)),
                "topicId": album_id,
                "inCharset": "utf-8",
                "outCharset": "utf-8",
            },
            retry_login=retry_login,
            prefer_full_cookie=True,
        )
        if not self._ok(payload):
            raise RuntimeError(self._qzone_error_message(payload, "获取 QQ 空间相册视频列表失败"))
        return payload

    async def _query_qzone_photo_floatview(
        self,
        ctx: QzoneContext,
        album_id: str,
        photo_key: str,
        *,
        retry_login: bool = True,
    ) -> dict[str, Any]:
        album_id = str(album_id or "").strip()
        photo_key = str(photo_key or "").strip()
        if not album_id or not photo_key:
            return {}
        payload = await self._qzone_request_with_cookie_variants(
            ctx,
            "GET",
            self.PHOTO_FLOATVIEW_URL,
            params_factory=lambda current_ctx: {
                "g_tk": current_ctx.gtk,
                "topicId": album_id,
                "picKey": photo_key,
                "cmtNum": 1,
                "inCharset": "utf-8",
                "outCharset": "utf-8",
                "uin": self._qzone_raw_uin(current_ctx),
                "hostUin": current_ctx.uin,
                "appid": 4,
                "isFirst": 1,
                "postNum": 0,
            },
            retry_login=retry_login,
            prefer_full_cookie=True,
        )
        if not self._ok(payload):
            raise RuntimeError(self._qzone_error_message(payload, "获取 QQ 空间相册视频详情失败"))
        return payload

    async def _query_qzone_album_info(
        self,
        ctx: QzoneContext,
        album_id: str,
        *,
        retry_login: bool = True,
    ) -> dict[str, Any]:
        album_id = str(album_id or "").strip()
        if not album_id:
            return {}
        payload = await self._qzone_request_with_cookie_variants(
            ctx,
            "GET",
            self.PHOTO_ALBUM_INFO_URL,
            params_factory=lambda current_ctx: {
                "g_tk": current_ctx.gtk,
                "albumId": album_id,
                "hostUin": current_ctx.uin,
                "uin": current_ctx.uin,
                "appid": 4,
                "inCharset": "utf-8",
                "outCharset": "utf-8",
                "source": "qzone",
                "plat": "qzone",
            },
            retry_login=retry_login,
            prefer_full_cookie=True,
        )
        if not self._ok(payload):
            raise RuntimeError(self._qzone_error_message(payload, "获取 QQ 空间相册信息失败"))
        return payload




from __future__ import annotations

import random
import time
from typing import Any

from astrbot.api import logger

from ...models import QzoneContext


class QzoneVideoCoverPayloadMixin:
    """构建 QQ 空间视频封面上传 payload。"""

    @classmethod
    def _video_cover_base_map_params(
        cls,
        vid: str,
        cover_size: int,
        client_key: str,
        width: int,
        height: int,
    ) -> dict[str, str]:
        map_params = {
            "vid": vid,
            "photo_num": "undefined",
            "video_num": "undefined",
            "raw_width": str(max(0, int(width or 0))),
            "raw_height": str(max(0, int(height or 0))),
            "raw_size": str(max(0, int(cover_size or 0))),
            "show_geo": "0",
            "ugc_right": "1",
            "who": "1",
        }
        if client_key:
            map_params["clientkey"] = str(client_key)
        return map_params

    @staticmethod
    def _video_cover_external_map_ext(client_key: str, video_size: int, duration_ms: int) -> dict[str, str]:
        external_map_ext = {
            "is_client_upload_cover": "1",
            "ugc_right": "1",
            "who": "1",
            "mix_isOriginalVideo": "0",
        }
        if int(video_size or 0) > 0:
            external_map_ext["mix_videoSize"] = str(int(video_size))
        if int(duration_ms or 0) > 0:
            external_map_ext["mix_time"] = str(int(duration_ms))
        return external_map_ext

    @staticmethod
    def _video_cover_album_fields(album_id: str, default_album: bool) -> dict[str, str]:
        album_fields = {
            "priv": "1",
            "privacy": "1",
            "accessright": "1",
        }
        if album_id and not default_album:
            album_fields.update(
                {
                    "albumid": album_id,
                    "album_id": album_id,
                    "topicId": album_id,
                }
            )
        return album_fields

    @staticmethod
    def _video_cover_album_type_id(album_type_id: int | None, default_album: bool) -> int:
        default_type_id = 7 if default_album else 0
        if album_type_id is None:
            return default_type_id
        try:
            return int(album_type_id)
        except (TypeError, ValueError):
            return default_type_id

    @classmethod
    def _video_cover_biz_req(
        cls,
        filename: str,
        vid: str,
        batch_id: int,
        album_id: str,
        album_name: str,
        cover_size: int = 0,
        client_key: str = "",
        upload_time: int = 0,
        description: str = "",
        width: int = 0,
        height: int = 0,
        cover_path: str = "",
        album_type_id: int | None = None,
        default_album: bool = False,
        video_size: int = 0,
        duration_ms: int = 0,
        need_feeds: int = 0,
    ) -> dict[str, Any]:
        album_id = str(album_id or "").strip()
        album_name = str(album_name or "").strip()
        default_album = bool(default_album)
        need_feeds = 1 if int(need_feeds or 0) else 0
        map_params = cls._video_cover_base_map_params(vid, cover_size, client_key, width, height)
        external_map_ext = cls._video_cover_external_map_ext(client_key, video_size, duration_ms)
        map_ext: dict[str, Any] = {}
        if need_feeds:
            external_map_ext["is_pic_video_mix_feeds"] = "1"
            if client_key:
                map_ext["mobile_fakefeeds_clientkey"] = str(client_key)
        album_fields = cls._video_cover_album_fields(album_id, default_album)
        if album_id and not default_album:
            map_params.update(album_fields)
            external_map_ext.update(album_fields)
        elif default_album:
            map_params.update(album_fields)
            external_map_ext.update(album_fields)
        resolved_album_type_id = cls._video_cover_album_type_id(album_type_id, default_album)
        return {
            "sPicTitle": filename,
            "sPicDesc": str(description or ""),
            "sAlbumName": "" if default_album else album_name,
            "sAlbumID": "" if default_album else album_id,
            "iAlbumTypeID": resolved_album_type_id,
            "iBitmap": 0,
            "iUploadType": 2,
            "iUpPicType": 0,
            "iBatchID": batch_id,
            "sPicPath": cover_path,
            "iPicWidth": int(width or 0),
            "iPicHight": int(height or 0),
            "iWaterType": 0,
            "iDistinctUse": 0x37DD,
            "mutliPicInfo": {"iBatUploadNum": 1, "iCurUpload": 0, "iSuccNum": 0, "iFailNum": 0},
            "iNeedFeeds": need_feeds,
            "iUploadTime": int(upload_time or time.time()),
            "stExtendInfo": {"mapParams": map_params},
            "stExternalMapExt": external_map_ext,
            "mapExt": map_ext,
            "sExif_CameraMaker": "",
            "sExif_CameraModel": "",
            "sExif_Time": "",
            "sExif_LatitudeRef": "",
            "sExif_Latitude": "",
            "sExif_LongitudeRef": "",
            "sExif_Longitude": "",
        }

    @staticmethod
    def _h5_upload_batch_id() -> int:
        return int(time.time() * 1000) * 1000 + random.randint(0, 999)

    def _build_video_cover_upload_payload(
        self,
        ctx: QzoneContext,
        cover_payload: dict[str, Any],
        *,
        filename: str,
        vid: str,
        album_id: str,
        album_name: str,
        client_key: str = "",
        upload_time: int = 0,
        description: str = "",
        album_type_id: int | None = None,
        default_album: bool = False,
        video_size: int = 0,
        duration_ms: int = 0,
        need_feeds: int = 0,
    ) -> tuple[str, dict[str, Any]]:
        checksum = str(cover_payload["md5"])
        batch_id = self._h5_upload_batch_id()
        cover_data = cover_payload.get("data")
        cover_path = str(cover_payload.get("path") or cover_payload.get("source") or "")
        width, height = self._image_size(
            cover_path if not isinstance(cover_data, (bytes, bytearray, memoryview)) else "",
            bytes(cover_data) if isinstance(cover_data, (bytes, bytearray, memoryview)) else None,
        )
        payload = {
            "control_req": [
                {
                    "uin": str(ctx.uin),
                    "token": self._h5_token(ctx),
                    "appid": "pic_qzone",
                    "checksum": checksum,
                    "check_type": 0,
                    "file_len": int(cover_payload["size"]),
                    "env": {"refer": "qzone", "deviceInfo": "h5"},
                    "model": 0,
                    "biz_req": self._video_cover_biz_req(
                        filename,
                        vid,
                        batch_id,
                        album_id,
                        album_name,
                        int(cover_payload["size"]),
                        client_key,
                        upload_time,
                        description,
                        width,
                        height,
                        cover_path,
                        album_type_id,
                        default_album,
                        video_size,
                        duration_ms,
                        need_feeds,
                    ),
                    "session": "",
                    "asy_upload": 0,
                    "cmd": "FileUpload",
                }
            ]
        }
        logger.debug(
            f"[每日分享] QQ 空间视频封面上传参数: 视频ID={vid}，相册ID={album_id}，"
            f"相册名称={album_name}，相册类型ID={album_type_id}，默认相册={default_album}，"
            f"生成动态={int(need_feeds or 0)}，批次ID={batch_id}，封面字节数={int(cover_payload['size'])}"
        )
        return checksum, payload

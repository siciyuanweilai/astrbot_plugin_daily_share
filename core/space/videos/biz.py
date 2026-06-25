from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..models import QzoneContext


class QzoneVideoBizMixin:
    """视频上传业务参数。"""

    @classmethod
    def _video_biz_req(
        cls,
        filename: str,
        title: str,
        description: str,
        play_time: int,
        client_key: str = "",
        upload_time: int = 0,
    ) -> dict[str, Any]:
        extend_info = {
            "video_type": "3",
            "domainid": "5",
            "qz_video_format": Path(filename).suffix.lower().lstrip(".") or "mp4",
            "ugc_right": "1",
            "who": "1",
        }
        if client_key:
            extend_info["clientkey"] = str(client_key)
        return {
            "sTitle": title or filename,
            "sDesc": description,
            "iFlag": 0,
            "iUploadTime": int(upload_time or time.time()),
            "iPlayTime": max(0, int(play_time or 0)),
            "iNeedFeeds": 0,
            "sCoverUrl": "",
            "iIsNew": 111,
            "iIsOriginalVideo": 0,
            "iIsFormatF20": 0,
            "extend_info": extend_info,
        }

    async def _init_h5_video_upload(
        self,
        ctx: QzoneContext,
        video_payload: dict[str, Any],
        *,
        title: str,
        description: str,
        play_time: int,
        client_key: str = "",
        upload_time: int = 0,
    ) -> dict[str, Any]:
        checksum = str(video_payload.get("sha1") or video_payload.get("md5") or "")
        payload = {
            "control_req": [
                {
                    "uin": str(ctx.uin),
                    "token": self._h5_token(ctx),
                    "appid": "video_qzone",
                    "checksum": checksum,
                    "check_type": 1,
                    "file_len": int(video_payload["size"]),
                    "env": {"refer": "qzone", "deviceInfo": "h5"},
                    "model": 0,
                    "biz_req": self._video_biz_req(
                        str(video_payload["filename"]),
                        title,
                        description,
                        play_time,
                        client_key,
                        upload_time,
                    ),
                    "session": "",
                    "asy_upload": 0,
                    "cmd": "FileUploadVideo",
                }
            ]
        }
        result = await self._h5_post_json(
            ctx,
            f"{self.H5_FILE_BATCH_CONTROL_URL}/{checksum}",
            payload,
            params={"g_tk": ctx.gtk},
            label="video-init",
        )
        if not self._h5_ok(result):
            raise RuntimeError(self._h5_error_message(result, "QQ 空间视频上传初始化失败"))
        return result

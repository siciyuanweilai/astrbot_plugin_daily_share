from __future__ import annotations

from typing import Any

from astrbot.api import logger

from ..models import QzoneContext


class QzoneVideoChunkMixin:
    """视频与封面分片上传。"""

    async def _upload_h5_file_chunks(
        self,
        ctx: QzoneContext,
        file_payload: dict[str, Any],
        *,
        session_id: str,
        slice_size: int,
        is_video: bool,
        include_image_cmd: bool = True,
        prefer_native_h2: bool = False,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        total = int(file_payload["size"])
        endpoint = self.H5_FILE_UPLOAD_VIDEO_URL if is_video else self.H5_FILE_UPLOAD_URL
        appid = "video_qzone" if is_video else "pic_qzone"
        cmd = "FileUploadVideo" if is_video else "FileUpload"
        for seq, (offset, end, chunk) in enumerate(self._payload_chunks(file_payload, slice_size), start=1):
            params = {
                "seq": seq,
                "retry": 0,
                "offset": offset,
                "end": end,
                "total": total,
                "type": "form",
                "g_tk": ctx.gtk,
            }
            result = None
            for retry_index, data_content_type in enumerate(("application/octet-stream", None)):
                body, content_type = self._h5_slice_multipart(
                    uin=ctx.uin,
                    appid=appid,
                    cmd=cmd,
                    session_id=session_id,
                    seq=seq,
                    offset=offset,
                    end=end,
                    slice_size=slice_size,
                    chunk=chunk,
                    upload_type=0 if is_video else 2,
                    data_content_type=data_content_type,
                )
                current_params = dict(params or {})
                if current_params:
                    current_params["retry"] = retry_index
                result = await self._h5_post_bytes(
                    ctx,
                    endpoint,
                    body,
                    content_type,
                    params=current_params or None,
                    label=f"{'video' if is_video else 'cover'}-chunk-{seq}",
                    headers=headers,
                )
                if self._h5_payload_ret_code(result) == -115 and data_content_type is not None:
                    logger.debug(
                        f"[每日分享] QQ 空间{'视频' if is_video else '视频封面'}分片拒绝二进制内容类型，改用不带内容类型的请求重试。"
                    )
                    continue
                break
            if result is None:
                raise RuntimeError("QQ 空间视频分片上传失败")
            if not self._h5_ok(result):
                raise RuntimeError(self._h5_error_message(result, "QQ 空间视频分片上传失败"))
            data = result.get("data") if isinstance(result.get("data"), dict) else {}
            if data.get("flag") == 1:
                return result
        raise RuntimeError("QQ 空间视频上传完成但未收到服务端最终响应")

    async def _upload_h5_video_payload(
        self,
        ctx: QzoneContext,
        video_payload: dict[str, Any],
        *,
        title: str,
        description: str,
        play_time: int,
        client_key: str,
        upload_time: int,
    ) -> dict[str, Any]:
        init = await self._init_h5_video_upload(
            ctx,
            video_payload,
            title=title,
            description=description,
            play_time=play_time,
            client_key=client_key,
            upload_time=upload_time,
        )
        init_data = init.get("data") if isinstance(init.get("data"), dict) else {}
        if init_data.get("flag") == 1:
            return init

        session_id = str(init_data.get("session") or "").strip()
        if not session_id:
            raise RuntimeError("QQ 空间视频上传初始化缺少 session")
        slice_size = max(1, int(init_data.get("slice_size") or self.H5_UPLOAD_SLICE_SIZE))
        return await self._upload_h5_file_chunks(
            ctx,
            video_payload,
            session_id=session_id,
            slice_size=slice_size,
            is_video=True,
        )

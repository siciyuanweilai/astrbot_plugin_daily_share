from __future__ import annotations

from ..panelcomponent import PanelComponent

import base64
import asyncio
import inspect

from ..common import _quart_request


class DashboardQzoneUploadService(PanelComponent):
    _QZONE_PANEL_UPLOAD_CHUNK_SIZE = 64 * 1024
    _QZONE_PANEL_UPLOAD_MAX_BYTES = 24 * 1024 * 1024

    @staticmethod
    def _qzone_upload_base64_ascii(data: bytes) -> str:
        return base64.b64encode(data).decode("ascii")

    async def _read_qzone_panel_upload(self, upload) -> bytes:
        data = bytearray()
        while True:
            read = upload.read
            if inspect.iscoroutinefunction(read):
                chunk = await read(self.qzone_upload._QZONE_PANEL_UPLOAD_CHUNK_SIZE)
            else:
                chunk = await asyncio.to_thread(
                    read, self.qzone_upload._QZONE_PANEL_UPLOAD_CHUNK_SIZE
                )
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > self.qzone_upload._QZONE_PANEL_UPLOAD_MAX_BYTES:
                raise RuntimeError("QQ 空间图片不能超过 24MB")
        return bytes(data)

    async def page_qzone_upload_media(self):
        async def handler():
            files = await _quart_request.files
            upload = files.get("file") or files.get("image") or files.get("media")
            if upload is None:
                raise RuntimeError("没有收到媒体文件")
            mime_type = getattr(upload, "content_type", "") or ""
            if mime_type.lower().startswith("video/"):
                raise RuntimeError("QQ 空间说说已移除视频上传支持，请上传图片")
            data = await self.qzone_upload._read_qzone_panel_upload(upload)
            encoded = await asyncio.to_thread(
                self.qzone_upload._qzone_upload_base64_ascii, data
            )
            return {
                "ok": True,
                "data": {
                    "media": {
                        "kind": "image",
                        "name": upload.filename or "image.jpg",
                        "source": f"base64://{encoded}",
                        "size": len(data),
                        "mime_type": mime_type or "image/jpeg",
                    }
                },
            }

        return await self.server._page_json(handler)

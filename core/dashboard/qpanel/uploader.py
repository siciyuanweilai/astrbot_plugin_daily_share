from __future__ import annotations

import base64

from ..common import _quart_request


class DashboardQzoneUploadMixin:
    async def page_qzone_upload_media(self):
        async def handler():
            if _quart_request is None:
                raise RuntimeError("当前环境不支持上传")
            files = await _quart_request.files
            upload = files.get("file") or files.get("image") or files.get("media")
            if upload is None:
                raise RuntimeError("没有收到媒体文件")
            data = await upload.read()
            mime_type = getattr(upload, "content_type", "") or ""
            kind = "video" if mime_type.lower().startswith("video/") else "image"
            return {
                "ok": True,
                "data": {
                    "media": {
                        "kind": kind,
                        "name": upload.filename or ("video.mp4" if kind == "video" else "image.jpg"),
                        "source": f"base64://{base64.b64encode(data).decode('ascii')}",
                        "size": len(data),
                        "mime_type": mime_type or ("video/mp4" if kind == "video" else "image/jpeg"),
                    }
                },
            }

        return await self._page_json(handler)

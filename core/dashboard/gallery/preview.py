from __future__ import annotations

import asyncio
import base64
import mimetypes
from io import BytesIO
from pathlib import Path
from typing import Optional

from astrbot.api import logger

from ..common import (
    _PAGE_INLINE_PREVIEW_MAX_BYTES,
    _PAGE_THUMBNAIL_MAX_SIDE,
    _PAGE_VIEW_IMAGE_MAX_SIDE,
)


class DashboardMediaPreviewMixin:
    def _page_image_data_url(self, path: Path, max_side: int = _PAGE_THUMBNAIL_MAX_SIDE, quality: int = 86) -> str:
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        stat_result = path.stat()
        size = stat_result.st_size

        try:
            from PIL import Image as PILImage
            from PIL import ImageOps

            with PILImage.open(path) as image:
                image = ImageOps.exif_transpose(image)
                image.thumbnail(
                    (max_side, max_side),
                    PILImage.Resampling.LANCZOS,
                )
                if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
                    background = PILImage.new("RGB", image.size, (255, 255, 255))
                    background.paste(image.convert("RGBA"), mask=image.convert("RGBA").split()[-1])
                    image = background
                else:
                    image = image.convert("RGB")
                output = BytesIO()
                image.save(output, format="JPEG", quality=quality, optimize=True)
                encoded = base64.b64encode(output.getvalue()).decode("ascii")
                return f"data:image/jpeg;base64,{encoded}"
        except Exception as exc:
            logger.debug(f"[每日分享] 生成媒体缩略图失败: {path}, {exc}")
            if size <= _PAGE_INLINE_PREVIEW_MAX_BYTES * 2:
                return self._page_file_data_url(path, mime)
            return ""

    async def _page_view_image_payload(self, item: dict, history_id: int) -> dict:
        media_url = str(item.get("media_url") or "").strip()
        path = self._page_resolve_media_path(item.get("media_path", ""))
        if not path and media_url:
            return {"delivery": "url", "view_url": media_url}
        if not path:
            raise RuntimeError("查看图文件不存在")
        return {
            "delivery": "data",
            "view_url": await asyncio.to_thread(self._page_image_data_url, path, _PAGE_VIEW_IMAGE_MAX_SIDE, 90),
            "version": self._page_media_file_version(path),
        }

    async def _page_media_preview_url(self, item: dict) -> str:
        media_url = str(item.get("media_url") or "").strip()
        kind = self._page_media_kind(item)
        if kind != "image":
            return ""

        path = self._page_resolve_media_path(item.get("media_path", ""))
        if not path:
            return media_url

        try:
            return await asyncio.to_thread(self._page_image_data_url, path)
        except Exception as exc:
            logger.debug(f"[每日分享] 构建媒体预览失败: {path}, {exc}")
            return ""

    async def _page_prepare_media_items(self, items: list) -> list:
        prepared = []
        for item in await self._page_prepare_history_items(items):
            item = dict(item)
            item["media_type"] = self._page_media_kind(item) or str(item.get("media_type") or "")
            item["preview_url"] = await self._page_media_preview_url(item)
            prepared.append(item)
        return prepared

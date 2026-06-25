from __future__ import annotations

import asyncio
import base64
import hashlib
import os
from pathlib import Path
from typing import Any


class QzoneLocalMediaMixin:
    @staticmethod
    def _media_source(media: Any) -> str:
        if isinstance(media, dict):
            for key in ("source", "url", "path", "file", "data_url", "dataUrl"):
                value = str(media.get(key) or "").strip()
                if value:
                    return value
            return ""
        return str(media or "").strip()

    @staticmethod
    def _path_like_source(source: str) -> bool:
        text = str(source or "").strip()
        if not text:
            return False
        if text.startswith(("http://", "https://", "base64://", "data:", "qzone://")):
            return False
        if text.startswith("file://"):
            return True
        return bool(Path(text).is_file())

    @staticmethod
    def _first_media_bytes(media: Any) -> bytes | None:
        if isinstance(media, (bytes, bytearray, memoryview)):
            return bytes(media)
        if isinstance(media, dict):
            for key in ("bytes", "data", "content"):
                value = media.get(key)
                if isinstance(value, (bytes, bytearray, memoryview)):
                    return bytes(value)
        return None

    @staticmethod
    def _decode_base64_media(source: str) -> bytes | None:
        text = str(source or "").strip()
        if text.startswith("base64://"):
            return base64.b64decode(text.removeprefix("base64://"))
        if text.startswith("data:") and ";base64," in text:
            return base64.b64decode(text.split(",", 1)[1])
        return None

    @staticmethod
    def _file_md5(path: Path) -> str:
        return QzoneLocalMediaMixin._file_hashes(path)["md5"]

    @staticmethod
    def _file_hashes(path: Path) -> dict[str, str]:
        md5_digest = hashlib.md5()
        sha1_digest = hashlib.sha1()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                md5_digest.update(chunk)
                sha1_digest.update(chunk)
        return {"md5": md5_digest.hexdigest(), "sha1": sha1_digest.hexdigest()}

    @staticmethod
    def _media_filename(media: Any, source: str, default_name: str) -> str:
        if isinstance(media, dict):
            for key in ("filename", "file_name", "name", "title"):
                value = str(media.get(key) or "").strip()
                if value:
                    return os.path.basename(value)[:128] or default_name
        if source and not source.startswith(("base64://", "data:")):
            name = os.path.basename(source)
            if name:
                return name[:128]
        return default_name

    async def _local_media_payload(self, media: Any, *, default_name: str, label: str) -> dict[str, Any]:
        source = self._media_source(media)
        filename = self._media_filename(media, source, default_name)
        data = self._first_media_bytes(media)
        if data is None:
            data = self._decode_base64_media(source)
        if data is not None:
            if not data:
                raise RuntimeError(f"QQ 空间{label}为空")
            raw_md5 = hashlib.md5(data).hexdigest()
            raw_sha1 = hashlib.sha1(data).hexdigest()
            return {
                "source": source,
                "filename": filename,
                "data": data,
                "size": len(data),
                "md5": raw_md5,
                "sha1": raw_sha1,
            }

        if source.startswith(("http://", "https://")):
            raise RuntimeError(f"QQ 空间{label}需要本地文件或 base64 数据")
        path = Path(source)
        if not path.is_file():
            raise RuntimeError(f"QQ 空间{label}不存在: {source}")
        size = path.stat().st_size
        if size <= 0:
            raise RuntimeError(f"QQ 空间{label}为空: {source}")
        hashes = await asyncio.to_thread(self._file_hashes, path)
        return {
            "source": source,
            "filename": filename,
            "path": path,
            "size": size,
            **hashes,
        }

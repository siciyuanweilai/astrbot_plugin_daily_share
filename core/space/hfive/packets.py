from __future__ import annotations

import gzip
import json
import zlib
from pathlib import Path
from typing import Any


class QzoneH5BaseMixin:
    """H5 传输基础工具。"""

    @staticmethod
    def _payload_chunks(payload: dict[str, Any], slice_size: int):
        size = int(payload.get("size") or 0)
        data = payload.get("data")
        if isinstance(data, (bytes, bytearray, memoryview)):
            raw = bytes(data)
            for offset in range(0, len(raw), slice_size):
                chunk = raw[offset : offset + slice_size]
                yield offset, offset + len(chunk), chunk
            return

        path = payload.get("path")
        with Path(path).open("rb") as handle:
            offset = 0
            while offset < size:
                chunk = handle.read(slice_size)
                if not chunk:
                    break
                end = offset + len(chunk)
                yield offset, end, chunk
                offset = end

    @staticmethod
    def _h5_json_body(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _decode_h5_body(raw: bytes, encoding: str = "") -> bytes:
        enc = str(encoding or "").strip().lower()
        try:
            if enc == "gzip":
                return gzip.decompress(raw)
            if enc == "deflate":
                try:
                    return zlib.decompress(raw)
                except zlib.error:
                    return zlib.decompress(raw, -zlib.MAX_WBITS)
        except Exception:
            return raw
        return raw

    @staticmethod
    def _annotate_h5_response(
        payload: dict[str, Any],
        *,
        status: int,
        text: str,
        label: str,
        transport: str,
    ) -> dict[str, Any]:
        payload["_http_status"] = status
        payload["_raw_length"] = len(text or "")
        if transport:
            payload["_transport"] = transport
        if label:
            payload["_endpoint"] = label
        return payload

    @staticmethod
    def _h5_ok(payload: dict[str, Any]) -> bool:
        code = payload.get("ret", payload.get("code", 0))
        try:
            return int(code or 0) == 0
        except (TypeError, ValueError):
            return False

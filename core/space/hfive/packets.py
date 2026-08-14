from __future__ import annotations

import gzip
import json
import zlib
from typing import Any

from ..methodset import QzoneMethodSet


class QzoneH5BaseService(QzoneMethodSet):
    """H5 传输基础工具。"""

    @staticmethod
    def _h5_json_body(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )

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
        payload["_raw_blank"] = not str(text or "").strip()
        if transport:
            payload["_transport"] = transport
        if label:
            payload["_endpoint"] = label
        return payload

    @staticmethod
    def _h5_ok(payload: dict[str, Any]) -> bool:
        code = payload.get("ret")
        if code is None:
            code = payload.get("code", 0)
        try:
            return int(code or 0) == 0
        except (TypeError, ValueError):
            return False

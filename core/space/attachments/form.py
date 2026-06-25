from __future__ import annotations

import random
from typing import Any


class QzoneMultipartMixin:
    @staticmethod
    def _multipart_field(boundary: str, name: str, value: str) -> bytes:
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n'
            "\r\n"
            f"{value}\r\n"
        ).encode("utf-8")

    @staticmethod
    def _multipart_blob(
        boundary: str,
        name: str,
        filename: str,
        data: bytes,
        *,
        content_type: str | None = "application/octet-stream",
    ) -> bytes:
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
        )
        if content_type is not None:
            header += f"Content-Type: {content_type}\r\n"
        header += "\r\n"
        return header.encode("utf-8") + bytes(data or b"") + b"\r\n"

    @classmethod
    def _h5_slice_multipart(
        cls,
        *,
        uin: int | str,
        appid: str,
        cmd: str,
        session_id: str,
        seq: int,
        offset: int,
        end: int,
        slice_size: int,
        chunk: bytes,
        upload_type: int,
        data_content_type: str | None = "application/octet-stream",
    ) -> tuple[bytes, str]:
        boundary = f"qzoneh5{random.getrandbits(128):032x}"
        body = bytearray()
        body.extend(cls._multipart_field(boundary, "uin", str(uin)))
        body.extend(cls._multipart_field(boundary, "appid", str(appid)))
        body.extend(cls._multipart_blob(boundary, "data", "blob", chunk, content_type=data_content_type))
        for key, value in (
            ("session", str(session_id)),
            ("offset", str(int(offset))),
            ("checksum", ""),
            ("check_type", "0"),
            ("retry", "0"),
            ("seq", str(int(seq))),
            ("end", str(int(end))),
            ("cmd", str(cmd)),
            ("slice_size", str(int(slice_size))),
            ("biz_req.iUploadType", str(int(upload_type))),
        ):
            body.extend(cls._multipart_field(boundary, key, value))
        body.extend(f"--{boundary}--\r\n".encode("ascii"))
        return bytes(body), f"multipart/form-data; boundary={boundary}"

    @staticmethod
    def _multipart_text(body: bytes) -> str:
        return body.decode("utf-8", "ignore")

    @staticmethod
    def _h5_payload_ret_code(payload: dict[str, Any]) -> int:
        if not isinstance(payload, dict):
            return 0
        for value in (payload.get("ret"), payload.get("code")):
            if value in (None, ""):
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
        data = payload.get("data")
        if isinstance(data, dict):
            for value in (data.get("ret"), data.get("code")):
                if value in (None, ""):
                    continue
                try:
                    return int(value)
                except (TypeError, ValueError):
                    pass
        return 0

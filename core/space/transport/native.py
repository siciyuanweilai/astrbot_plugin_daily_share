from __future__ import annotations

import asyncio
import ssl
from typing import Any, TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlsplit

try:
    import h2.connection
    import h2.config
    import h2.events
except Exception:  # pragma: no cover - 可选运行时依赖
    h2 = None

if TYPE_CHECKING:
    from ..models import QzoneContext


class QzoneH5NativeMixin:
    @staticmethod
    def _h5_native_request_path(url: str, params: dict[str, Any] | None = None):
        parsed_url = urlsplit(url)
        if parsed_url.scheme != "https" or not parsed_url.hostname:
            raise RuntimeError("原生 HTTP/2 只支持 HTTPS 地址")
        query = list(parse_qsl(parsed_url.query, keep_blank_values=True))
        if params:
            query.extend((str(key), str(value)) for key, value in params.items() if value is not None)
        path = parsed_url.path or "/"
        if query:
            path = f"{path}?{urlencode(query)}"
        return parsed_url, path

    async def _open_h5_native_h2_connection(self, parsed_url: Any):
        port = parsed_url.port or 443
        ssl_context = ssl.create_default_context()
        ssl_context.set_alpn_protocols(["h2"])
        return await asyncio.wait_for(
            asyncio.open_connection(
                parsed_url.hostname,
                port,
                ssl=ssl_context,
                server_hostname=parsed_url.hostname,
            ),
            timeout=self._api_timeout_seconds(),
        )

    @staticmethod
    def _ensure_h5_native_h2_alpn(writer: Any) -> None:
        ssl_object = writer.get_extra_info("ssl_object")
        selected_alpn = ssl_object.selected_alpn_protocol() if ssl_object else ""
        if selected_alpn != "h2":
            raise RuntimeError(f"原生 HTTP/2 ALPN 协商失败: {selected_alpn or '无'}")

    def _h5_native_h2_header_items(
        self,
        ctx: "QzoneContext",
        parsed_url: Any,
        path: str,
        headers: dict[str, str] | None = None,
    ) -> list[tuple[str, str]]:
        header_items = [
            (":method", "POST"),
            (":scheme", "https"),
            (":authority", parsed_url.netloc),
            (":path", path),
            ("accept-encoding", "gzip"),
        ]
        h2_headers = headers or self._h5_headers(ctx)
        for key, value in h2_headers.items():
            if value is not None:
                header_items.append((str(key).lower(), str(value)))
        return header_items

    @staticmethod
    async def _send_h5_native_h2_request(writer: Any, conn: Any, header_items: list[tuple[str, str]], body: bytes) -> None:
        conn.initiate_connection()
        writer.write(conn.data_to_send())
        await writer.drain()

        conn.send_headers(1, header_items, end_stream=not body)
        if body:
            max_frame_size = 16384
            for offset in range(0, len(body), max_frame_size):
                conn.send_data(
                    1,
                    body[offset : offset + max_frame_size],
                    end_stream=offset + max_frame_size >= len(body),
                )
                writer.write(conn.data_to_send())
                await writer.drain()
            return

        writer.write(conn.data_to_send())
        await writer.drain()

    def _handle_h5_native_h2_event(
        self,
        conn: Any,
        event: Any,
        response: dict[str, Any],
    ) -> tuple[int, str] | None:
        if isinstance(event, h2.events.ResponseReceived):
            for key, value in event.headers:
                key_text = key.decode() if isinstance(key, bytes) else str(key)
                value_text = value.decode() if isinstance(value, bytes) else str(value)
                if key_text == ":status":
                    try:
                        response["status"] = int(value_text)
                    except ValueError:
                        response["status"] = 0
                elif key_text.lower() == "content-encoding":
                    response["encoding"] = value_text
        elif isinstance(event, h2.events.DataReceived):
            response["chunks"].append(event.data)
            conn.acknowledge_received_data(event.flow_controlled_length, event.stream_id)
        elif isinstance(event, h2.events.StreamEnded):
            raw = b"".join(response["chunks"])
            text = self._decode_h5_body(raw, response.get("encoding") or "").decode("utf-8", "ignore")
            return int(response.get("status") or 0), text
        return None

    async def _read_h5_native_h2_response(self, reader: Any, writer: Any, conn: Any) -> tuple[int, str]:
        response: dict[str, Any] = {"status": 0, "encoding": "", "chunks": []}
        while True:
            data = await asyncio.wait_for(reader.read(65535), timeout=self._api_timeout_seconds())
            if not data:
                break
            for event in conn.receive_data(data):
                result = self._handle_h5_native_h2_event(conn, event, response)
                if result is not None:
                    return result
            pending = conn.data_to_send()
            if pending:
                writer.write(pending)
                await writer.drain()
        raw = b"".join(response["chunks"])
        text = self._decode_h5_body(raw, response.get("encoding") or "").decode("utf-8", "ignore")
        return int(response.get("status") or 0), text

    @staticmethod
    async def _close_h5_native_h2_writer(writer: Any) -> None:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

    async def _h5_post_json_native_h2(
        self,
        ctx: "QzoneContext",
        url: str,
        payload: dict[str, Any],
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, str]:
        if h2 is None:
            raise RuntimeError("原生 HTTP/2 不可用")
        parsed_url, path = self._h5_native_request_path(url, params)
        body = self._h5_json_body(payload)
        reader, writer = await self._open_h5_native_h2_connection(parsed_url)
        config = h2.config.H2Configuration(client_side=True, header_encoding="utf-8")
        conn = h2.connection.H2Connection(config=config)
        try:
            self._ensure_h5_native_h2_alpn(writer)
            header_items = self._h5_native_h2_header_items(ctx, parsed_url, path, headers)
            await self._send_h5_native_h2_request(writer, conn, header_items, body)
            return await self._read_h5_native_h2_response(reader, writer, conn)
        finally:
            await self._close_h5_native_h2_writer(writer)

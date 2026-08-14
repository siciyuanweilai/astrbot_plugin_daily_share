import asyncio
import json
from datetime import datetime

from astrbot.api import logger

from .common import _quart_response
from .panelcomponent import PanelComponent


class DashboardEventsService(PanelComponent):
    """仪表盘服务端事件流通道。"""

    def _ensure_page_event_state(self) -> None:
        if not isinstance(self.runtime._page_event_clients, set):
            self.runtime._page_event_clients = set()
        if not isinstance(self.runtime._page_event_seq, int):
            self.runtime._page_event_seq = 0

    def _page_event_payload(self, event_type: str, data: dict | None = None) -> dict:
        self.events._ensure_page_event_state()
        self._page_event_seq += 1
        return {
            "seq": self._page_event_seq,
            "type": str(event_type or "status"),
            "data": data or {},
            "time": datetime.now().isoformat(timespec="seconds"),
        }

    @staticmethod
    def _page_sse_message(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def emit_dashboard_event(
        self, event_type: str = "status", data: dict | None = None
    ) -> None:
        """向已打开的仪表盘页面广播轻量事件，前端收到后自行刷新页面状态。"""
        if self._is_terminated:
            return

        self.events._ensure_page_event_state()
        clients = list(self._page_event_clients)
        if not clients:
            return

        payload = self.events._page_event_payload(event_type, data)
        for queue in clients:
            try:
                while queue.full():
                    queue.get_nowait()
                queue.put_nowait(payload)
            except Exception as exc:
                logger.debug(f"[日常分享] 推送仪表盘事件失败: {exc}")

    def shutdown_event_streams(self) -> None:
        """唤醒并结束当前插件实例持有的全部面板事件流。"""
        self.events._ensure_page_event_state()
        clients = list(self._page_event_clients)
        self._page_event_clients.clear()
        for queue in clients:
            try:
                while queue.full():
                    queue.get_nowait()
                queue.put_nowait(None)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                continue

    async def page_events(self):
        self.events._ensure_page_event_state()
        queue = asyncio.Queue(maxsize=50)
        self._page_event_clients.add(queue)

        async def stream():
            try:
                hello = {
                    "seq": self._page_event_seq,
                    "type": "hello",
                    "data": {},
                    "time": datetime.now().isoformat(timespec="seconds"),
                }
                yield self.events._page_sse_message(hello)
                while not self._is_terminated:
                    try:
                        payload = await asyncio.wait_for(queue.get(), timeout=25)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    if payload is None:
                        break
                    yield self.events._page_sse_message(payload)
            finally:
                self._page_event_clients.discard(queue)

        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        return _quart_response(
            stream(), content_type="text/event-stream", headers=headers
        )

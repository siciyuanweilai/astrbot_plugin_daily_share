from __future__ import annotations

from collections.abc import Awaitable, Callable

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent


class PluginShareJobMixin:
    """后台执行手动分享，避免阻塞 AstrBot 消息处理链。"""

    async def _start_manual_share_task(
        self,
        event: AstrMessageEvent,
        *,
        specific_target: str | None = None,
        global_scope: bool = False,
        task_factory: Callable[[], Awaitable[None]],
    ) -> bool:
        share_lock = self._get_share_lock(specific_target, global_scope=global_scope)
        if share_lock.locked():
            return False
        await share_lock.acquire()

        async def run_manual_share() -> None:
            try:
                await task_factory()
            except Exception as exc:
                logger.error(f"[每日分享] 手动分享后台任务失败: {exc}")
                try:
                    await event.send(event.plain_result(f"分享出错: {exc}"))
                except Exception as send_exc:
                    logger.debug(f"[每日分享] 手动分享失败提示发送失败: {send_exc}")
            finally:
                if share_lock.locked():
                    share_lock.release()
                if not global_scope:
                    self._release_idle_share_lock(specific_target)

        self._track_task(run_manual_share())
        return True

    async def _send_manual_share_result(self, event: AstrMessageEvent, result) -> None:
        try:
            await event.send(result)
        except Exception as exc:
            logger.debug(f"[每日分享] 手动分享后台结果发送失败: {exc}")

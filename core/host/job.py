from __future__ import annotations

from collections.abc import Awaitable, Callable

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from .supportcomponent import SupportComponent


class PluginShareJobService(SupportComponent):
    """在后台执行手动分享，避免阻塞框架消息处理链。"""

    async def _start_manual_share_task(
        self,
        event: AstrMessageEvent,
        *,
        specific_target: str | None = None,
        global_scope: bool = False,
        task_factory: Callable[[], Awaitable[None]],
    ) -> bool:
        share_lock = self.get_share_lock(specific_target, global_scope=global_scope)
        if share_lock.locked():
            return False
        await share_lock.acquire()

        manual_coro = self.jobs._run_manual_share_task(
            event,
            task_factory,
            share_lock=share_lock,
            specific_target=specific_target,
            global_scope=global_scope,
        )
        try:
            task = self.track_task(manual_coro)
        except Exception:
            manual_coro.close()
            self.jobs._release_manual_share_task_lock(
                share_lock,
                specific_target=specific_target,
                global_scope=global_scope,
            )
            raise

        if task is not None:
            return True

        self.jobs._release_manual_share_task_lock(
            share_lock,
            specific_target=specific_target,
            global_scope=global_scope,
        )
        return False

    async def _run_manual_share_task(
        self,
        event: AstrMessageEvent,
        task_factory: Callable[[], Awaitable[None]],
        *,
        share_lock,
        specific_target: str | None,
        global_scope: bool,
    ) -> None:
        try:
            await task_factory()
        except Exception as exc:
            logger.error(f"[日常分享] 手动分享后台任务失败: {exc}")
            await self.jobs._send_manual_share_result(
                event,
                event.plain_result(f"分享出错: {exc}"),
            )
        finally:
            self.jobs._release_manual_share_task_lock(
                share_lock,
                specific_target=specific_target,
                global_scope=global_scope,
            )

    def _release_manual_share_task_lock(
        self,
        share_lock,
        *,
        specific_target: str | None,
        global_scope: bool,
    ) -> None:
        if share_lock.locked():
            share_lock.release()
        if not global_scope:
            self.release_idle_share_lock(specific_target)

    async def _send_manual_share_result(
        self,
        event: AstrMessageEvent,
        result,
    ) -> bool:
        try:
            await self.send_event(event, result)
            return True
        except Exception as exc:
            logger.debug(f"[日常分享] 手动分享后台结果发送失败: {exc}")
            return False

from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from ...config import NEWS_SOURCE_MAP, ShareType


class PluginShareStartRouteMixin:
    async def _start_news_image_task(
        self,
        event: AstrMessageEvent,
        *,
        news_src: str | None,
        current_uid: str,
        is_qzone_target: bool,
        specific_target: str | None,
        share_global_scope: bool,
    ):
        if not news_src:
            news_src = self.news_service.select_news_source()
        started = await self._start_manual_share_task(
            event,
            specific_target=specific_target,
            global_scope=share_global_scope,
            task_factory=lambda: self._run_news_image_share(
                event,
                news_src=news_src,
                current_uid=current_uid,
                is_qzone_target=is_qzone_target,
            ),
        )
        if not started:
            yield event.plain_result("正如火如荼地准备中，请稍后...")
            return

        target_desc = "QQ空间" if is_qzone_target else "当前会话"
        source_label = NEWS_SOURCE_MAP.get(news_src or "", {}).get("name") or "新闻源"
        yield event.plain_result(f"正在向{target_desc}分享{source_label}图片...")

    async def _start_typed_share_task(
        self,
        event: AstrMessageEvent,
        *,
        force_type: ShareType | None,
        news_source: str | None,
        start_text: str,
        is_qzone_target: bool,
        specific_target: str | None,
        share_global_scope: bool,
    ):
        if self._is_share_busy(specific_target, global_scope=share_global_scope):
            yield event.plain_result("正如火如荼地准备中，请稍后...")
            return

        if is_qzone_target:
            if news_source is None:
                task_factory = lambda: self.task_manager.execute_qzone_share(force_type, event=event)
            else:
                task_factory = lambda: self.task_manager.execute_qzone_share(
                    force_type,
                    news_source=news_source,
                    event=event,
                )
        elif news_source is None:
            task_factory = lambda: self.task_manager.execute_share(
                force_type,
                specific_target=specific_target,
                event=event,
            )
        else:
            task_factory = lambda: self.task_manager.execute_share(
                force_type,
                news_source=news_source,
                specific_target=specific_target,
                event=event,
            )

        started = await self._start_manual_share_task(
            event,
            specific_target=specific_target,
            global_scope=share_global_scope,
            task_factory=task_factory,
        )
        if not started:
            yield event.plain_result("正如火如荼地准备中，请稍后...")
            return
        yield event.plain_result(start_text)

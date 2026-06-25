from __future__ import annotations

from astrbot.api.event import AstrMessageEvent


class PluginShareBriefingRouteMixin:
    async def _handle_manual_briefing_command(
        self,
        event: AstrMessageEvent,
        *,
        arg: str,
        is_broadcast: bool,
        is_qzone_target: bool,
        specific_target: str | None = None,
        share_global_scope: bool = False,
    ):
        if arg == "60s":
            url = self.news_service.get_60s_image_url()
            if not url:
                yield event.plain_result("获取 60s 新闻失败，请检查接口密钥配置。")
                return
            task_factory = lambda: self._run_static_news_image_share(
                event,
                url=url,
                display_name="每天60s读世界",
                broadcast_name="60s新闻",
                history_text="【每天60秒读懂世界】",
                download_fail_message="60s新闻图片下载失败。",
                is_broadcast=is_broadcast,
                is_qzone_target=is_qzone_target,
            )
            share_name = "每天60s读世界"
        elif arg == "ai":
            task_factory = lambda: self._run_ai_news_image_share(
                event,
                is_broadcast=is_broadcast,
                is_qzone_target=is_qzone_target,
            )
            share_name = "AI资讯快报"
        else:
            return

        started = await self._start_manual_share_task(
            event,
            specific_target=specific_target,
            global_scope=share_global_scope,
            task_factory=task_factory,
        )
        if not started:
            yield event.plain_result("正如火如荼地准备中，请稍后...")
            return

        target_desc = self._manual_share_target_desc(
            is_broadcast=is_broadcast,
            is_qzone_target=is_qzone_target,
        )
        yield event.plain_result(f"正在向{target_desc}分享{share_name}...")

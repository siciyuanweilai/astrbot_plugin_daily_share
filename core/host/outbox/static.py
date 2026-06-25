from __future__ import annotations

from astrbot.api.event import AstrMessageEvent


class ImageStaticShareMixin:
    async def _run_static_news_image_share(self, event: AstrMessageEvent, **kwargs) -> None:
        async for result in self._handle_static_news_image_share(event, emit_start=False, **kwargs):
            await self._send_manual_share_result(event, result)

    async def _run_ai_news_image_share(
        self,
        event: AstrMessageEvent,
        *,
        is_broadcast: bool,
        is_qzone_target: bool,
    ) -> None:
        ai_data = await self.news_service.get_ai_news_json()
        if not ai_data:
            await self._send_manual_share_result(event, event.plain_result("获取 AI 资讯失败或今日暂无更新。"))
            return

        url = self.news_service.get_ai_news_image_url()
        if not url:
            await self._send_manual_share_result(event, event.plain_result("获取 AI 资讯图片失败，请检查接口密钥配置。"))
            return

        await self._run_static_news_image_share(
            event,
            url=url,
            display_name="AI资讯快报",
            broadcast_name="AI资讯",
            history_text="【AI资讯快报】",
            download_fail_message="AI资讯快报图片下载失败。",
            is_broadcast=is_broadcast,
            is_qzone_target=is_qzone_target,
        )

    async def _handle_static_news_image_share(
        self,
        event: AstrMessageEvent,
        *,
        url: str,
        display_name: str,
        broadcast_name: str,
        history_text: str,
        download_fail_message: str,
        is_broadcast: bool,
        is_qzone_target: bool,
        emit_start: bool = True,
    ):
        if is_qzone_target:
            async for result in self._share_static_image_to_qzone(
                event,
                url=url,
                display_name=display_name,
                history_text=history_text,
                emit_start=emit_start,
            ):
                yield result
            return

        if is_broadcast:
            async for result in self._broadcast_static_image(
                event,
                url=url,
                broadcast_name=broadcast_name,
                download_fail_message=download_fail_message,
                emit_start=emit_start,
            ):
                yield result
            return

        async for result in self._send_static_image_to_current(
            event,
            url=url,
            broadcast_name=broadcast_name,
            download_fail_message=download_fail_message,
            emit_start=emit_start,
        ):
            yield result

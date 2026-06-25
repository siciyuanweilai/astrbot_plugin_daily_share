from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from ...database.keys import (
    HISTORY_SHARE_NEWS,
    QZONE_TARGET_ID,
    SOURCE_COMMAND,
)


class ImageNewsShareMixin:
    async def _run_news_image_share(
        self,
        event: AstrMessageEvent,
        *,
        news_src: str,
        current_uid: str,
        is_qzone_target: bool,
    ) -> None:
        if not news_src:
            news_src = self.news_service.select_news_source()
        img_url, src_name = self.news_service.get_hot_news_image_url(news_src)
        snapshot_data = await self.news_service.get_hot_news(
            news_src,
            limit=self.task_manager.get_news_snapshot_limit(),
            allow_fallback=False,
        )

        if is_qzone_target:
            await self._run_qzone_news_image_share(
                event,
                news_src=news_src,
                img_url=img_url,
                src_name=src_name,
                current_uid=current_uid,
                snapshot_data=snapshot_data,
            )
            return

        await self._run_current_news_image_share(
            event,
            news_src=news_src,
            img_url=img_url,
            src_name=src_name,
            current_uid=current_uid,
            snapshot_data=snapshot_data,
        )

    async def _run_qzone_news_image_share(
        self,
        event: AstrMessageEvent,
        *,
        news_src: str,
        img_url: str,
        src_name: str,
        current_uid: str,
        snapshot_data,
    ) -> None:
        for target in (QZONE_TARGET_ID, current_uid):
            await self.task_manager.cache_news_snapshot(
                target,
                news_data=snapshot_data,
                source_key=news_src,
                image_url=img_url,
            )

        await self._send_manual_share_result(event, event.plain_result(f"正在获取[{src_name}]图片并分享到QQ空间..."))
        try:
            await self._safe_publish_qzone(text=f"【{src_name}】", images=[img_url])
            await self._send_manual_share_result(event, event.plain_result("QQ空间分享成功！"))
            await self.db.add_sent_history(
                QZONE_TARGET_ID,
                HISTORY_SHARE_NEWS,
                f"【{src_name}】长图(手动)",
                True,
                source_type=SOURCE_COMMAND,
                **self.task_manager._image_history_kwargs(img_url),
            )
        except Exception as exc:
            await self.db.add_sent_history(
                QZONE_TARGET_ID,
                HISTORY_SHARE_NEWS,
                f"【{src_name}】长图(手动)失败",
                False,
                error_reason=str(exc),
                source_type=SOURCE_COMMAND,
                **self.task_manager._image_history_kwargs(img_url),
            )
            await self._send_manual_share_result(event, event.plain_result(f"QQ空间分享失败: {exc}"))

    async def _run_current_news_image_share(
        self,
        event: AstrMessageEvent,
        *,
        news_src: str,
        img_url: str,
        src_name: str,
        current_uid: str,
        snapshot_data,
    ) -> None:
        await self.task_manager.cache_news_snapshot(
            current_uid,
            news_data=snapshot_data,
            source_key=news_src,
            image_url=img_url,
        )
        await self._send_manual_share_result(event, event.plain_result(f"正在获取 [{src_name}] 图片..."))
        filename = self.task_manager._build_news_image_filename(img_url, src_name)
        local_path = await self.task_manager._download_image_to_local(img_url, filename)
        if local_path:
            await self._send_manual_share_result(event, event.image_result(local_path))
            await self.db.add_sent_history(
                current_uid,
                HISTORY_SHARE_NEWS,
                f"【{src_name}】长图(手动)",
                True,
                source_type=SOURCE_COMMAND,
                **self.task_manager._image_history_kwargs(local_path),
            )
            return

        message = f"获取 [{src_name}] 图片下载失败。"
        await self.db.add_sent_history(
            current_uid,
            HISTORY_SHARE_NEWS,
            message,
            False,
            error_reason=message,
            source_type=SOURCE_COMMAND,
            **self.task_manager._image_history_kwargs(img_url),
        )
        await self._send_manual_share_result(event, event.plain_result(message))

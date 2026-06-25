from __future__ import annotations

import asyncio

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain

from ...database.keys import (
    GLOBAL_TARGET_ID,
    HISTORY_SHARE_BRIEFING,
    QZONE_TARGET_ID,
    SOURCE_COMMAND,
)


class ImageDeliveryShareMixin:
    async def _share_static_image_to_qzone(
        self,
        event: AstrMessageEvent,
        *,
        url: str,
        display_name: str,
        history_text: str,
        emit_start: bool,
    ):
        if emit_start:
            yield event.plain_result(f"正在分享{display_name}到QQ空间...")
        try:
            await self._safe_publish_qzone(text=history_text, images=[url])
            yield event.plain_result(f"{display_name}已成功分享到QQ空间！")
            await self.db.add_sent_history(
                QZONE_TARGET_ID,
                HISTORY_SHARE_BRIEFING,
                f"{history_text}(手动)",
                True,
                source_type=SOURCE_COMMAND,
                **self.task_manager._image_history_kwargs(url),
            )
        except Exception as exc:
            await self.db.add_sent_history(
                QZONE_TARGET_ID,
                HISTORY_SHARE_BRIEFING,
                f"{history_text}(手动)失败",
                False,
                error_reason=str(exc),
                source_type=SOURCE_COMMAND,
                **self.task_manager._image_history_kwargs(url),
            )
            yield event.plain_result(f"QQ空间分享失败: {exc}")

    async def _send_static_image_to_current(
        self,
        event: AstrMessageEvent,
        *,
        url: str,
        broadcast_name: str,
        download_fail_message: str,
        emit_start: bool,
    ):
        if emit_start:
            yield event.plain_result(f"正在向当前会话分享{broadcast_name}...")
        filename = self.task_manager._build_news_image_filename(url, broadcast_name)
        local_path = await self.task_manager._download_image_to_local(url, filename)
        if local_path:
            yield event.image_result(local_path)
            await self.db.add_sent_history(
                event.unified_msg_origin,
                HISTORY_SHARE_BRIEFING,
                f"【{broadcast_name}】手动",
                True,
                source_type=SOURCE_COMMAND,
                **self.task_manager._image_history_kwargs(local_path),
            )
            return

        await self.db.add_sent_history(
            event.unified_msg_origin,
            HISTORY_SHARE_BRIEFING,
            download_fail_message,
            False,
            error_reason=download_fail_message,
            source_type=SOURCE_COMMAND,
            **self.task_manager._image_history_kwargs(url),
        )
        yield event.plain_result(download_fail_message)

    async def _broadcast_static_image(
        self,
        event: AstrMessageEvent,
        *,
        url: str,
        broadcast_name: str,
        download_fail_message: str,
        emit_start: bool,
    ):
        if emit_start:
            yield event.plain_result(f"正在向配置的所有群聊和私聊分享{broadcast_name}...")
        filename = self.task_manager._build_news_image_filename(url, broadcast_name)
        local_path = await self.task_manager._download_image_to_local(url, filename)
        if not local_path:
            await self.db.add_sent_history(
                GLOBAL_TARGET_ID,
                HISTORY_SHARE_BRIEFING,
                download_fail_message,
                False,
                error_reason=download_fail_message,
                source_type=SOURCE_COMMAND,
                **self.task_manager._image_history_kwargs(url),
            )
            yield event.plain_result(download_fail_message)
            return

        success_count = 0
        fail_count = 0
        for target in self.task_manager.get_broadcast_targets():
            try:
                prepared_path = await self.task_manager._prepare_image_for_target(target, local_path)
                await self.task_manager._send_message_chain(
                    target,
                    MessageChain().file_image(prepared_path),
                )
                await self.db.add_sent_history(
                    target,
                    HISTORY_SHARE_BRIEFING,
                    f"【{broadcast_name}】手动广播",
                    True,
                    source_type=SOURCE_COMMAND,
                    **self.task_manager._image_history_kwargs(prepared_path),
                )
                success_count += 1
            except Exception as exc:
                fail_count += 1
                logger.error(f"[每日分享] 分享{broadcast_name}到 {target} 失败: {exc}")
                await self.db.add_sent_history(
                    target,
                    HISTORY_SHARE_BRIEFING,
                    f"{broadcast_name}广播失败: {exc}",
                    False,
                    error_reason=str(exc),
                    source_type=SOURCE_COMMAND,
                    **self.task_manager._image_history_kwargs(local_path),
                )
            await asyncio.sleep(1)
        yield event.plain_result(f"{broadcast_name}广播完成：成功 {success_count} 个，失败 {fail_count} 个。")

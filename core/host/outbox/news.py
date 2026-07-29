from __future__ import annotations

from ..supportcomponent import SupportComponent

from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger

from ...database.keys import (
    HISTORY_SHARE_NEWS,
    QZONE_TARGET_ID,
    SOURCE_COMMAND,
)
from ...toolkit import format_exception


class ImageNewsShareService(SupportComponent):
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
            limit=self.task_manager.snapshot_store.get_news_snapshot_limit(),
            allow_fallback=False,
        )
        snapshot_payload = (
            {"items": snapshot_data[0], "source": snapshot_data[1]}
            if snapshot_data
            else None
        )
        if not snapshot_payload:
            await self.jobs._send_manual_share_result(
                event,
                event.plain_result("获取新闻列表失败，长图分享已取消。"),
            )
            return

        if is_qzone_target:
            await self.news_outbox._run_qzone_news_image_share(
                event,
                news_src=news_src,
                img_url=img_url,
                src_name=src_name,
                current_uid=current_uid,
                snapshot_data=snapshot_payload,
            )
            return

        await self.news_outbox._run_current_news_image_share(
            event,
            news_src=news_src,
            img_url=img_url,
            src_name=src_name,
            current_uid=current_uid,
            snapshot_data=snapshot_payload,
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
        await self.jobs._send_manual_share_result(
            event, event.plain_result(f"正在获取[{src_name}]图片并分享到QQ空间...")
        )
        try:
            await self.qzone.publish_qzone(text=f"【{src_name}】", images=[img_url])
        except Exception as exc:
            await self.db.add_sent_history(
                QZONE_TARGET_ID,
                HISTORY_SHARE_NEWS,
                f"【{src_name}】长图(手动)失败",
                False,
                error_reason=str(exc),
                source_type=SOURCE_COMMAND,
                **self.task_manager.executor_helpers.image_history_kwargs(img_url),
            )
            await self.jobs._send_manual_share_result(
                event, event.plain_result(f"QQ空间分享失败: {exc}")
            )
            return

        try:
            await self.task_manager.executor_helpers.record_share_history(
                target_id=QZONE_TARGET_ID,
                share_type=HISTORY_SHARE_NEWS,
                content=f"【{src_name}】长图(手动)",
                success=True,
                source_type=SOURCE_COMMAND,
                image_ref=img_url,
                news_snapshot_data=snapshot_data,
                news_image_url=img_url,
                news_snapshot_targets=[QZONE_TARGET_ID, current_uid],
            )
        except Exception as exc:
            logger.error(
                "[日常分享] QQ 空间新闻长图已发送，但历史和快照保存失败: %s",
                format_exception(exc),
            )
        await self.jobs._send_manual_share_result(
            event, event.plain_result("QQ空间分享成功！")
        )

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
        await self.jobs._send_manual_share_result(
            event, event.plain_result(f"正在获取 [{src_name}] 图片...")
        )
        filename = self.task_manager.delivery_assets.build_news_image_filename(
            img_url, src_name
        )
        local_path = await self.task_manager.delivery_assets.download_image_to_local(
            img_url, filename
        )
        if local_path:
            image_sent = await self.jobs._send_manual_share_result(
                event, event.image_result(local_path)
            )
            if not image_sent:
                await self.db.add_sent_history(
                    current_uid,
                    HISTORY_SHARE_NEWS,
                    "新闻长图发送失败",
                    False,
                    error_reason="新闻长图发送失败",
                    source_type=SOURCE_COMMAND,
                    **self.task_manager.executor_helpers.image_history_kwargs(
                        local_path
                    ),
                )
                return
            try:
                await self.task_manager.executor_helpers.record_share_history(
                    target_id=current_uid,
                    share_type=HISTORY_SHARE_NEWS,
                    content=f"【{src_name}】长图(手动)",
                    success=True,
                    source_type=SOURCE_COMMAND,
                    image_ref=local_path,
                    news_snapshot_data=snapshot_data,
                    news_image_url=local_path,
                )
            except Exception as exc:
                logger.error(
                    "[日常分享] 新闻长图已发送，但历史和快照保存失败: %s",
                    format_exception(exc),
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
            **self.task_manager.executor_helpers.image_history_kwargs(img_url),
        )
        await self.jobs._send_manual_share_result(event, event.plain_result(message))

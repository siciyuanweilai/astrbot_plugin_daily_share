from typing import TYPE_CHECKING, Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ...config import ShareType, TimePeriod
from ...constants import period_label, share_type_label
from ...database.keys import (
    QZONE_TARGET_ID,
    SOURCE_COMMAND,
    SOURCE_SCHEDULED,
)
from ...toolkit import format_exception, log_exception
from ..taskbase import TaskServiceBase


class TaskQzoneFlowService(TaskServiceBase):
    """QQ 空间分享主流程编排。"""

    if TYPE_CHECKING:

        async def _load_qzone_news_data(
            self,
            *,
            news_source: str | None,
            event: AstrMessageEvent | None,
            history_source: str,
            progress_id: str,
        ) -> tuple[bool, tuple[list, str] | None]: ...

        async def _generate_qzone_content(
            self,
            *,
            stype: ShareType,
            period: TimePeriod,
            life_ctx: Any,
            news_data: Any,
            progress_id: str,
            event: AstrMessageEvent | None,
        ) -> str: ...

        async def _generate_qzone_image(
            self,
            *,
            stype: ShareType,
            content: str,
            life_ctx: Any,
            news_data: Any,
            progress_id: str,
            event: AstrMessageEvent | None,
        ) -> str | None: ...

        async def _prepare_qzone_publish_media(
            self, *, target_local_img: str | None
        ) -> list: ...

        async def _publish_and_record_qzone_share(
            self,
            *,
            progress_id: str,
            stype: ShareType,
            content: str,
            qzone_images: list,
            target_local_img: str | None,
            history_source: str,
            news_snapshot_data: dict | None,
        ) -> str: ...

    async def _start_qzone_share_progress(
        self,
        *,
        force_type: ShareType | None = None,
        history_source: str,
    ) -> tuple[TimePeriod, ShareType, str]:
        period = self.services.executor_helpers.get_curr_period()
        stype = (
            force_type
            if force_type
            else await self.services.type_selector.decide_type_with_state(
                period, is_qzone=True
            )
        )
        logger.info(
            f"[日常分享] QQ 空间时段: {period_label(period)}, 类型: {share_type_label(stype)}"
        )
        progress_id = self.services.progress.start_share_progress(
            source_type=history_source,
            target_id=QZONE_TARGET_ID,
            share_type=stype,
            enabled_steps=["content", "image", "send"],
            message="准备分享到 QQ 空间",
        )
        return period, stype, progress_id

    async def _record_qzone_share_exception(
        self,
        *,
        error: Exception,
        stype: ShareType,
        history_source: str,
        progress_id: str = "",
        event: AstrMessageEvent | None = None,
    ) -> None:
        log_exception(
            "[日常分享] 生成并分享到 QQ 空间失败", error, with_traceback=False
        )
        try:
            await self.services.executor_helpers.record_share_failure(
                target_id=QZONE_TARGET_ID,
                share_type=stype,
                message=f"生成并分享到QQ空间失败: {format_exception(error)}",
                error_reason=format_exception(error),
                source_type=history_source,
            )
        except Exception as record_error:
            log_exception(
                "[日常分享] 记录 QQ 空间失败历史失败",
                record_error,
                level="debug",
                with_traceback=False,
            )
        if event:
            try:
                await self.send_event(
                    event,
                    event.plain_result(
                        f"生成并分享到QQ空间失败: {format_exception(error)}"
                    ),
                )
            except Exception as send_error:
                log_exception(
                    "[日常分享] 发送 QQ 空间失败提示失败",
                    send_error,
                    level="debug",
                    with_traceback=False,
                )
        self.services.progress.finish_share_progress(
            progress_id, success=False, message="QQ 空间分享失败"
        )

    async def execute_qzone_share(
        self,
        force_type: ShareType | None = None,
        news_source: str | None = None,
        event: AstrMessageEvent | None = None,
        source_type: str = "",
        need_video: bool = False,
    ) -> bool:
        """完全独立的 QQ 空间分享主流程。"""
        if self.plugin._is_terminated:
            return False
        history_source = str(
            source_type or (SOURCE_COMMAND if event else SOURCE_SCHEDULED)
        ).strip()
        progress_id = ""
        stype = ShareType.GREETING

        try:
            period, stype, progress_id = await self._start_qzone_share_progress(
                force_type=force_type,
                history_source=history_source,
            )

            life_ctx = await self.ctx_service.get_life_context(QZONE_TARGET_ID)
            news_data = None
            if stype == ShareType.NEWS:
                loaded_news, news_data = await self._load_qzone_news_data(
                    news_source=news_source,
                    event=event,
                    history_source=history_source,
                    progress_id=progress_id,
                )
                if not loaded_news:
                    return False

            clean_qzone_content = await self._generate_qzone_content(
                stype=stype,
                period=period,
                life_ctx=life_ctx,
                news_data=news_data,
                progress_id=progress_id,
                event=event,
            )
            if not clean_qzone_content:
                return False

            target_local_img = await self._generate_qzone_image(
                stype=stype,
                content=clean_qzone_content,
                life_ctx=life_ctx,
                news_data=news_data,
                progress_id=progress_id,
                event=event,
            )
            qzone_images = await self._prepare_qzone_publish_media(
                target_local_img=target_local_img,
            )
            await self._publish_and_record_qzone_share(
                progress_id=progress_id,
                stype=stype,
                content=clean_qzone_content,
                qzone_images=qzone_images,
                target_local_img=target_local_img,
                history_source=history_source,
                news_snapshot_data=(
                    self.services.snapshots.news_snapshot_payload(
                        news_data[0], news_data[1]
                    )
                    if (
                        stype == ShareType.NEWS
                        and news_data
                        and str(target_local_img or "").startswith(
                            ("http://", "https://")
                        )
                    )
                    else None
                ),
            )

            if event:
                try:
                    await self.services.executor_helpers.sync_qzone_result_to_event(
                        event,
                        clean_qzone_content,
                        target_local_img,
                        None,
                    )
                except Exception as e:
                    log_exception(
                        "[日常分享] 同步发送内容到会话失败", e, with_traceback=False
                    )

            self.services.progress.finish_share_progress(
                progress_id, success=True, message="QQ 空间分享完成"
            )
            return True

        except Exception as e:
            await self._record_qzone_share_exception(
                error=e,
                stype=stype,
                history_source=history_source,
                progress_id=progress_id,
                event=event,
            )
            return False

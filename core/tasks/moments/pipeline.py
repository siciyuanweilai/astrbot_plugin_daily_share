from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ...config import ShareType
from ...constants import period_label, share_type_label
from ...database.keys import MEDIA_VIDEO, QZONE_TARGET_ID, SOURCE_COMMAND, SOURCE_SCHEDULED
from ...toolkit import format_exception, log_exception


class TaskQzoneFlowMixin:
    """QQ 空间分享主流程编排。"""

    async def _start_qzone_share_progress(
        self,
        *,
        force_type: ShareType = None,
        history_source: str,
    ) -> tuple[str, ShareType, str]:
        period = self.get_curr_period()
        stype = force_type if force_type else await self.decide_type_with_state(period, is_qzone=True)
        logger.info(f"[每日分享] QQ 空间时段: {period_label(period)}, 类型: {share_type_label(stype)}")
        progress_id = self._start_share_progress(
            source_type=history_source,
            target_id=QZONE_TARGET_ID,
            share_type=stype,
            enabled_steps=["content", "image", "video", "send"],
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
        event: AstrMessageEvent = None,
    ) -> None:
        log_exception("[每日分享] 生成并分享到 QQ 空间失败", error, with_traceback=False)
        try:
            await self._record_share_failure(
                target_id=QZONE_TARGET_ID,
                share_type=stype,
                message=f"生成并分享到QQ空间失败: {format_exception(error)}",
                error_reason=format_exception(error),
                source_type=history_source,
            )
        except Exception as record_error:
            log_exception("[每日分享] 记录 QQ 空间失败历史失败", record_error, level="debug", with_traceback=False)
        if event:
            try:
                await event.send(event.plain_result(f"生成并分享到QQ空间失败: {format_exception(error)}"))
            except Exception as send_error:
                log_exception("[每日分享] 发送 QQ 空间失败提示失败", send_error, level="debug", with_traceback=False)
        self._finish_share_progress(progress_id, success=False, message="QQ 空间分享失败")

    async def execute_qzone_share(
        self,
        force_type: ShareType = None,
        news_source: str = None,
        event: AstrMessageEvent = None,
        source_type: str = "",
        need_video: bool = False,
    ) -> bool:
        """完全独立的 QQ 空间分享主流程。"""
        if self.plugin._is_terminated:
            return False
        history_source = str(source_type or (SOURCE_COMMAND if event else SOURCE_SCHEDULED)).strip()
        progress_id = ""
        stype = ShareType.GREETING

        try:
            period, stype, progress_id = await self._start_qzone_share_progress(
                force_type=force_type,
                history_source=history_source,
            )

            life_ctx = await self.ctx_service.get_life_context()
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

            self.image_service.reset_last_description()
            target_local_img = await self._generate_qzone_image(
                stype=stype,
                content=clean_qzone_content,
                life_ctx=life_ctx,
                news_data=news_data,
                progress_id=progress_id,
                event=event,
            )
            qzone_videos, qzone_video_url = await self._generate_qzone_video_payloads(
                stype=stype,
                content=clean_qzone_content,
                target_local_img=target_local_img,
                progress_id=progress_id,
                need_video=need_video,
                event=event,
            )
            qzone_images = await self._prepare_qzone_publish_media(
                target_local_img=target_local_img,
                qzone_videos=qzone_videos,
            )
            sent_media_type = await self._publish_and_record_qzone_share(
                progress_id=progress_id,
                stype=stype,
                content=clean_qzone_content,
                qzone_images=qzone_images,
                qzone_videos=qzone_videos,
                target_local_img=target_local_img,
                qzone_video_url=qzone_video_url,
                history_source=history_source,
            )

            if event:
                try:
                    await self._sync_qzone_result_to_event(
                        event,
                        clean_qzone_content,
                        target_local_img,
                        qzone_video_url if sent_media_type == MEDIA_VIDEO else None,
                    )
                except Exception as e:
                    log_exception("[每日分享] 同步发送内容到会话失败", e, with_traceback=False)

            self._finish_share_progress(progress_id, success=True, message="QQ 空间分享完成")
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

from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from ....config import ShareType, TimePeriod
from .logbook import TaskCommandLocalRecordService


class TaskCommandLocalRunService(TaskCommandLocalRecordService):
    async def _run_command_local_share(
        self,
        *,
        event: AstrMessageEvent,
        uid: str,
        target_umo: str,
        target_type_enum: ShareType,
        period: TimePeriod,
        life_ctx: str,
        news_data,
        img_path: str | None = None,
        need_image: bool,
        need_video: bool,
        need_voice: bool,
        history_source: str,
        progress_id: str,
        finish_progress,
    ) -> bool:
        is_group, nickname = await self._command_content_nickname(target_umo, event)
        content_context = await self.services.executor_helpers.prepare_content_context(
            target_umo=target_umo,
            share_type=target_type_enum,
            life_ctx=life_ctx,
            is_group=is_group,
            event=event,
            nickname=nickname,
            recent_target_id=uid,
        )

        self.services.progress.update_share_progress(
            progress_id, "content", message="文案生成中"
        )
        content = await self.content_service.generate(
            target_type_enum,
            period,
            target_umo,
            is_group,
            content_context["life_prompt"],
            news_data,
            nickname=nickname,
            recent_dynamics=content_context["recent_dynamics"],
            structured_history=content_context.get("structured_history", ""),
        )
        if not content:
            await self.send_event(
                event, event.plain_result("内容生成失败，请稍后再试。")
            )
            finish_progress(False, "文案生成失败")
            return False

        self.services.progress.complete_share_progress_step(
            progress_id, "content", "文案已生成"
        )
        hot_news_image_url = img_path if target_type_enum == ShareType.NEWS else None
        (
            img_path,
            send_img_path,
            video_url,
            audio_path,
            image_description,
        ) = await self._generate_command_media(
            progress_id=progress_id,
            content=content,
            target_type_enum=target_type_enum,
            life_ctx=life_ctx,
            target_umo=target_umo,
            period=period,
            event=event,
            img_path=img_path,
            need_image=need_image,
            need_video=need_video,
            need_voice=need_voice,
        )

        sent, media_result = await self._send_command_generated_share(
            target_umo=target_umo,
            content=content,
            send_img_path=send_img_path,
            audio_path=audio_path,
            video_url=video_url,
            event=event,
            progress_id=progress_id,
        )
        if not sent:
            await self.send_event(
                event,
                event.plain_result(
                    "内容已生成，但发送失败，请查看日志或检查平台连接状态。"
                ),
            )
            finish_progress(False, "发送失败")
            return False

        news_snapshot_data = None
        news_image_url = None
        if (
            target_type_enum == ShareType.NEWS
            and news_data
            and hot_news_image_url
            and media_result.get("image_sent")
        ):
            news_snapshot_data = self.services.snapshots.news_snapshot_payload(
                news_data[0], news_data[1]
            )
            news_image_url = (
                media_result.get("downloaded_image_path")
                or media_result.get("image_path")
                or hot_news_image_url
                or ""
            )

        await self._record_command_share_success(
            target_umo=target_umo,
            target_type_enum=target_type_enum,
            content=content,
            history_source=history_source,
            media_result=media_result,
            img_path=img_path,
            video_url=video_url,
            news_snapshot_data=news_snapshot_data,
            news_image_url=news_image_url,
            image_description=image_description,
            degradation_reason=self.services.progress.share_progress_degradation_reason(
                progress_id
            ),
        )
        self.services.executor_helpers.log_partial_send_errors(target_umo, media_result)
        await self.services.executor_helpers.notify_partial_send_errors(
            event, media_result
        )
        finish_progress(True, "分享完成")
        return True

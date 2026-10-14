from __future__ import annotations

from ..continuation import preserve_share
from ..taskbase import TaskServiceBase
from .manual.localnews import TaskCommandLocalNewsService
from .manual.logbook import TaskCommandLocalRecordService
from .manual.mediafile import TaskCommandLocalMediaService
from .manual.resolve import TaskCommandLocalResolveService
from .manual.run import TaskCommandLocalRunService
from .picture import TaskCommandImageService
from .runner import TaskCommandRunnerService


class TaskCommandShareService(TaskServiceBase):
    """自然语言触发的分享后台任务。"""

    def _finish_command_progress(self, progress, success, message):
        return self.runner._finish_command_progress(progress, success, message)

    async def _resolve_command_share_request(
        self, *, event, share_type, source, to_qzone, history_source
    ):
        return await self.runner._resolve_command_share_request(
            event=event,
            share_type=share_type,
            source=source,
            to_qzone=to_qzone,
            history_source=history_source,
        )

    async def _run_command_share_request(
        self,
        *,
        event,
        request,
        get_image,
        need_image,
        need_video,
        need_voice,
        to_qzone,
        history_source,
        progress,
    ):
        return await self.runner._run_command_share_request(
            event=event,
            request=request,
            get_image=get_image,
            need_image=need_image,
            need_video=need_video,
            need_voice=need_voice,
            to_qzone=to_qzone,
            history_source=history_source,
            progress=progress,
        )

    async def async_daily_share_task(
        self,
        event,
        share_type,
        source,
        get_image,
        need_image,
        need_video,
        need_voice,
        to_qzone,
    ):
        """自然语言触发的分享后台任务。"""
        return await self.runner.async_daily_share_task(
            event,
            share_type,
            source,
            get_image,
            need_image,
            need_video,
            need_voice,
            to_qzone,
        )

    async def _finalize_command_share_task(
        self,
        *,
        event,
        progress,
        feedback_enabled,
        feedback_success,
        share_lock,
        lock_acquired,
        share_global_scope,
        share_target,
    ):
        return await self.runner._finalize_command_share_task(
            event=event,
            progress=progress,
            feedback_enabled=feedback_enabled,
            feedback_success=feedback_success,
            share_lock=share_lock,
            lock_acquired=lock_acquired,
            share_global_scope=share_global_scope,
            share_target=share_target,
        )

    async def _run_command_local_share(
        self,
        *,
        event,
        uid,
        target_umo,
        target_type_enum,
        period,
        life_ctx,
        news_data,
        img_path=None,
        need_image,
        need_video,
        need_voice,
        history_source,
        progress_id,
        finish_progress,
        post_context=None,
    ):
        return await self.local._run_command_local_share(
            event=event,
            uid=uid,
            target_umo=target_umo,
            target_type_enum=target_type_enum,
            period=period,
            life_ctx=life_ctx,
            news_data=news_data,
            img_path=img_path,
            need_image=need_image,
            need_video=need_video,
            need_voice=need_voice,
            history_source=history_source,
            progress_id=progress_id,
            finish_progress=finish_progress,
            post_context=post_context,
        )

    @preserve_share("command")
    async def send_prepared_command_share(
        self,
        *,
        target_umo,
        target_type_enum,
        period,
        life_ctx,
        news_data,
        img_path=None,
        need_image,
        need_video,
        need_voice,
        history_source,
        progress_id,
        content,
        event=None,
        finish_progress=None,
    ):
        return await self.local.send_prepared_command_share(
            target_umo=target_umo,
            target_type_enum=target_type_enum,
            period=period,
            life_ctx=life_ctx,
            news_data=news_data,
            img_path=img_path,
            need_image=need_image,
            need_video=need_video,
            need_voice=need_voice,
            history_source=history_source,
            progress_id=progress_id,
            content=content,
            event=event,
            finish_progress=finish_progress,
        )

    async def _send_command_generated_share(
        self,
        *,
        target_umo,
        content,
        send_img_path=None,
        audio_path=None,
        video_url=None,
        event,
        progress_id,
    ):
        return await self.records._send_command_generated_share(
            target_umo=target_umo,
            content=content,
            send_img_path=send_img_path,
            audio_path=audio_path,
            video_url=video_url,
            event=event,
            progress_id=progress_id,
        )

    async def _record_command_share_success(
        self,
        *,
        target_umo,
        target_type_enum,
        content,
        history_source,
        media_result,
        img_path=None,
        video_url=None,
        news_snapshot_data=None,
        news_image_url=None,
        image_description="",
        degradation_reason="",
    ):
        return await self.records._record_command_share_success(
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
            degradation_reason=degradation_reason,
        )

    async def _generate_command_media(
        self,
        *,
        progress_id,
        content,
        target_type_enum,
        life_ctx,
        target_umo,
        period,
        event,
        img_path=None,
        need_image,
        need_video,
        need_voice,
    ):
        return await self.media._generate_command_media(
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

    async def _generate_command_video(
        self,
        *,
        progress_id,
        content,
        target_umo,
        event,
        img_path,
        image_description,
        need_video,
    ):
        return await self.media._generate_command_video(
            progress_id=progress_id,
            content=content,
            target_umo=target_umo,
            event=event,
            img_path=img_path,
            image_description=image_description,
            need_video=need_video,
        )

    async def _generate_command_audio(
        self, *, progress_id, content, target_umo, share_type, period, event, need_voice
    ):
        return await self.media._generate_command_audio(
            progress_id=progress_id,
            content=content,
            target_umo=target_umo,
            share_type=share_type,
            period=period,
            event=event,
            need_voice=need_voice,
        )

    async def _load_command_news(
        self,
        *,
        event,
        target_umo,
        target_type_enum,
        news_src_key,
        get_image,
        need_image,
    ):
        return await self.news._load_command_news(
            event=event,
            target_umo=target_umo,
            target_type_enum=target_type_enum,
            news_src_key=news_src_key,
            get_image=get_image,
            need_image=need_image,
        )

    async def _resolve_command_share_type(self, *, event, share_type_text, st_clean):
        return await self.resolver._resolve_command_share_type(
            event=event, share_type_text=share_type_text, st_clean=st_clean
        )

    async def _prepare_command_local_target(
        self, *, event, target_type_enum, history_source
    ):
        return await self.resolver._prepare_command_local_target(
            event=event,
            target_type_enum=target_type_enum,
            history_source=history_source,
        )

    async def _run_command_qzone_share(
        self, *, event, target_type_enum, news_src_key, history_source, need_video
    ):
        return await self.resolver._run_command_qzone_share(
            event=event,
            target_type_enum=target_type_enum,
            news_src_key=news_src_key,
            history_source=history_source,
            need_video=need_video,
        )

    async def _command_content_nickname(self, target_umo, event):
        return await self.resolver._command_content_nickname(target_umo, event)

    async def _send_command_news_long_image(
        self,
        *,
        event,
        progress_id,
        to_qzone,
        news_src_key,
        history_source,
        finish_progress,
    ):
        return await self.images._send_command_news_long_image(
            event=event,
            progress_id=progress_id,
            to_qzone=to_qzone,
            news_src_key=news_src_key,
            history_source=history_source,
            finish_progress=finish_progress,
        )

    async def _try_send_command_briefing(
        self, *, event, st_clean, to_qzone, history_source
    ):
        return await self.images._try_send_command_briefing(
            event=event,
            st_clean=st_clean,
            to_qzone=to_qzone,
            history_source=history_source,
        )

    async def _try_send_command_news_image(
        self,
        *,
        event,
        target_type_enum,
        get_image,
        need_image,
        need_voice,
        need_video,
        to_qzone,
        progress_id,
        news_src_key,
        history_source,
        finish_progress,
    ):
        return await self.images._try_send_command_news_image(
            event=event,
            target_type_enum=target_type_enum,
            get_image=get_image,
            need_image=need_image,
            need_voice=need_voice,
            need_video=need_video,
            to_qzone=to_qzone,
            progress_id=progress_id,
            news_src_key=news_src_key,
            history_source=history_source,
            finish_progress=finish_progress,
        )

    def __init__(self, runtime, config, state) -> None:
        super().__init__(runtime, config, state)
        self.runner = TaskCommandRunnerService(self)
        self.local = TaskCommandLocalRunService(self)
        self.records = TaskCommandLocalRecordService(self)
        self.media = TaskCommandLocalMediaService(self)
        self.news = TaskCommandLocalNewsService(self)
        self.resolver = TaskCommandLocalResolveService(self)
        self.images = TaskCommandImageService(self)


__all__ = ["TaskCommandShareService"]

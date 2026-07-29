from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from ...config import ShareType
from ...database.keys import QZONE_TARGET_ID, SOURCE_COMMAND
from ...reaction import mark_failed, mark_processing, mark_success
from ...toolkit import format_exception
from .local import TaskCommandLocalService


class TaskCommandRunnerService(TaskCommandLocalService):
    def _finish_command_progress(
        self, progress: dict, success: bool, message: str
    ) -> None:
        progress_id = str(progress.get("id") or "")
        if progress_id and not progress.get("done"):
            self.services.progress.finish_share_progress(
                progress_id, success=success, message=message
            )
            progress["done"] = True

    async def _resolve_command_share_request(
        self,
        *,
        event: AstrMessageEvent,
        share_type: str,
        source: str,
        to_qzone: bool,
        history_source: str,
    ) -> dict:
        share_type_text = str(share_type or "auto").strip()
        st_clean = share_type_text.lower().replace(" ", "").replace("　", "")

        briefing_result = await self._try_send_command_briefing(
            event=event,
            st_clean=st_clean,
            to_qzone=to_qzone,
            history_source=history_source,
        )
        if briefing_result is not None:
            return {"handled": True, "success": briefing_result}

        valid_type, target_type_enum = await self._resolve_command_share_type(
            event=event,
            share_type_text=share_type_text,
            st_clean=st_clean,
        )
        if not valid_type:
            return {"handled": True, "success": False}

        return {
            "handled": False,
            "target_type": target_type_enum,
            "news_source": self.services.executor_helpers.map_news_source_arg(source),
        }

    async def _run_command_share_request(
        self,
        *,
        event: AstrMessageEvent,
        request: dict,
        get_image: bool,
        need_image: bool,
        need_video: bool,
        need_voice: bool,
        to_qzone: bool,
        history_source: str,
        progress: dict,
    ) -> bool:
        target_type_enum = request["target_type"]
        news_src_key = request["news_source"]

        if not to_qzone:
            (
                uid,
                target_umo,
                period,
                target_type_enum,
                progress_id,
            ) = await self._prepare_command_local_target(
                event=event,
                target_type_enum=target_type_enum,
                history_source=history_source,
            )
            progress["id"] = progress_id

        is_news_image_mode = (
            target_type_enum == ShareType.NEWS
            and get_image
            and not need_image
            and not need_voice
            and not need_video
        )
        if to_qzone and is_news_image_mode and not progress.get("id"):
            progress["id"] = self.services.progress.start_share_progress(
                source_type=history_source,
                target_id=QZONE_TARGET_ID,
                share_type=target_type_enum,
                enabled_steps=["image", "send"],
                message="准备发送新闻长图",
            )

        news_image_result = await self._try_send_command_news_image(
            event=event,
            target_type_enum=target_type_enum,
            get_image=get_image,
            need_image=need_image,
            need_voice=need_voice,
            need_video=need_video,
            to_qzone=to_qzone,
            progress_id=progress.get("id", ""),
            news_src_key=news_src_key,
            history_source=history_source,
            finish_progress=lambda success, message: self._finish_command_progress(
                progress, success, message
            ),
        )
        if news_image_result is not None:
            return news_image_result

        if to_qzone:
            return await self._run_command_qzone_share(
                event=event,
                target_type_enum=target_type_enum,
                news_src_key=news_src_key,
                history_source=history_source,
                need_video=need_video,
            )

        life_ctx = await self.ctx_service.get_life_context(target_umo)
        loaded_news, news_data, img_path, news_src_key = await self._load_command_news(
            event=event,
            target_umo=target_umo,
            target_type_enum=target_type_enum,
            news_src_key=news_src_key,
            get_image=get_image,
            need_image=need_image,
        )
        if not loaded_news:
            self._finish_command_progress(progress, False, "获取新闻失败")
            return False

        return await self._run_command_local_share(
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
            progress_id=progress.get("id", ""),
            history_source=history_source,
            finish_progress=lambda success, message: self._finish_command_progress(
                progress, success, message
            ),
        )

    async def async_daily_share_task(
        self,
        event: AstrMessageEvent,
        share_type: str,
        source: str,
        get_image: bool,
        need_image: bool,
        need_video: bool,
        need_voice: bool,
        to_qzone: bool,
    ):
        """自然语言触发的分享后台任务。"""
        if self.plugin._is_terminated:
            return

        feedback_enabled = event is not None
        feedback_success = False
        history_source = SOURCE_COMMAND

        share_target = str(getattr(event, "unified_msg_origin", "") or "").strip()
        share_global_scope = bool(to_qzone)
        is_busy = self.services.executor_helpers.is_command_share_busy(
            share_target, global_scope=share_global_scope
        )
        share_lock = self.services.executor_helpers.get_command_share_lock(
            share_target, global_scope=share_global_scope
        )

        if is_busy:
            if feedback_enabled:
                await mark_failed(event)
            await self.send_event(
                event, event.plain_result("正如火如荼地准备中，请稍后...")
            )
            return

        lock_acquired = False
        progress = {"id": "", "done": False}

        await share_lock.acquire()
        lock_acquired = True
        try:
            if feedback_enabled:
                await mark_processing(event)

            request = await self._resolve_command_share_request(
                event=event,
                share_type=share_type,
                source=source,
                to_qzone=to_qzone,
                history_source=history_source,
            )
            if request.get("handled"):
                feedback_success = bool(request.get("success"))
                return

            feedback_success = await self._run_command_share_request(
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

        except Exception as e:
            self.services.executor_helpers.log_exception("[日常分享] 异步任务错误", e)
            await self.send_event(
                event, event.plain_result(f"分享出错: {format_exception(e)}")
            )
            self._finish_command_progress(progress, False, "分享出错")
        finally:
            await self._finalize_command_share_task(
                event=event,
                progress=progress,
                feedback_enabled=feedback_enabled,
                feedback_success=feedback_success,
                share_lock=share_lock,
                lock_acquired=lock_acquired,
                share_global_scope=share_global_scope,
                share_target=share_target,
            )

    async def _finalize_command_share_task(
        self,
        *,
        event,
        progress: dict,
        feedback_enabled: bool,
        feedback_success: bool,
        share_lock,
        lock_acquired: bool,
        share_global_scope: bool,
        share_target: str,
    ) -> None:
        self._finish_command_progress(
            progress, feedback_success, "分享完成" if feedback_success else "分享未完成"
        )
        if feedback_enabled:
            await (mark_success(event) if feedback_success else mark_failed(event))
        if lock_acquired and share_lock.locked():
            share_lock.release()
        if not share_global_scope:
            self.services.executor_helpers.release_command_share_lock(share_target)

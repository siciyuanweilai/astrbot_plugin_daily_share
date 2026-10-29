from astrbot.api import logger

from ...integrations.mediajob import current_share_job, media_error_message
from ...toolkit import log_exception
from ..taskbase import TaskServiceBase


class TaskHelperRecordService(TaskServiceBase):
    """分享历史与部分发送异常记录。"""

    def log_exception(self, message: str, exc: Exception) -> None:
        log_exception(message, exc, with_traceback=False)

    async def record_share_history(
        self,
        *,
        target_id: str,
        share_type,
        content: str,
        success: bool,
        source_type: str,
        error_reason: str = "",
        media_result: dict | None = None,
        image_ref: str | None = None,
        video_ref: str | None = None,
        news_snapshot_data: dict | None = None,
        news_image_url: str | None = None,
        news_snapshot_targets: list[str] | None = None,
        degradation_reason: str = "",
    ) -> None:
        visual = self._sent_visual_history_kwargs(media_result, image_ref, video_ref)
        degradation_reasons = []
        if success and str(degradation_reason or "").strip():
            degradation_reasons.append(str(degradation_reason).strip())
        if success:
            for item in (media_result or {}).get("partial_errors", []):
                if item.get("probable_sent"):
                    continue
                label = str(
                    item.get("stage_label") or item.get("stage") or "媒体"
                ).strip()
                message = media_error_message(item.get("message"), "发送失败")
                reason = f"{label}发送失败：{message}"
                if reason not in degradation_reasons:
                    degradation_reasons.append(reason)
        resolved_degradation_reason = "；".join(degradation_reasons)
        job = current_share_job.get()
        if job is not None and success:
            job["degradation_reason"] = resolved_degradation_reason
        snapshot = self.services.snapshots.prepare_news_snapshot_record(
            news_snapshot_data,
            news_image_url,
        )
        history = {
            "target_id": target_id,
            "share_type": getattr(share_type, "value", share_type),
            "content": content,
            "source_type": source_type,
            "degraded": bool(resolved_degradation_reason),
            "degradation_reason": resolved_degradation_reason,
            **visual,
        }
        if success and snapshot:
            targets = news_snapshot_targets or [target_id]
            records = []
            seen = set()
            for item in targets:
                snapshot_target = str(item or "").strip()
                if not snapshot_target or snapshot_target in seen:
                    continue
                seen.add(snapshot_target)
                records.append({**snapshot, "target_id": snapshot_target})
            if len(records) == 1:
                await self.db.add_sent_history_with_news_snapshot(history, records[0])
            else:
                await self.db.add_sent_history_with_news_snapshots(history, records)
            for record in records:
                self.services.snapshots.invalidate_news_context_prompt(
                    record["target_id"]
                )
        else:
            await self.db.add_sent_history(
                target_id=target_id,
                share_type=getattr(share_type, "value", share_type),
                content=content,
                success=success,
                error_reason=error_reason or None,
                source_type=source_type,
                degraded=bool(resolved_degradation_reason),
                degradation_reason=resolved_degradation_reason,
                **visual,
            )
        if resolved_degradation_reason:
            logger.warning(
                f"[日常分享] 目标 {target_id}："
                f"{media_error_message(resolved_degradation_reason, '媒体未完成')}"
            )

    async def record_share_failure(
        self,
        *,
        target_id: str,
        share_type,
        message: str,
        source_type: str,
        error_reason: str = "",
        media_result: dict | None = None,
        image_ref: str | None = None,
        video_ref: str | None = None,
    ) -> None:
        await self.record_share_history(
            target_id=target_id,
            share_type=share_type,
            content=message,
            success=False,
            error_reason=error_reason or message,
            source_type=source_type,
            media_result=media_result,
            image_ref=image_ref,
            video_ref=video_ref,
        )

    def _media_history_kwargs(
        self, media_type: str, media_ref: str | None = None
    ) -> dict:
        ref = str(media_ref or "").strip()
        if not ref:
            return {}
        if ref.startswith(("http://", "https://")):
            return {"media_type": media_type, "media_url": ref}
        return {"media_type": media_type, "media_path": ref}

    def image_history_kwargs(self, media_ref: str | None = None) -> dict:
        return self._media_history_kwargs("image", media_ref)

    def _video_history_kwargs(self, media_ref: str | None = None) -> dict:
        return self._media_history_kwargs("video", media_ref)

    def _visual_history_kwargs(
        self, image_ref: str | None = None, video_ref: str | None = None
    ) -> dict:
        if video_ref:
            return self._video_history_kwargs(video_ref)
        return self.image_history_kwargs(image_ref)

    def _sent_visual_history_kwargs(
        self,
        media_result: dict | None = None,
        image_ref: str | None = None,
        video_ref: str | None = None,
    ) -> dict:
        if media_result is None:
            return self._visual_history_kwargs(image_ref, video_ref)
        if media_result.get("video_sent"):
            resolved_video = media_result.get("video_url") or video_ref
            return self._video_history_kwargs(resolved_video)
        if media_result.get("image_sent"):
            resolved_image = (
                media_result.get("downloaded_image_path")
                or media_result.get("image_path")
                or image_ref
            )
            return self.image_history_kwargs(resolved_image)
        return {}

    def log_partial_send_errors(
        self, target_id: str, media_result: dict | None = None
    ) -> None:
        errors = (media_result or {}).get("partial_errors", [])
        if not errors:
            return
        summary = "；".join(
            f"{item.get('stage_label') or item.get('stage')}: {item.get('message')}"
            for item in errors
        )
        logger.warning(f"[日常分享] {target_id} 部分发送异常: {summary}")


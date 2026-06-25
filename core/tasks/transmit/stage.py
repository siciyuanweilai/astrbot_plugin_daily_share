from __future__ import annotations

from ...toolkit import format_exception


class TaskDeliveryStatusMixin:
    def _init_media_result(
        self,
        media_result: dict,
        *,
        downloaded_img_path: str = "",
        img_path: str = "",
        video_url: str = "",
    ) -> None:
        if media_result is None:
            return
        media_result.clear()
        media_result.update(
            {
                "text_sent": False,
                "audio_sent": False,
                "image_sent": False,
                "video_sent": False,
            }
        )
        if downloaded_img_path:
            media_result["downloaded_image_path"] = downloaded_img_path
        if img_path:
            media_result["image_path"] = img_path
        if video_url:
            media_result["video_url"] = video_url

    def _record_send_stage_error(
        self,
        media_result: dict,
        stage: str,
        error: Exception,
        *,
        probable_sent: bool = False,
    ) -> None:
        if media_result is None:
            return
        media_result.setdefault("partial_errors", []).append(
            {
                "stage": stage,
                "stage_label": self._send_stage_label(stage),
                "message": format_exception(error),
                "probable_sent": probable_sent,
            }
        )

    def _send_stage_label(self, stage: str) -> str:
        return {
            "text": "文字",
            "audio": "语音",
            "image": "配图",
            "video": "视频",
        }.get(str(stage or ""), str(stage or "消息"))

    def _mark_send_stage_success(
        self,
        media_result: dict,
        stage: str,
        *,
        probable_sent: bool = False,
    ) -> None:
        if media_result is None:
            return
        media_result[f"{stage}_sent"] = True
        if probable_sent:
            media_result[f"{stage}_probable_sent"] = True

    def _has_sent_stage(self, media_result: dict) -> bool:
        if not media_result:
            return False
        return any(
            bool(media_result.get(f"{stage}_sent"))
            for stage in ("text", "audio", "image", "video")
        )

from datetime import datetime

from ..constants import TYPE_CN_MAP
from ..database.keys import (
    BRIEFING_TARGET_ALIASES,
    GLOBAL_TARGET_ID,
    QZONE_TARGET_ID,
    XIAOHONGSHU_TARGET_ID,
)
from .taskbase import TaskServiceBase


class TaskProgressService(TaskServiceBase):
    """分享过程阶段进度。"""

    _PROGRESS_STEP_LABELS = {
        "content": "文案",
        "image": "配图",
        "video": "视频",
        "audio": "语音",
        "send": "发送",
    }

    _PROGRESS_STAGE_LABELS = {
        "prepare": "准备中",
        "content": "文案生成中",
        "image": "配图生成中",
        "video": "视频生成中",
        "audio": "语音生成中",
        "send": "发送中",
        "done": "已完成",
        "error": "失败",
        "empty": "空闲",
        "skipped": "已跳过",
    }

    def _progress_now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _progress_type_label(self, share_type) -> str:
        value = getattr(share_type, "value", share_type)
        value = str(value or "auto").strip()
        if value == "briefing":
            return "早报"
        return TYPE_CN_MAP.get(value, "自动" if value == "auto" else value)

    def _progress_source_label(self, source_type: str) -> str:
        return {
            "manual": "手动",
            "command": "自然语言",
            "scheduled": "定时",
            "smart_schedule": "智能定时",
        }.get(
            str(source_type or "").strip().lower(),
            str(source_type or "").strip() or "分享",
        )

    def progress_target_label(self, target_id: str, target_label: str = "") -> str:
        label = str(target_label or "").strip()
        if label:
            return label
        try:
            label = self.services.targets.get_contact_alias(target_id)
        except Exception:
            label = ""
        if label:
            return label
        raw = str(target_id or "").strip()
        known = {
            GLOBAL_TARGET_ID: "全局",
            QZONE_TARGET_ID: "QQ 空间",
            XIAOHONGSHU_TARGET_ID: "小红书",
            **dict.fromkeys(BRIEFING_TARGET_ALIASES, "早报"),
        }
        if raw in known:
            return known[raw]
        try:
            _adapter_id, real_id = self.ctx_service.parse_umo(raw)
            return real_id or raw or "当前任务"
        except Exception:
            return raw or "当前任务"

    def _progress_emit(
        self, event_type: str = "share_progress", payload: dict | None = None
    ) -> None:
        self.plugin.emit_dashboard_event(event_type, payload or {})

    def _progress_steps(self, enabled=None) -> list:
        enabled_set = set(
            self._PROGRESS_STEP_LABELS.keys() if enabled is None else enabled
        )
        return [
            {
                "key": key,
                "label": label,
                "status": "pending" if key in enabled_set else "skipped",
            }
            for key, label in self._PROGRESS_STEP_LABELS.items()
        ]

    def start_share_progress(
        self,
        *,
        source_type: str,
        target_id: str = "",
        target_label: str = "",
        share_type=None,
        total_targets: int = 1,
        current_index: int = 1,
        enabled_steps=None,
        message: str = "",
    ) -> str:
        seq = self.state.share_progress_seq + 1
        self.state.share_progress_seq = seq
        job_id = f"share-{seq}"
        now = self._progress_now()
        progress = {
            "id": job_id,
            "status": "running",
            "stage": "prepare",
            "stage_label": self._PROGRESS_STAGE_LABELS["prepare"],
            "message": message or self._PROGRESS_STAGE_LABELS["prepare"],
            "source_type": str(source_type or "").strip(),
            "source_label": self._progress_source_label(source_type),
            "target_id": str(target_id or "").strip(),
            "target_label": self.progress_target_label(target_id, target_label),
            "share_type": getattr(share_type, "value", share_type) or "auto",
            "share_type_label": self._progress_type_label(share_type),
            "total_targets": max(1, int(total_targets or 1)),
            "current_index": max(1, int(current_index or 1)),
            "started_at": now,
            "updated_at": now,
            "finished_at": "",
            "steps": self._progress_steps(enabled_steps),
        }
        self.state.share_progress = progress
        self._progress_emit("share_progress", progress)
        return job_id

    def update_share_progress(
        self,
        job_id: str = "",
        stage: str = "",
        *,
        status: str = "running",
        message: str = "",
        step_status: str = "running",
        mark_previous_done: bool = True,
        extra: dict | None = None,
    ) -> None:
        if not job_id:
            return
        progress = self._active_share_progress(job_id)
        if progress is None:
            return

        stage = str(stage or progress.get("stage") or "prepare").strip()
        now = self._progress_now()
        progress["status"] = status
        progress["stage"] = stage
        progress["stage_label"] = self._PROGRESS_STAGE_LABELS.get(stage, stage)
        progress["message"] = message or progress["stage_label"]
        progress["updated_at"] = now
        if status in {"done", "error", "empty"}:
            progress["finished_at"] = now
        if extra:
            progress.update(extra)

        self.update_share_progress_steps(
            progress,
            stage,
            step_status,
            message=message,
            mark_previous_done=mark_previous_done,
        )

        self.state.share_progress = progress
        self._progress_emit("share_progress", progress)

    def _active_share_progress(self, job_id: str) -> dict | None:
        progress = self.state.share_progress
        if not isinstance(progress, dict) or progress.get("id") != job_id:
            return None
        return progress

    @staticmethod
    def update_share_progress_steps(
        progress: dict,
        stage: str,
        step_status: str,
        *,
        message: str = "",
        mark_previous_done: bool,
    ) -> None:
        step_keys = [item["key"] for item in progress.get("steps", [])]
        if stage not in step_keys:
            return
        current_pos = step_keys.index(stage)
        for index, step in enumerate(progress["steps"]):
            if step.get("status") in {"skipped", "error"}:
                continue
            if index < current_pos and mark_previous_done:
                step["status"] = "done"
            elif index == current_pos:
                step["status"] = step_status
                if message:
                    step["message"] = message

    def skip_share_progress_step(
        self, job_id: str, stage: str, message: str = ""
    ) -> None:
        if not job_id:
            return
        progress = self.state.share_progress
        if not isinstance(progress, dict):
            return
        if progress.get("id") != job_id:
            return
        for step in progress.get("steps", []):
            if step.get("key") == stage:
                step["status"] = "skipped"
                if message:
                    step["message"] = message
                break
        progress["updated_at"] = self._progress_now()
        if message:
            progress["message"] = message
        self.state.share_progress = progress
        self._progress_emit("share_progress", progress)

    def complete_share_progress_step(
        self, job_id: str, stage: str, message: str = ""
    ) -> None:
        if not job_id:
            return
        progress = self.state.share_progress
        if not isinstance(progress, dict):
            return
        if progress.get("id") != job_id:
            return
        for step in progress.get("steps", []):
            if step.get("key") == stage and step.get("status") != "skipped":
                step["status"] = "done"
                if message:
                    step["message"] = message
                break
        progress["updated_at"] = self._progress_now()
        if message:
            progress["message"] = message
        self.state.share_progress = progress
        self._progress_emit("share_progress", progress)

    def fail_share_progress_step(
        self, job_id: str, stage: str, message: str = ""
    ) -> None:
        self.update_share_progress(
            job_id,
            stage,
            message=message,
            step_status="error",
            mark_previous_done=False,
        )

    def share_progress_degradation_reason(self, job_id: str) -> str:
        progress = self._active_share_progress(job_id)
        if progress is None:
            return ""
        reasons = []
        for step in progress.get("steps", []):
            if step.get("status") != "error":
                continue
            label = str(step.get("label") or step.get("key") or "媒体").strip()
            message = str(step.get("message") or "").strip()
            reason = message or f"{label}处理失败"
            if label and not reason.startswith(label):
                reason = f"{label}：{reason}"
            if reason not in reasons:
                reasons.append(reason)
        return "；".join(reasons)

    def finish_share_progress(
        self, job_id: str = "", *, success: bool = True, message: str = ""
    ) -> None:
        if not job_id:
            return
        status = "done" if success else "error"
        progress = self.state.share_progress
        if isinstance(progress, dict):
            if progress.get("id") != job_id:
                return
            for step in progress.get("steps", []):
                if step.get("status") == "skipped":
                    continue
                if success and step.get("status") in {"pending", "running"}:
                    step["status"] = "done"
                elif not success and step.get("status") == "running":
                    step["status"] = "error"
        self.update_share_progress(
            job_id,
            "done" if success else "error",
            status=status,
            message=message or ("分享完成" if success else "分享失败"),
        )

    def get_share_progress_snapshot(self) -> dict:
        progress = self.state.share_progress
        if not isinstance(progress, dict):
            return {
                "status": "idle",
                "stage": "empty",
                "stage_label": "空闲",
                "message": "空闲",
                "steps": self._progress_steps(enabled=[]),
            }
        snapshot = dict(progress)
        snapshot["steps"] = [dict(step) for step in progress.get("steps", [])]
        return snapshot

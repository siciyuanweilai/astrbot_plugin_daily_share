from __future__ import annotations

import re
from contextvars import ContextVar


class ShareMediaPending(Exception):
    """已受理的生成任务属于尚未完成的分享流程。"""


current_share_job: ContextVar[dict | None] = ContextVar("daily_share_job", default=None)


async def save_share_job(job: dict) -> None:
    service = job["service"]
    await service.save(job)


def media_error_message(value: object, default: str) -> str:
    """保留长度受限的诊断信息，移除凭据和带签名的资源 URL。"""
    if not isinstance(value, str) or not value.strip():
        return default
    text = re.sub(r"https?://[^\s<>\"']+", "[地址已隐藏]", value)
    text = re.sub(r"(?i)\b(?:Bearer|Basic)\s+[^\s,;\"']+", "[凭据已隐藏]", text)
    text = re.sub(
        r"(?i)(\b(?:api[_-]?key|access[_-]?token|token|authorization|password|secret|cookie)"
        r"\b[\"']?\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
        r"\1[已隐藏]",
        text,
    )
    text = re.sub(r"\b(?:sk-[\w-]+|AIza[\w-]+)\b", "[凭据已隐藏]", text)
    return " ".join(text.split())[:240] or default


def normalize_media_task_result(result: object, kind: str) -> dict:
    """查询结果不明确时，不得据此重新生成或发送。"""
    label = "图片" if kind == "image" else "视频"
    if not isinstance(result, dict):
        return {"status": "unavailable", "error": f"生活插件{label}任务返回格式无效"}
    status = str(result.get("status") or "").strip().lower()
    if status not in {"pending", "unavailable", "ready", "failed", "missing"}:
        return {"status": "unavailable", "error": f"生活插件{label}任务状态无法确认"}
    payload = {"status": status}
    if status == "ready":
        field = "path" if kind == "image" else "url"
        value = result.get(field)
        if isinstance(value, str) and value.strip():
            payload[field] = value.strip()
        else:
            payload.update(
                status="failed", error=f"原{label}任务已结束，但未返回有效成品"
            )
    elif status != "pending":
        default = {
            "unavailable": f"生活插件{label}任务暂时无法查询",
            "missing": "原媒体任务未登记，未重新提交",
            "failed": f"原{label}任务失败，未重新提交",
        }[status]
        payload["error"] = media_error_message(result.get("error"), default)
    return payload


def remember_media_task_result(job: dict, kind: str, result: dict) -> None:
    """按分享任务持久化结果，防止恢复时误用其他任务的错误信息。"""
    status = result["status"]
    media_status = {"ready": "ok", "failed": "error", "missing": "error"}.get(
        status, status
    )
    job.setdefault("media_results", {})[kind] = [media_status, result.get("error", "")]
    if status in {"pending", "unavailable"}:
        job["pending_media"] = kind
        return
    job["pending_media"] = ""
    if kind == "image":
        job.update(image_path=result.get("path", ""), image_failed=status != "ready")
    else:
        job.update(video_url=result.get("url", ""), video_started=True)

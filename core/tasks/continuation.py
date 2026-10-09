from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from functools import wraps
from pathlib import Path

from astrbot.api import logger

from ..config import ShareType, TimePeriod
from ..integrations.mediajob import ShareMediaPending, current_share_job
from ..schedule import normalize_schedule_mode

_STATE_KEY = "share_media_continuations"


def _encode(value):
    if isinstance(value, Enum):
        return {"enum": type(value).__name__, "value": value.value}
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (datetime, Path)):
        return str(value)
    raise TypeError(f"Unsupported sharing checkpoint value: {type(value).__name__}")


def _decode(value):
    if isinstance(value, dict) and value.get("enum") in {"ShareType", "TimePeriod"}:
        return {"ShareType": ShareType, "TimePeriod": TimePeriod}[value["enum"]](
            value["value"]
        )
    return value


def preserve_share(kind: str):
    """Checkpoint the prepared text and media owner, not a callable or old event."""

    def decorate(method):
        @wraps(method)
        async def run(self, *args, **kwargs):
            service = getattr(self.plugin, "share_continuations", None)
            if service is None:
                return await method(self, *args, **kwargs)
            current = current_share_job.get()
            if current is not None:
                return await method(self, *args, **kwargs)
            params = dict(
                inspect.signature(method).bind(self, *args, **kwargs).arguments
            )
            for key in ("self", "event", "finish_progress"):
                params.pop(key, None)
            params = json.loads(json.dumps(params, ensure_ascii=False, default=_encode))
            job = {
                "id": uuid.uuid4().hex,
                "kind": kind,
                "params": params,
                "status": "generating",
                "created_at": datetime.now().timestamp(),
                "service": service,
            }
            service.active.add(job["id"])
            try:
                await service.save(job)
            except BaseException:
                service.active.discard(job["id"])
                raise
            token = current_share_job.set(job)
            try:
                result = await method(self, *args, **kwargs)
            except ShareMediaPending:
                job["status"] = "pending"
                await service.save(job)
                progress_id = str(params.get("progress_id") or "")
                self.services.progress.update_share_progress(
                    progress_id,
                    "video" if job.get("pending_media") == "video" else "image",
                    message="媒体任务已受理，等待原任务成品",
                )
                logger.info(
                    "[日常分享] 媒体任务已受理，原文案和发布目标已保存，稍后继续分享"
                )
                return False
            except asyncio.CancelledError:
                if job["status"] != "submitting":
                    job["status"] = "pending"
                await service.save(job)
                raise
            except Exception:
                if job["status"] != "submitting":
                    job["status"] = "failed"
                await service.save(job)
                raise
            else:
                job["status"] = "completed" if result else "failed"
                await service.save(job)
                return result
            finally:
                service.active.discard(job["id"])
                current_share_job.reset(token)

        return run

    return decorate


class ShareContinuationService:
    def __init__(self, plugin):
        self.plugin = plugin
        self.active: set[str] = set()
        self._write_lock = asyncio.Lock()
        self._recovery_lock = asyncio.Lock()
        self._ambiguous_warned: set[str] = set()

    async def save(self, job: dict) -> None:
        payload = {key: value for key, value in job.items() if key != "service"}
        async with self._write_lock:
            await self.plugin.db.update_share_state(_STATE_KEY, {job["id"]: payload})

    async def mark_submitting(self) -> None:
        job = current_share_job.get()
        if job is not None:
            job["status"] = "submitting"
            await self.save(job)

    async def has_pending_share(self, target: str) -> bool:
        jobs = await self.plugin.db.get_share_state(_STATE_KEY, {})
        for job in jobs.values():
            if not isinstance(job, dict) or job.get("status") not in {
                "pending",
                "generating",
                "submitting",
            }:
                continue
            params = job.get("params") or {}
            original_target = (
                params.get("uid") or params.get("target_umo") or "qzone_broadcast"
            )
            if original_target != target:
                continue
            if job["status"] == "submitting" or not self.recovery_allowed(job)[1]:
                return True
        return False

    def recovery_allowed(self, job: dict) -> tuple[bool, bool]:
        """Keep original scheduling switches and quiet hours effective on recovery."""
        params = job.get("params") or {}
        scheduled = params.get("history_source") in {"scheduled", "smart"}
        maximum_age = 7200 if scheduled else 86400
        if (
            job.get("created_at")
            and datetime.now().timestamp() - job["created_at"] > maximum_age
        ):
            return False, True
        if not scheduled:
            return True, False
        if job["kind"] == "qzone":
            conf = self.plugin.qzone_conf
            if not conf.get("enable_qzone", False):
                return False, True
            quiet = conf.get("qzone_smart_schedule_quiet_hours", ["23:30-07:30"])
            mode = normalize_schedule_mode(
                conf.get("qzone_trigger_mode", "llm_smart"), "llm_smart"
            )
        else:
            if not self.plugin.config.get("enable_auto_share", False):
                return False, True
            target = params.get("uid") or params.get("target_umo")
            current_targets = (
                self.plugin.task_manager.share.resolve_execute_share_targets(
                    None, "all", exclude_custom_cron=False
                )
            )
            if target not in current_targets:
                return False, True
            quiet = self.plugin.basic_conf.get(
                "smart_schedule_quiet_hours", ["23:30-07:30"]
            )
            mode = normalize_schedule_mode(
                self.plugin.basic_conf.get("trigger_mode", "llm_smart"), "llm_smart"
            )
        if (
            mode == "llm_smart"
            and self.plugin.task_manager.schedule.smart.is_quiet_time(
                datetime.now(), quiet if isinstance(quiet, list) else []
            )
        ):
            return False, False
        return True, False

    async def recover_once(self) -> None:
        if self._recovery_lock.locked():
            return
        async with self._recovery_lock:
            jobs = await self.plugin.db.get_share_state(_STATE_KEY, {})
            for key, payload in jobs.items():
                if (
                    isinstance(payload, dict)
                    and payload.get("status") == "submitting"
                    and key not in self.active
                    and key not in self._ambiguous_warned
                ):
                    self._ambiguous_warned.add(key)
                    logger.warning(
                        f"[日常分享] 分享提交结果不明（任务 {key}），"
                        "已停止自动重发，请核对原发布目标"
                    )
                if (
                    key in self.active
                    or not isinstance(payload, dict)
                    or payload.get("status") not in {"pending", "generating"}
                ):
                    continue
                params = payload.get("params") or {}
                allowed, cancelled = self.recovery_allowed(payload)
                if not allowed:
                    if cancelled:
                        await self.save(
                            dict(
                                payload,
                                service=self,
                                status="cancelled",
                                reason="原分享任务已过时或自动发布已关闭，保留媒体成品，不补发",
                            )
                        )
                    continue
                target = (
                    params.get("uid") or params.get("target_umo") or "qzone_broadcast"
                )
                if self.plugin.runtime_service.is_share_busy(target):
                    continue
                kind = payload.get("pending_media") or "image"
                query = (
                    self.plugin.daily_life_bridge.get_video_task
                    if kind == "video"
                    else self.plugin.daily_life_bridge.get_image_task
                )
                result = await query(f"{key}:{kind}")
                if result.get("status") in {"pending", "unavailable"}:
                    continue
                job = dict(payload, service=self)
                if result.get("status") == "missing":
                    job.update(status="failed", reason="原媒体任务未登记，未重新提交")
                    await self.save(job)
                    continue
                if kind == "video":
                    job["video_url"] = (
                        str(result.get("url") or "")
                        if result.get("status") == "ready"
                        else ""
                    )
                    job["pending_media"] = ""
                    await self.resume(job)
                    continue
                if result.get("status") != "ready" or not result.get("path"):
                    if result.get("status") == "failed":
                        job.update(image_failed=True, pending_media="")
                        await self.resume(job)
                        continue
                    job.update(status="failed", reason="原图片任务无法恢复，未重新提交")
                    await self.save(job)
                    continue
                job["image_path"] = str(result["path"])
                if not job["image_path"].startswith(
                    ("https://", "http://")
                ) and not await asyncio.to_thread(Path(job["image_path"]).is_file):
                    job.update(status="failed", reason="原成品文件不存在，未重新生成")
                    await self.save(job)
                    continue
                await self.resume(job)
            # Keep unfinished and ambiguous submissions; bound only finished journals.
            async with self._write_lock:
                latest = await self.plugin.db.get_share_state(_STATE_KEY, {})
                finished = [
                    key
                    for key, value in latest.items()
                    if isinstance(value, dict)
                    and value.get("status") in {"completed", "failed", "cancelled"}
                ]
                for key in finished[:-100]:
                    latest.pop(key, None)
                if len(finished) > 100:
                    await self.plugin.db.set_share_state(_STATE_KEY, latest)

    async def resume(self, job: dict) -> None:
        params = json.loads(json.dumps(job["params"]), object_hook=_decode)
        target = params.get("uid") or params.get("target_umo") or "qzone_broadcast"
        manager = self.plugin.task_manager
        handlers = {
            "qzone": manager.qzone_share.send_prepared_qzone_share,
            "chat": manager.share.send_prepared_chat_share,
            "command": manager.command_share.send_prepared_command_share,
        }
        handler = handlers.get(job["kind"])
        if handler is None:
            return
        self.active.add(job["id"])
        token = current_share_job.set(job)
        try:
            async with self.plugin.runtime_service.get_share_lock(
                target, global_scope=job["kind"] == "qzone"
            ):
                if self.plugin._is_terminated:
                    return
                allowed, cancelled = self.recovery_allowed(job)
                if not allowed:
                    if cancelled:
                        job["status"] = "cancelled"
                    return
                result = await handler(**params, event=None)
                job["status"] = "completed" if result else "failed"
        except ShareMediaPending:
            job["status"] = "pending"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if job["status"] != "submitting":
                job["status"] = "failed"
            job["reason"] = type(exc).__name__
            logger.warning(
                f"[日常分享] 原分享任务续接失败，未自动重发：{type(exc).__name__}"
            )
        finally:
            await self.save(job)
            current_share_job.reset(token)
            self.active.discard(job["id"])

    async def run(self) -> None:
        while not self.plugin._is_terminated:
            try:
                await self.plugin.daily_life_bridge.flush_public_receipts()
                await self.recover_once()
            except Exception as exc:
                logger.warning(f"[日常分享] 联动任务恢复巡检失败：{type(exc).__name__}")
            await asyncio.sleep(45)

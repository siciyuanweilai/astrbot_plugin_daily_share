from __future__ import annotations

import asyncio
import hashlib
import uuid
import time
from collections import OrderedDict
from datetime import datetime
from contextvars import ContextVar
from typing import Any

from astrbot.api import logger

from .delivery import ShareDeliveryBridge
from .mediajob import (
    ShareMediaPending,
    current_share_job,
    normalize_media_task_result,
    remember_media_task_result,
    save_share_job,
)

DAILY_LIFE_PLUGIN_ID = "astrbot_plugin_daily_life"
_MEDIA_METHODS = {
    "image": "generate_share_image",
    "video": "generate_share_video",
    "audio": "generate_share_voice",
}


class DailyLifeBridge:
    """每日分享与生活插件之间唯一的公开调用边界。"""

    def __init__(self, context: Any, db: Any = None):
        self.context = context
        self.db = db
        self._receipt_lock = asyncio.Lock()
        self._search_notices: set[str] = set()
        self._memory_cache = OrderedDict()
        self._media_results: ContextVar[dict[str, tuple[str, str]]] = ContextVar(
            f"daily_share_media_results_{id(self)}",
            default={},
        )
        self.delivery = ShareDeliveryBridge(self)

    def _plugin(self):
        try:
            stars = self.context.get_all_stars()
        except Exception as exc:
            logger.debug(f"[日常分享] 读取生活插件状态失败: {exc}")
            return None

        for metadata in stars or []:
            if (
                str(metadata.root_dir_name or "").strip() != DAILY_LIFE_PLUGIN_ID
                and str(metadata.name or "").strip() != DAILY_LIFE_PLUGIN_ID
            ):
                continue
            if not metadata.activated or metadata.star_cls is None:
                return None
            return metadata.star_cls
        return None

    async def get_share_context(self, target_umo: str) -> dict:
        plugin = self._plugin()
        method = getattr(plugin, "get_share_context", None) if plugin else None
        if not callable(method):
            return {}
        try:
            result = await method(str(target_umo or "").strip())
            return result if isinstance(result, dict) else {}
        except Exception as exc:
            logger.warning(f"[上下文] 读取生活插件目标上下文失败: {exc}")
            return {}

    async def plan_voice(self, text: str, target_umo: str) -> dict:
        method = getattr(self._plugin(), "plan_share_voice", None)
        if not callable(method):
            return {"channel": "text", "valid": False}
        try:
            result = await method(text, target_umo)
            return result if isinstance(result, dict) else {"channel": "text", "valid": False}
        except Exception:
            return {"channel": "text", "valid": False}

    async def related_memory_prompt(self, query: str, target_umo: str = "qzone_broadcast") -> str:
        query = str(query or "").strip()[:1200]
        if not query:
            return ""
        method = getattr(self._plugin(), "search_share_memories", None)
        if not callable(method):
            return ""
        key = (target_umo, query)
        entry = self._memory_cache.get(key)
        if entry and time.monotonic() < entry[0]:
            self._memory_cache.move_to_end(key)
            return entry[1]
        try:
            rows = await asyncio.wait_for(method(query, target_umo, limit=3), timeout=1.0)
            lines = [f"- {str(row.get('occurred_at') or '')[:40]} {str(row.get('text') or '')[:400]}" for row in rows[:3] if isinstance(row, dict)]
        except Exception:
            return ""
        prompt = "【本地相关记忆，仅作背景；纠正信息优先】\n" + "\n".join(lines) if lines else ""
        self._memory_cache[key] = (time.monotonic() + 15, prompt)
        self._memory_cache.move_to_end(key)
        while len(self._memory_cache) > 64:
            self._memory_cache.popitem(last=False)
        return prompt

    async def coordinate_contact(self, target_umo: str, **kwargs) -> dict:
        method = getattr(self._plugin(), "coordinate_share_contact", None)
        if not callable(method):
            return {"allowed": True}
        try:
            result = await method(target_umo, **kwargs)
            return result if isinstance(result, dict) else {"allowed": False}
        except Exception as exc:
            logger.debug(f"[日常分享] 主动联系状态暂不可用：{type(exc).__name__}")
            return {"allowed": False, "reason": "生活插件暂不可用，稍后再联系"}

    async def prepare_image(self, source: str) -> dict:
        method = getattr(self._plugin(), "prepare_share_image", None)
        if not callable(method):
            return {"status": "ok", "source": source, "hint": ""}
        try:
            result = await method(source)
            return result if isinstance(result, dict) else {"status": "unavailable"}
        except Exception:
            return {"status": "unavailable"}

    async def describe_video(self, source: str) -> dict:
        method = getattr(self._plugin(), "describe_share_video", None)
        if not callable(method):
            return {"status": "unavailable"}
        try:
            result = await method(source)
            return result if isinstance(result, dict) else {"status": "unavailable"}
        except Exception:
            return {"status": "unavailable"}

    async def get_share_chat_style_prompt(self, *, scene: str = "") -> str:
        """读取场景表达设置；普通分享同步聊天长度，公开场景保持自己的边界。"""
        plugin = self._plugin()
        method = getattr(plugin, "get_share_chat_style", None) if plugin else None
        if not callable(method):
            return ""
        try:
            result = await method(scene=scene) if scene else await method()
        except Exception as exc:
            logger.debug(f"[日常分享] 读取生活插件聊天表达失败: {exc}")
            return ""
        if not isinstance(result, dict) or result.get("enabled") is not True:
            return ""
        text = result.get("prompt")
        if not isinstance(text, str) or not text.strip():
            return ""
        chat_share = scene in {"share_private", "share_group"}
        text = " ".join(text.split())[: 1200 if chat_share else 500]
        if scene in {"qzone_comment", "qzone_reply"}:
            return f"【daily_life 聊天表达参考】\n{text}\n仅作语气与节奏参考，按当前公开互动任务输出正文。"
        boundary = "当前分享场景" if chat_share else "当前公开场景"
        return (
            f"【daily_life 聊天表达参考】\n{text}\n"
            f"此段作为{boundary}的语气与表达节奏参考。"
            "不覆盖本轮任务、人设、身份关系、事实与公开隐私边界；"
            + (
                "同步当前私聊/群聊的字数参考，标点由生活插件在生成后统一清洗；保留标题、名称和自定义排版。"
                if chat_share
                else "不套用聊天字数限制或分段发送；正常生成标点，正文提交前按生活插件设置统一清洗。"
            )
        )

    def search_available(self) -> bool:
        plugin = self._plugin()
        return (
            callable(getattr(plugin, "search_share_evidence", None))
            if plugin
            else False
        )

    def media_available(self, media_kind: str) -> bool:
        """检查生活插件是否暴露指定媒体入口，不代表调用一定成功。"""

        plugin = self._plugin()
        method_name = _MEDIA_METHODS.get(str(media_kind or "").strip().lower())
        return bool(
            plugin and method_name and callable(getattr(plugin, method_name, None))
        )

    def media_result(self, media_kind: str) -> tuple[str, str]:
        """读取当前任务最近一次媒体调用的状态与用户可读原因。"""

        key = str(media_kind or "").strip().lower()
        job = current_share_job.get()
        if job is not None:
            status, reason = job.get("media_results", {}).get(key, ("", ""))
            return status, reason
        return self._media_results.get().get(key, ("", ""))

    def _set_media_result(self, media_kind: str, status: str, reason: str = "") -> None:
        key = str(media_kind or "").strip().lower()
        if not key:
            return
        results = dict(self._media_results.get())
        results[key] = (str(status or "").strip(), str(reason or "").strip())
        self._media_results.set(results)
        job = current_share_job.get()
        if job is not None:
            job.setdefault("media_results", {})[key] = list(results[key])

    def _log_search_notice(
        self, key: str, message: str, *, warning: bool = False
    ) -> None:
        if key in self._search_notices:
            return
        self._search_notices.add(key)
        log = logger.warning if warning else logger.info
        log(message)

    async def search_evidence(
        self,
        query: str,
        *,
        category: str,
        target_umo: str = "",
    ) -> dict:
        """通过生活插件公开契约获取联网检索证据。"""
        plugin = self._plugin()
        method = getattr(plugin, "search_share_evidence", None) if plugin else None
        if not callable(method):
            self._log_search_notice(
                "unavailable",
                "[内容服务] 生活插件联网检索不可用，本次分享跳过联网补充资料。",
            )
            return {
                "status": "unavailable",
                "content": "",
                "error": "生活插件联网检索不可用",
            }
        try:
            result = await method(
                str(query or "").strip(),
                category=str(category or "").strip(),
                target_umo=str(target_umo or "").strip(),
            )
        except Exception as exc:
            detail = str(exc).strip()
            error_text = type(exc).__name__ + (f": {detail}" if detail else "")
            logger.warning(
                f"[内容服务] 生活插件联网检索失败，已跳过补充资料: {error_text}"
            )
            return {"status": "error", "content": "", "error": error_text}

        if not isinstance(result, dict):
            self._log_search_notice(
                "invalid-result",
                "[内容服务] 生活插件联网检索返回格式无效，已跳过补充资料。",
                warning=True,
            )
            return {
                "status": "error",
                "content": "",
                "error": "生活插件联网检索返回格式无效",
            }

        payload = dict(result)
        status = str(payload.get("status") or "error").strip().lower()
        content = str(payload.get("content") or "").strip()
        payload["status"] = status
        payload["content"] = content
        if status == "disabled":
            self._log_search_notice(
                "disabled",
                "[内容服务] 生活插件未启用联网检索，本次分享跳过联网补充资料。",
            )
        elif status != "ok":
            reason = str(payload.get("error") or "未返回可用结果").strip()
            logger.warning(
                f"[内容服务] 生活插件联网检索未完成，已跳过补充资料: {reason}"
            )
        elif not content:
            self._log_search_notice(
                "empty-result",
                "[内容服务] 生活插件联网检索未返回有效内容，已跳过补充资料。",
                warning=True,
            )
        return payload

    async def generate_image(
        self,
        event: Any,
        prompt: str,
        *,
        contains_character: bool = False,
    ) -> str:
        job = current_share_job.get()
        if job is not None and job.get("pending_media") == "image":
            return await self._accept_media_task_result(
                job, "image", await self.get_image_task(f"{job['id']}:image")
            )
        if job is not None and (job.get("image_path") or job.get("image_failed")):
            value = str(job.get("image_path") or "")
            status, reason = self.media_result("image")
            self._set_media_result(
                "image",
                "ok" if value else (status or "error"),
                "" if value else (reason or "原图片任务失败，未重新提交"),
            )
            return value
        plugin = self._plugin()
        task_method = getattr(plugin, "generate_share_image_task", None)
        if job is not None and not callable(task_method):
            self._set_media_result(
                "image", "unavailable", "生活插件缺少持久图片任务接口"
            )
            return ""
        if job is not None and callable(task_method):
            job.update(
                image_description=prompt,
                contains_character=contains_character,
                pending_media="image",
            )
            await save_share_job(job)
            try:
                result = await task_method(
                    event,
                    prompt,
                    task_key=f"{job['id']}:image",
                    contains_character=contains_character,
                    target_umo=self.share_target(job),
                )
            except Exception as exc:
                result = self._unconfirmed_media_result("图片", exc)
            return await self._accept_media_task_result(job, "image", result)
        return await self._call_media(
            "generate_share_image",
            "配图",
            event,
            prompt,
            contains_character=contains_character,
        )

    async def get_image_task(self, task_key: str) -> dict:
        return await self._get_media_task(task_key, "image")

    async def get_video_task(self, task_key: str) -> dict:
        return await self._get_media_task(task_key, "video")

    async def _get_media_task(self, task_key: str, kind: str) -> dict:
        plugin = self._plugin()
        method = getattr(plugin, f"get_share_{kind}_task", None)
        if not callable(method):
            return {
                "status": "unavailable",
                "error": "生活插件未就绪或缺少持久媒体查询接口，等待恢复",
            }
        try:
            result = await method(task_key)
            return normalize_media_task_result(result, kind)
        except Exception as exc:
            return self._unconfirmed_media_result("媒体查询", exc)

    @staticmethod
    def _unconfirmed_media_result(label: str, exc: Exception) -> dict:
        return {
            "status": "unavailable",
            "error": f"生活插件{label}暂时无法确认（{type(exc).__name__}），等待查询原任务",
        }

    async def _accept_media_task_result(
        self, job: dict, kind: str, result: object
    ) -> str:
        payload = normalize_media_task_result(result, kind)
        remember_media_task_result(job, kind, payload)
        self._set_media_result(kind, *job["media_results"][kind])
        await save_share_job(job)
        if payload["status"] in {"pending", "unavailable"}:
            raise ShareMediaPending(payload.get("error") or "原媒体任务仍在处理")
        return payload.get("path" if kind == "image" else "url", "")

    async def generate_video(
        self,
        event: Any,
        prompt: str,
        *,
        reference_image: str = "",
    ) -> str:
        job = current_share_job.get()
        if job is not None:
            if job.get("video_started"):
                if job.get("pending_media") == "video":
                    return await self._accept_media_task_result(
                        job, "video", await self.get_video_task(f"{job['id']}:video")
                    )
                value = str(job.get("video_url") or "")
                status, reason = self.media_result("video")
                self._set_media_result(
                    "video",
                    "ok" if value else (status or "error"),
                    "" if value else (reason or "原视频任务未返回有效成品，未重新提交"),
                )
                return value
            job["video_started"] = True
            await save_share_job(job)
            plugin = self._plugin()
            method = getattr(plugin, "generate_share_video_task", None)
            if callable(method):
                job["pending_media"] = "video"
                await save_share_job(job)
                try:
                    result = await method(
                        event,
                        prompt,
                        task_key=f"{job['id']}:video",
                        reference_image=reference_image,
                        target_umo=self.share_target(job),
                    )
                except Exception as exc:
                    result = self._unconfirmed_media_result("视频", exc)
                return await self._accept_media_task_result(job, "video", result)
            self._set_media_result(
                "video", "unavailable", "生活插件缺少持久视频任务接口"
            )
            return ""
        result = await self._call_media(
            "generate_share_video",
            "视频",
            event,
            prompt,
            reference_image=str(reference_image or "").strip(),
        )
        return result

    async def generate_voice(
        self,
        text: str,
        *,
        emotion: str = "",
        emotion_category: str = "",
        voice_style: str = "",
    ) -> str:
        job = current_share_job.get()
        if job is not None:
            if job.get("audio_started"):
                return str(job.get("audio_path") or "")
            job["audio_started"] = True
            await save_share_job(job)
        result = await self._call_media(
            "generate_share_voice",
            "语音",
            text,
            emotion=emotion,
            emotion_category=emotion_category,
            **({"voice_style": voice_style} if voice_style else {}),
        )
        if job is not None:
            job["audio_path"] = result
            await save_share_job(job)
        return result

    async def prepare_expression(
        self, text: str, *, scene: str, requirements: dict | None = None
    ) -> dict:
        plugin = self._plugin()
        method = getattr(plugin, "prepare_share_expression", None)
        if not callable(method):
            return {"text": text}
        try:
            options = {"requirements": requirements} if requirements is not None else {}
            result = await method(text, scene=scene, **options)
            return result if isinstance(result, dict) else {"text": text}
        except Exception as exc:
            logger.debug(f"[日常分享] 生活插件表达检查失败：{type(exc).__name__}")
            return {"text": text}

    async def clean_expression_punctuation(self, text: str, *, scene: str) -> str:
        plugin = self._plugin()
        method = getattr(plugin, "clean_share_punctuation", None)
        if not callable(method):
            return text
        try:
            result = await method(text, scene=scene)
            return result if isinstance(result, str) and result.strip() else text
        except Exception as exc:
            logger.debug(f"[日常分享] 生活插件标点清洗失败：{type(exc).__name__}")
            return text

    async def record_public_activity(self, receipt: dict) -> bool:
        self._memory_cache.clear()
        event_id = str(receipt.get("event_id") or "")
        if not event_id:
            return False
        key = hashlib.sha256(event_id.encode()).hexdigest()
        async with self._receipt_lock:
            if self.db is not None:
                await self.db.update_context_state(
                    "public_activity_outbox", {key: dict(receipt)}
                )
            delivered = await self._send_public_receipt(receipt)
            if delivered and self.db is not None:
                await self.db.update_context_state(
                    "public_activity_outbox", {key: None}
                )
            return delivered

    async def flush_public_receipts(self) -> None:
        await self.flush_delivery_receipts()
        await self.flush_external_receipts()
        if self.db is None:
            return
        async with self._receipt_lock:
            receipts = await self.db.get_context_state("public_activity_outbox", {})
            if not receipts:
                return
            remaining = {}
            for key, receipt in receipts.items():
                if isinstance(receipt, dict) and not await self._send_public_receipt(
                    receipt
                ):
                    remaining[key] = receipt
            await self.db.set_context_state("public_activity_outbox", remaining)

    async def _send_public_receipt(self, receipt: dict) -> bool:
        plugin = self._plugin()
        method = getattr(plugin, "record_public_activity", None)
        if not callable(method):
            return False
        try:
            return bool(await method(dict(receipt)))
        except Exception as exc:
            logger.warning(
                f"[日常分享] 公开活动回传失败，保留本地回执：{type(exc).__name__}"
            )
            return False

    async def _call_media(self, method_name: str, label: str, *args, **kwargs) -> str:
        media_kind = next(
            (kind for kind, name in _MEDIA_METHODS.items() if name == method_name),
            "",
        )
        self._set_media_result(media_kind, "")
        plugin = self._plugin()
        method = getattr(plugin, method_name, None) if plugin else None
        if not callable(method):
            self._set_media_result(
                media_kind,
                "unavailable",
                "生活插件未安装、未启用或正在重载",
            )
            logger.warning(
                f"[日常分享] 生活插件默认{label}工具不可用：未安装、未启用或正在重载"
            )
            return ""
        try:
            result = await method(*args, **kwargs)
            value = str(result or "").strip()
            if not value:
                self._set_media_result(
                    media_kind,
                    "empty",
                    f"生活插件{label}能力未返回有效结果",
                )
                logger.warning(f"[日常分享] 生活插件默认{label}工具未返回有效结果")
            else:
                self._set_media_result(media_kind, "ok")
            return value
        except Exception as exc:
            detail = str(exc).strip()
            error_text = type(exc).__name__ + (f": {detail}" if detail else "")
            if "尚未就绪或正在终止" in detail:
                self._set_media_result(
                    media_kind,
                    "unavailable",
                    "生活插件正在初始化、重载或停止",
                )
            elif method_name == "generate_share_video" and "视频任务超时" in detail:
                self._set_media_result(
                    media_kind,
                    "error",
                    "生活插件视频生成超时",
                )
            else:
                self._set_media_result(
                    media_kind,
                    "error",
                    f"生活插件{label}接口调用失败",
                )
            logger.warning(f"[日常分享] 生活插件默认{label}工具调用失败: {error_text}")
            return ""

    async def record_external_activity(
        self,
        target_umo: str,
        content: str,
        *,
        image_description: str = "",
        image_sent: bool = False,
        media_kind: str = "",
        reason: str,
        sync_memory: bool,
    ) -> bool:
        self._memory_cache.clear()
        plugin = self._plugin()
        if not callable(getattr(plugin, "record_external_activity_receipt", None)):
            legacy = getattr(plugin, "record_external_activity", None)
            if callable(legacy):
                try:
                    return bool(await legacy(target_umo, content, image_description=image_description, image_sent=image_sent, media_kind=media_kind, reason=reason, sync_memory=sync_memory))
                except Exception as exc:
                    logger.debug(f"[日常分享] 旧版生活插件活动回传失败，未自动重试：{type(exc).__name__}")
                    return False
        job = current_share_job.get()
        identity = f"{job['id']}:{target_umo}" if job else uuid.uuid4().hex
        receipt = {
            "event_id": f"daily_share:{identity}",
            "occurred_at": datetime.now().astimezone().isoformat(),
            "target_umo": str(target_umo or "").strip(),
            "content": str(content or "").strip(),
            "image_description": str(image_description or "").strip(),
            "image_sent": bool(image_sent), "media_kind": str(media_kind or ""),
            "reason": str(reason or ""), "sync_memory": bool(sync_memory),
        }
        key = hashlib.sha256(receipt["event_id"].encode()).hexdigest()
        async with self._receipt_lock:
            if job is not None:
                receipts = job.setdefault("external_activity_receipts", {})
                receipt = receipts.setdefault(key, receipt)
            if self.db is not None:
                pending = await self.db.get_context_state("external_activity_outbox", {})
                receipt = (pending or {}).get(key) or receipt
                await self.db.update_context_state("external_activity_outbox", {key: receipt})
            sent = await self._send_external_receipt(receipt)
            if sent and self.db is not None:
                await self.db.update_context_state("external_activity_outbox", {key: None})
            return sent

    async def _send_external_receipt(self, receipt: dict) -> bool:
        method = getattr(self._plugin(), "record_external_activity_receipt", None)
        if not callable(method):
            return False
        try:
            return bool(await method(dict(receipt)))
        except Exception as exc:
            logger.debug(f"[日常分享] 活动回执待补录：{type(exc).__name__}")
            return False

    async def flush_external_receipts(self) -> None:
        if self.db is None:
            return
        async with self._receipt_lock:
            receipts = await self.db.get_context_state("external_activity_outbox", {})
            remaining = {}
            for key, receipt in (receipts or {}).items():
                if isinstance(receipt, dict) and not await self._send_external_receipt(receipt):
                    remaining[key] = receipt
            if receipts:
                await self.db.set_context_state("external_activity_outbox", remaining)

    @staticmethod
    def share_target(job):
        return ShareDeliveryBridge.share_target(job)

    async def record_delivery(self, target_umo, sent_at, *, media_kinds=()):
        return await self.delivery.record_delivery(
            target_umo, sent_at, media_kinds=media_kinds
        )

    async def _send_delivery_receipt(self, receipt):
        return await self.delivery._send_delivery_receipt(receipt)

    async def flush_delivery_receipts(self):
        return await self.delivery.flush_delivery_receipts()


__all__ = ["DAILY_LIFE_PLUGIN_ID", "DailyLifeBridge"]

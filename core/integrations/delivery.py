from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from astrbot.api import logger

from .mediajob import current_share_job

if TYPE_CHECKING:
    from .dailylife import DailyLifeBridge


def confirmed_share_payload(content: str, description: str, result: dict) -> dict:
    """历史与生活回传共用实际送达事实，不把生成或可能送达当成成功。"""
    confirmed = {
        stage
        for stage in ("text", "audio", "image", "video")
        if result.get(f"{stage}_sent") and not result.get(f"{stage}_probable_sent")
    }
    if not confirmed:
        return {}
    kind = next(
        (stage for stage in ("video", "audio", "image") if stage in confirmed), ""
    )
    text = (
        content
        if confirmed.intersection({"text", "audio"})
        else f"[已分享{'视频' if kind == 'video' else '图片'}]"
    )
    return {
        "content": text,
        "description": description
        if confirmed.intersection({"image", "video"})
        else "",
        "image_sent": "image" in confirmed,
        "media_kind": kind,
    }


async def record_confirmed_history(
    context_service, target, content, description, result
):
    payload = confirmed_share_payload(content, description, result)
    if not payload:
        return
    text = payload["content"]
    image = payload["description"] if payload["image_sent"] else ""
    if payload["description"] and not payload["image_sent"]:
        text += f"\n[已分享视频: {payload['description']}]"
    await context_service.record_bot_reply_to_history(target, text, image_desc=image)


async def record_confirmed_share(
    context_service, target: str, content: str, description: str, result: dict
) -> None:
    payload = confirmed_share_payload(content, description, result)
    if payload:
        await context_service.record_external_share(
            target,
            payload["content"],
            payload["description"],
            image_sent=payload["image_sent"],
            media_kind=payload["media_kind"],
        )


class ShareDeliveryBridge:
    def __init__(self, owner: DailyLifeBridge) -> None:
        self.owner = owner

    @staticmethod
    def share_target(job: dict) -> str:
        if job.get("kind") == "qzone":
            return "qzone_broadcast"
        params = job.get("params") or {}
        return str(params.get("uid") or params.get("target_umo") or "")

    async def record_delivery(
        self, target_umo: str, sent_at: float, *, media_kinds: tuple[str, ...] = ()
    ) -> bool:
        job = current_share_job.get()
        tasks = {}
        if job and self.owner.share_target(job) == str(target_umo):
            for kind in media_kinds:
                if kind in {"image", "video"}:
                    tasks[kind] = f"{job['id']}:{kind}"
        receipt = {
            "target_umo": str(target_umo),
            "sent_at": sent_at,
            "media_tasks": tasks,
        }
        key = hashlib.sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest()
        async with self.owner._receipt_lock:
            if self.owner.db is not None:
                await self.owner.db.update_context_state(
                    "share_delivery_outbox", {key: receipt}
                )
            sent = await self.owner._send_delivery_receipt(receipt)
            if sent and self.owner.db is not None:
                await self.owner.db.update_context_state(
                    "share_delivery_outbox", {key: None}
                )
            return sent

    async def _send_delivery_receipt(self, receipt: dict) -> bool:
        method = getattr(self.owner._plugin(), "record_share_delivery", None)
        if not callable(method):
            return False
        try:
            return bool(await method(dict(receipt)))
        except Exception as exc:
            logger.warning(
                f"[日常分享] 发送时间/作品回传失败，保留回执：{type(exc).__name__}"
            )
            return False

    async def flush_delivery_receipts(self) -> None:
        if self.owner.db is None:
            return
        async with self.owner._receipt_lock:
            receipts = await self.owner.db.get_context_state(
                "share_delivery_outbox", {}
            )
            remaining = {}
            for key, receipt in (receipts or {}).items():
                if isinstance(
                    receipt, dict
                ) and not await self.owner._send_delivery_receipt(receipt):
                    remaining[key] = receipt
            if receipts:
                await self.owner.db.set_context_state(
                    "share_delivery_outbox", remaining
                )

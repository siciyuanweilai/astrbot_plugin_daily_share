from __future__ import annotations

import hashlib
import json

from astrbot.api import logger

from .mediajob import current_share_job


async def record_confirmed_share(
    context_service, target: str, content: str, description: str, result: dict
) -> None:
    confirmed = {
        stage
        for stage in ("text", "audio", "image", "video")
        if result.get(f"{stage}_sent") and not result.get(f"{stage}_probable_sent")
    }
    if not confirmed:
        return
    kind = next(
        (stage for stage in ("video", "audio", "image") if stage in confirmed), ""
    )
    text = (
        content
        if confirmed.intersection({"text", "audio"})
        else f"[已分享{'视频' if kind == 'video' else '图片'}]"
    )
    await context_service.record_external_share(
        target,
        text,
        description if confirmed.intersection({"image", "video"}) else "",
        image_sent="image" in confirmed,
        media_kind=kind,
    )


class ShareDeliveryBridge:
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
        if job and self.share_target(job) == str(target_umo):
            for kind in media_kinds:
                if kind in {"image", "video"}:
                    tasks[kind] = f"{job['id']}:{kind}"
        receipt = {
            "target_umo": str(target_umo),
            "sent_at": sent_at,
            "media_tasks": tasks,
        }
        key = hashlib.sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest()
        async with self._receipt_lock:
            if self.db is not None:
                await self.db.update_context_state(
                    "share_delivery_outbox", {key: receipt}
                )
            sent = await self._send_delivery_receipt(receipt)
            if sent and self.db is not None:
                await self.db.update_context_state("share_delivery_outbox", {key: None})
            return sent

    async def _send_delivery_receipt(self, receipt: dict) -> bool:
        method = getattr(self._plugin(), "record_share_delivery", None)
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
        if self.db is None:
            return
        async with self._receipt_lock:
            receipts = await self.db.get_context_state("share_delivery_outbox", {})
            remaining = {}
            for key, receipt in (receipts or {}).items():
                if isinstance(receipt, dict) and not await self._send_delivery_receipt(
                    receipt
                ):
                    remaining[key] = receipt
            if receipts:
                await self.db.set_context_state("share_delivery_outbox", remaining)

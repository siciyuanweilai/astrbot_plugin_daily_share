from __future__ import annotations

import time
from typing import Any

from astrbot.api import logger

from ...models import QzoneContext, QzonePost


class QzoneAlbumProbeConfirmMixin:
    """确认相册视频已公开，并生成可用于后续流程的动态对象。"""

    def _album_video_context_non_public_markers(self, cover_result: Any, probes: list[tuple[str, Any]]) -> list[str]:
        markers = self._album_video_non_public_context_markers(cover_result)
        for _source, payload in probes:
            markers.extend(self._album_video_non_public_context_markers(payload))
        return list(dict.fromkeys(markers))[:8]

    def _album_video_public_post(
        self,
        ctx: QzoneContext,
        expected_vid: str,
        item: dict[str, Any],
        item_context: dict[str, str],
        evidence: dict[str, Any],
        url: str,
        submitted_at: int,
    ) -> QzonePost:
        tid = str(
            self._first_nested_text(item, {"tid", "fid", "key", "cellid", "cellId"})
            or item_context.get("cellid")
            or item_context.get("photo_id")
            or item_context.get("sloc")
            or expected_vid
        )
        busi_param = {
            "album_video_public": evidence,
            "daily_share_result_type": self.RESULT_TYPE_ALBUM_VIDEO_DYNAMIC,
            "daily_share_vid": expected_vid,
            "daily_share_public_video_url": url,
        }
        for key in ("album_id", "photo_id", "sloc", "cellid", "video_share_h5", "busi_param_1"):
            value = str(item_context.get(key) or "").strip()
            if value:
                busi_param[f"daily_share_{key}"] = value
        return QzonePost(
            tid=tid,
            uin=ctx.uin,
            name=ctx.nickname or str(ctx.uin),
            text=str(self._first_nested_text(item, {"desc", "description", "content", "caption"}) or ""),
            videos=[f"qzone://video/{expected_vid}", url],
            create_time=int(time.time() if not submitted_at else max(submitted_at, int(time.time()))),
            appid=4,
            busi_param=busi_param,
        )

    async def _public_album_video_post_from_item(
        self,
        ctx: QzoneContext,
        expected_vid: str,
        payload: Any,
        item: dict[str, Any],
        cover_context: dict[str, str],
        context_non_public_markers: list[str],
        checked_urls: set[str],
        submitted_at: int,
    ) -> tuple[QzonePost | None, dict[str, Any]]:
        evidence = self._album_video_public_evidence(self._album_video_evidence_payload(payload, item))
        if context_non_public_markers:
            evidence = {
                **evidence,
                "public": False,
                "context_non_public_markers": context_non_public_markers,
            }
        item_context = self._album_video_context({"cover": cover_context, "item": item})
        if evidence.get("non_public_markers") or not evidence.get("public"):
            return None, evidence

        last_evidence = evidence
        for url in evidence.get("urls") or []:
            url = str(url or "").strip()
            if not url or url in checked_urls:
                continue
            checked_urls.add(url)
            if not self._contains_public_album_video_url(url):
                continue
            probe = await self._probe_public_album_video_url(url)
            if probe.get("state") == "success":
                evidence = {**evidence, "probe": probe, "public": True}
                post = self._album_video_public_post(
                    ctx,
                    expected_vid,
                    item,
                    item_context,
                    evidence,
                    url,
                    submitted_at,
                )
                logger.info("[每日分享] 已确认 QQ 空间视频资源可公开访问。")
                return post, evidence
            last_evidence = {**evidence, "probe": probe}
        return None, last_evidence

    async def _confirm_album_video_public(
        self,
        ctx: QzoneContext,
        vid: str,
        *,
        cover_result: Any = None,
        submitted_at: int = 0,
    ) -> QzonePost | None:
        expected_vid = str(vid or "").strip()
        if not expected_vid:
            return None
        context = self._album_video_context(cover_result)
        album_id = context.get("album_id") or ""
        photo_key = context.get("sloc") or context.get("photo_id") or ""
        probes = await self._album_video_public_probes(ctx, album_id, photo_key)
        context_non_public_markers = self._album_video_context_non_public_markers(cover_result, probes)

        checked = 0
        hits = 0
        last_evidence: dict[str, Any] = {}
        checked_urls: set[str] = set()
        for source, payload in probes:
            if not payload:
                continue
            self._debug_qzone_video_payload(f"album-{source}", payload)
            for item in self._video_payload_items(payload):
                checked += 1
                if not self._item_contains_text(item, expected_vid):
                    continue
                hits += 1
                post, last_evidence = await self._public_album_video_post_from_item(
                    ctx,
                    expected_vid,
                    payload,
                    item,
                    context,
                    context_non_public_markers,
                    checked_urls,
                    submitted_at,
                )
                if post:
                    return post
        logger.debug(
            "[每日分享] QQ 空间相册视频未确认公开: "
            f"视频ID={expected_vid}，相册ID={album_id or '<空>'}，照片键={photo_key or '<空>'}，"
            f"检查条目数={checked}，相同视频ID命中数={hits}，证据={self._video_debug_value('evidence', last_evidence)}"
        )
        self._last_album_video_public_evidence = last_evidence
        return None

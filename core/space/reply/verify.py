from __future__ import annotations

import asyncio
from typing import Any

from astrbot.api import logger

from ..models import QzoneComment, QzoneContext, QzonePost
from .identity import QzoneReplyIdentityMixin


class QzoneReplyVerifyMixin(QzoneReplyIdentityMixin):
    async def _verify_thread_reply_submission(
        self,
        post: QzonePost,
        comment: QzoneComment,
        content: str,
        *,
        parent_comment: QzoneComment | None,
        ctx: QzoneContext,
        submitted_at: int,
    ) -> dict[str, Any]:
        target_ids = self._reply_verification_target_ids(comment, parent_comment=parent_comment)
        parent_ids = self._comment_id_aliases(parent_comment)
        before_ids = self._reply_verification_existing_self_ids(post, int(ctx.uin or 0))
        base = {
            "status": "not_found",
            "target_ids": sorted(target_ids),
            "parent_ids": sorted(parent_ids),
            "submitted_at": int(submitted_at or 0),
            "candidates": [],
        }
        last = dict(base)
        for delay in (0.0, 0.8, 1.6):
            if delay:
                await asyncio.sleep(delay)
            try:
                fresh = await self.detail(post.key)
            except Exception as exc:
                last = {**base, "status": "detail_failed", "error": str(exc or "")}
                continue
            last = self._verify_thread_reply_in_post(
                fresh,
                comment,
                content,
                self_uin=int(ctx.uin or 0),
                target_ids=target_ids,
                parent_ids=parent_ids,
                before_ids=before_ids,
                submitted_at=int(submitted_at or 0),
            )
            if str(last.get("status") or "") in {"confirmed", "parent_target", "wrong_target"}:
                return last
        return last

    async def _cleanup_failed_thread_reply(
        self,
        post: QzonePost,
        verification: dict[str, Any],
        *,
        ctx: QzoneContext,
    ) -> dict[str, Any]:
        status = str((verification or {}).get("status") or "")
        if status not in {"parent_target", "wrong_target"}:
            return {}
        comment_id = str((verification or {}).get("verified_reply_tid") or "").strip()
        if not comment_id:
            return {"status": "skipped", "reason": "missing_verified_reply_tid"}
        try:
            result = await self.delete_comment(
                post,
                comment_id,
                comment_uin=int(ctx.uin or 0),
                ctx=ctx,
            )
            return {
                "status": "deleted",
                "comment_id": comment_id,
                "result": result,
            }
        except Exception as exc:
            logger.warning(f"[每日分享] QQ 空间错楼回评自动删除失败: {exc}")
            return {
                "status": "delete_failed",
                "comment_id": comment_id,
                "error": str(exc or ""),
            }

    @classmethod
    def _verify_thread_reply_in_post(
        cls,
        post: QzonePost,
        comment: QzoneComment,
        content: str,
        *,
        self_uin: int,
        target_ids: set[str],
        parent_ids: set[str],
        before_ids: set[str],
        submitted_at: int,
    ) -> dict[str, Any]:
        comments = list(getattr(post, "comments", []) or [])
        aliases = cls._comment_alias_map(comments)
        expected_texts = cls._reply_verification_text_variants(content)
        target_uin = int(getattr(comment, "uin", 0) or 0)
        candidates: list[dict[str, Any]] = []
        best_wrong: dict[str, Any] | None = None

        for item in comments:
            if int(getattr(item, "uin", 0) or 0) != int(self_uin or 0):
                continue
            text_matches = cls._reply_verification_text_matches(item, expected_texts)
            is_new = cls._reply_verification_is_new_self_comment(
                item,
                before_ids=before_ids,
                submitted_at=submitted_at,
            )
            target_status = cls._reply_verification_target_status(
                item,
                aliases=aliases,
                target_ids=target_ids,
                parent_ids=parent_ids,
                target_uin=target_uin,
            )
            row = cls._reply_verification_candidate_debug(
                item,
                text_matches=text_matches,
                is_new=is_new,
                target_status=target_status,
            )
            if text_matches or target_status in {"target", "parent"}:
                candidates.append(row)
            if not text_matches or not is_new:
                continue
            if target_status == "target":
                return {
                    "status": "confirmed",
                    "target_ids": sorted(target_ids),
                    "parent_ids": sorted(parent_ids),
                    "verified_reply_tid": str(getattr(item, "tid", "") or ""),
                    "verified_reply_to_tid": str(getattr(item, "reply_to_tid", "") or ""),
                    "verified_reply_to_uin": int(getattr(item, "reply_to_uin", 0) or 0),
                    "candidates": candidates,
                    "detail_comment_count": len(comments),
                }
            if target_status == "parent":
                best_wrong = {
                    "status": "parent_target",
                    "target_ids": sorted(target_ids),
                    "parent_ids": sorted(parent_ids),
                    "verified_reply_tid": str(getattr(item, "tid", "") or ""),
                    "verified_reply_to_tid": str(getattr(item, "reply_to_tid", "") or ""),
                    "verified_reply_to_uin": int(getattr(item, "reply_to_uin", 0) or 0),
                    "candidates": candidates,
                    "detail_comment_count": len(comments),
                }
            elif best_wrong is None:
                best_wrong = {
                    "status": "wrong_target",
                    "target_ids": sorted(target_ids),
                    "parent_ids": sorted(parent_ids),
                    "verified_reply_tid": str(getattr(item, "tid", "") or ""),
                    "verified_reply_to_tid": str(getattr(item, "reply_to_tid", "") or ""),
                    "verified_reply_to_uin": int(getattr(item, "reply_to_uin", 0) or 0),
                    "candidates": candidates,
                    "detail_comment_count": len(comments),
                }

        if best_wrong is not None:
            best_wrong["candidates"] = candidates
            return best_wrong
        return {
            "status": "not_found",
            "target_ids": sorted(target_ids),
            "parent_ids": sorted(parent_ids),
            "candidates": candidates,
            "detail_comment_count": len(comments),
        }

    @classmethod
    def _reply_verification_target_ids(
        cls,
        comment: QzoneComment,
        *,
        parent_comment: QzoneComment | None,
    ) -> set[str]:
        target_ids = cls._comment_id_aliases(comment)
        parent_ids = cls._comment_id_aliases(parent_comment)
        precise_ids = target_ids - parent_ids
        return precise_ids or target_ids

    @classmethod
    def _reply_verification_existing_self_ids(cls, post: QzonePost, self_uin: int) -> set[str]:
        ids: set[str] = set()
        for item in getattr(post, "comments", []) or []:
            if int(getattr(item, "uin", 0) or 0) != int(self_uin or 0):
                continue
            ids.update(cls._comment_id_aliases(item))
        return ids

    @classmethod
    def _comment_alias_map(cls, comments: list[QzoneComment]) -> dict[str, QzoneComment]:
        aliases: dict[str, QzoneComment] = {}
        for item in comments:
            for alias in cls._comment_id_aliases(item):
                aliases.setdefault(alias, item)
        return aliases

    @classmethod
    def _reply_verification_target_status(
        cls,
        item: QzoneComment,
        *,
        aliases: dict[str, QzoneComment],
        target_ids: set[str],
        parent_ids: set[str],
        target_uin: int,
    ) -> str:
        reply_to_tid = str(getattr(item, "reply_to_tid", "") or "").strip()
        if not reply_to_tid:
            return "unknown"
        reply_ids = {reply_to_tid}
        reply_target = aliases.get(reply_to_tid)
        if reply_target is not None:
            reply_ids.update(cls._comment_id_aliases(reply_target))
        reply_to_uin = int(getattr(item, "reply_to_uin", 0) or 0)
        uin_matches = not reply_to_uin or not target_uin or reply_to_uin == target_uin
        if uin_matches and reply_ids & target_ids:
            return "target"
        if reply_ids & parent_ids:
            return "parent"
        return "other"

    @classmethod
    def _reply_verification_text_variants(cls, content: str) -> set[str]:
        text = str(content or "").strip()
        variants = {cls._normalize_reply_verification_text(text)}
        if text.startswith("@{"):
            end = text.find("}")
            if end >= 0:
                variants.add(cls._normalize_reply_verification_text(text[end + 1 :]))
        variants.discard("")
        return variants

    @staticmethod
    def _normalize_reply_verification_text(content: str) -> str:
        return " ".join(str(content or "").strip().split())

    @classmethod
    def _reply_verification_text_matches(cls, item: QzoneComment, expected_texts: set[str]) -> bool:
        if not expected_texts:
            return False
        actual_texts = cls._reply_verification_text_variants(str(getattr(item, "content", "") or ""))
        if actual_texts & expected_texts:
            return True
        return any(
            expected and actual and (expected in actual or actual in expected)
            for expected in expected_texts
            for actual in actual_texts
        )

    @classmethod
    def _reply_verification_is_new_self_comment(
        cls,
        item: QzoneComment,
        *,
        before_ids: set[str],
        submitted_at: int,
    ) -> bool:
        aliases = cls._comment_id_aliases(item)
        if aliases and aliases & before_ids:
            return False
        created_at = int(getattr(item, "create_time", 0) or 0)
        return not created_at or not submitted_at or created_at >= submitted_at - 120

    @staticmethod
    def _reply_verification_candidate_debug(
        item: QzoneComment,
        *,
        text_matches: bool,
        is_new: bool,
        target_status: str,
    ) -> dict[str, Any]:
        content = str(getattr(item, "content", "") or "").strip()
        return {
            "tid": str(getattr(item, "tid", "") or ""),
            "submit_tid": str(getattr(item, "submit_tid", "") or ""),
            "raw_tid": str(getattr(item, "raw_tid", "") or ""),
            "parent_tid": str(getattr(item, "parent_tid", "") or ""),
            "reply_to_tid": str(getattr(item, "reply_to_tid", "") or ""),
            "raw_reply_to_tid": str(getattr(item, "raw_reply_to_tid", "") or ""),
            "reply_to_uin": int(getattr(item, "reply_to_uin", 0) or 0),
            "raw_reply_to_uin": int(getattr(item, "raw_reply_to_uin", 0) or 0),
            "reply_to_tid_source": str(getattr(item, "reply_to_tid_source", "") or ""),
            "raw_fields": dict(getattr(item, "raw_fields", {}) or {}),
            "uin": int(getattr(item, "uin", 0) or 0),
            "create_time": int(getattr(item, "create_time", 0) or 0),
            "content": content if len(content) <= 240 else f"{content[:240]}...",
            "text_matches": bool(text_matches),
            "new_comment": bool(is_new),
            "target_status": str(target_status or ""),
        }

    @staticmethod
    def _reply_verification_debug_fields(verification: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(verification, dict) or not verification:
            return {}
        fields = {
            "verification_status": str(verification.get("status") or ""),
            "verified_reply_tid": str(verification.get("verified_reply_tid") or ""),
            "verified_reply_to_tid": str(verification.get("verified_reply_to_tid") or ""),
            "verified_reply_to_uin": int(verification.get("verified_reply_to_uin") or 0),
            "verification_candidates": list(verification.get("candidates") or []),
            "verification_target_ids": list(verification.get("target_ids") or []),
            "verification_parent_ids": list(verification.get("parent_ids") or []),
        }
        if verification.get("error"):
            fields["verification_error"] = str(verification.get("error") or "")
        if isinstance(verification.get("cleanup"), dict):
            fields["verification_cleanup"] = dict(verification.get("cleanup") or {})
        return fields

    @staticmethod
    def _reply_verification_error_message(verification: dict[str, Any]) -> str:
        status = str((verification or {}).get("status") or "unknown")
        if status == "parent_target":
            return "QQ 空间回评落点校验失败：接口把回复挂到了父楼，已停止自动标记成功"
        if status == "not_found":
            return "QQ 空间回评落点校验失败：提交后未找到新回复，已停止自动标记成功"
        if status == "detail_failed":
            return "QQ 空间回评落点校验失败：提交后无法回查详情，已停止自动标记成功"
        return f"QQ 空间回评落点校验失败：{status}"

    @classmethod
    def _attach_reply_failure_debug(
        cls,
        exc: Exception,
        *,
        attempts: list[dict[str, Any]],
        attempted_targets: list[dict[str, Any]],
        verification: dict[str, Any] | None = None,
    ) -> None:
        setattr(exc, "attempts", [dict(item) for item in attempts])
        setattr(exc, "attempted_targets", [dict(item) for item in attempted_targets])
        if verification is not None:
            setattr(exc, "reply_verification_failed", True)
            setattr(exc, "verification", dict(verification))
            for key, value in cls._reply_verification_debug_fields(verification).items():
                setattr(exc, key, value)

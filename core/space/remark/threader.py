from __future__ import annotations

import time
from typing import Any

from ..methodset import QzoneMethodSet
from ..models import QzoneComment


class QzoneCommentReplyService(QzoneMethodSet):
    """编排 QQ 空间评论回评提交和落点校验。"""

    async def reply_comment(
        self,
        post_id: str,
        comment: QzoneComment,
        content: str,
        *,
        parent_comment: QzoneComment | None = None,
    ) -> dict[str, Any]:
        post = self._require_post(post_id)
        content = str(content or "").strip()
        if not content:
            raise RuntimeError("评论回复内容不能为空")
        thread_reply = parent_comment is not None
        reply_targets = self._reply_submit_targets(
            post, comment, parent_comment=parent_comment
        )
        if thread_reply:
            reply_targets = self._filter_thread_reply_targets(
                post,
                comment,
                parent_comment=parent_comment,
                targets=reply_targets,
            )
        if not reply_targets:
            raise RuntimeError("评论 ID 无效，无法回评")
        ctx = await self.context()
        submit_content = self._reply_content(content, comment)
        prefer_h5 = self._prefer_h5_reply(comment, parent_comment=parent_comment)

        last_payload: dict[str, Any] = {}
        attempts: list[dict[str, Any]] = []
        seen_attempts: set[tuple[str, str, str, int, str, int, str, int]] = set()
        plans = self._reply_submit_plans(
            ctx,
            post,
            comment,
            content=submit_content,
            parent_comment=parent_comment,
            reply_targets=reply_targets,
            prefer_h5=prefer_h5,
        )
        self._ensure_reply_plans(
            plans,
            thread_reply=thread_reply,
            post=post,
            comment=comment,
            parent_comment=parent_comment,
            reply_targets=reply_targets,
        )

        for plan in plans:
            request_data = dict(plan["data"])
            attempt_started_at = int(time.time())
            attempt_key = self._reply_attempt_key(plan, request_data)
            if attempt_key in seen_attempts:
                continue
            seen_attempts.add(attempt_key)
            payload = await self._request(
                "POST",
                str(plan["url"]),
                params={"g_tk": ctx.gtk},
                data=request_data,
                headers=plan.get("headers"),
                retry_parse_error=False,
            )
            attempt = self._reply_attempt_debug(plan, request_data, payload)
            attempts.append(attempt)
            if self._comment_submit_ok(payload):
                return await self._verified_reply_result(
                    post,
                    comment,
                    submit_content,
                    parent_comment=parent_comment,
                    ctx=ctx,
                    submitted_at=attempt_started_at,
                    thread_reply=thread_reply,
                    plan=plan,
                    attempt=attempt,
                    attempts=attempts,
                    reply_targets=reply_targets,
                )
            last_payload = payload

            if not thread_reply and not self._reply_target_unavailable(payload):
                break

        exc = RuntimeError(self._payload_message(last_payload) or "QQ 空间回评失败")
        self._attach_reply_failure_debug(
            exc,
            attempts=attempts,
            attempted_targets=reply_targets,
        )
        raise exc

    def _ensure_reply_plans(
        self,
        plans: list,
        *,
        thread_reply: bool,
        post,
        comment,
        parent_comment,
        reply_targets: list,
    ) -> None:
        if not thread_reply or plans:
            return
        unsafe_reason = self._unsafe_thread_reply_target_reason(
            comment, parent_comment=parent_comment
        )
        verification = {
            "status": "unsafe_synthetic_thread_target"
            if unsafe_reason
            else "not_found",
            "target_ids": sorted(self._comment_id_aliases(comment)),
            "parent_ids": sorted(self._comment_id_aliases(parent_comment)),
            "candidates": [],
            "detail_comment_count": len(getattr(post, "comments", []) or []),
            "error": unsafe_reason or "no_safe_thread_reply_submit_plan",
        }
        exc = RuntimeError(self._reply_verification_error_message(verification))
        self._attach_reply_failure_debug(
            exc, attempts=[], attempted_targets=reply_targets, verification=verification
        )
        raise exc

    @staticmethod
    def _reply_attempt_key(plan: dict, data: dict) -> tuple:
        return (
            str(plan.get("transport") or ""),
            str(data.get("topicId") or ""),
            str(data.get("commentId") or ""),
            int(data.get("commentUin") or 0),
            str(data.get("t2_tid") or ""),
            int(data.get("t2_uin") or 0),
            str(data.get("replyUin") or ""),
            int(data.get("t1_uin") or 0),
        )

    def _reply_attempt_debug(self, plan: dict, data: dict, payload: dict) -> dict:
        return {
            "transport": str(plan.get("transport") or ""),
            "variant": str(plan.get("variant") or ""),
            "comment_id": str(plan.get("comment_id") or ""),
            "comment_uin": int(plan.get("comment_uin") or 0),
            "payload_topic_id": str(data.get("topicId") or ""),
            "payload_comment_id": str(data.get("commentId") or ""),
            "payload_comment_uin": int(data.get("commentUin") or 0),
            "payload_reply_uin": int(data.get("replyUin") or 0),
            "payload_t1_tid": str(data.get("t1_tid") or ""),
            "payload_t1_uin": int(data.get("t1_uin") or 0),
            "payload_t2_tid": str(data.get("t2_tid") or ""),
            "payload_t2_uin": int(data.get("t2_uin") or 0),
            "code": payload.get("code"),
            "ret": payload.get("ret"),
            "message": self._payload_message(payload),
        }

    async def _verified_reply_result(
        self,
        post,
        comment,
        content: str,
        *,
        parent_comment,
        ctx,
        submitted_at: int,
        thread_reply: bool,
        plan: dict,
        attempt: dict,
        attempts: list,
        reply_targets: list,
    ) -> dict:
        verification: dict[str, Any] = {}
        if thread_reply:
            verification = await self._verify_thread_reply_submission(
                post,
                comment,
                content,
                parent_comment=parent_comment,
                ctx=ctx,
                submitted_at=submitted_at,
            )
            attempt.update(self._reply_verification_debug_fields(verification))
            if str(verification.get("status") or "") != "confirmed":
                cleanup = await self._cleanup_failed_thread_reply(
                    post, verification, ctx=ctx
                )
                if cleanup:
                    verification["cleanup"] = cleanup
                    attempt["cleanup"] = cleanup
                exc = RuntimeError(self._reply_verification_error_message(verification))
                self._attach_reply_failure_debug(
                    exc,
                    attempts=attempts,
                    attempted_targets=reply_targets,
                    verification=verification,
                )
                raise exc
        result = {
            "comment_id": str(plan.get("comment_id") or ""),
            "comment_uin": int(plan.get("comment_uin") or 0),
            "transport": str(plan.get("transport") or ""),
            "variant": str(plan.get("variant") or ""),
            "attempted_targets": [dict(item) for item in reply_targets],
            "attempts": attempts,
        }
        result.update(self._reply_verification_debug_fields(verification))
        self._invalidate_qzone_cache(post_id=post.key, target_id=str(post.uin))
        return result

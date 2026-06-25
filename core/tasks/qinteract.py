import asyncio
import time

from astrbot.api import logger

from .interact.comments import (
    QzoneCommentIndex,
    _comment_has_self_reply,
    _comment_replies_to_self,
    _post_has_self_comment,
)
from .interact.options import QzoneAutoInteractionConfig
from .interact.errors import (
    QzoneAutoInteractionRateLimited,
    _is_qzone_deleted_or_unavailable_error,
    _is_qzone_retry_later_error,
)
from .interact.executors import (
    execute_qzone_auto_comment_task,
    execute_qzone_auto_like_task,
    execute_qzone_auto_reply_task,
)
from .interact.formatting import _clean_auto_comment_text, _qzone_summary_generation_failed_suffix
from .interact.policy import QzoneAutoPolicyMixin
from .interact.dialogue import QzoneAutoPromptMixin
from .interact.response import (
    _qzone_copy_reply_verification_fields,
    _qzone_reply_exception_fields,
    _qzone_reply_skipped_payload,
    _qzone_reply_success_payload,
    _qzone_submitted_reply_fields,
)
from .interact.totals import (
    _qzone_empty_interaction_result,
    _qzone_log_interaction_summary,
    _qzone_merge_interaction_result,
    _qzone_should_log_interaction_summary,
)
from .interact.tracker import (
    QZONE_ACTION_RETRY_LATER,
    QZONE_ACTION_SKIPPED,
    QZONE_AUTO_COMMENT_DEFAULT_COOLDOWN_HOURS,
    QZONE_AUTO_COMMENT_DEFAULT_CRON,
    QZONE_AUTO_COMMENT_DEFAULT_INTERVAL_MINUTES,
    QZONE_AUTO_COMMENT_STATE_KEY,
    QZONE_AUTO_INTERACTION_DEFAULT_CRON,
    QZONE_AUTO_INTERACTION_DEFAULT_INTERVAL_MINUTES,
    QZONE_AUTO_INTERACTION_STATE_KEY,
    QZONE_AUTO_LIKE_DEFAULT_COOLDOWN_HOURS,
    QZONE_AUTO_LIKE_POLICY_VERSION,
    QZONE_AUTO_LIKE_STATE_KEY,
    QZONE_AUTO_REPLY_DEFAULT_COOLDOWN_HOURS,
    QZONE_AUTO_REPLY_DEFAULT_CRON,
    QZONE_AUTO_REPLY_DEFAULT_INTERVAL_MINUTES,
    QZONE_AUTO_REPLY_STATE_KEY,
    _mark_qzone_processed,
)
_QZONE_REPLY_ACTION_DELAY_SECONDS = 0.8


class TaskQzoneAutoCommentMixin(QzoneAutoPromptMixin, QzoneAutoPolicyMixin):
    """QQ 空间自动互动任务能力。"""

    def _qzone_auto_config(self) -> QzoneAutoInteractionConfig:
        return QzoneAutoInteractionConfig.from_conf(self.qzone_conf)

    def _qzone_auto_interaction_enabled(self) -> bool:
        cfg = self._qzone_auto_config()
        return bool(cfg.enable_interaction and cfg.child_enabled)

    def _qzone_auto_comment_prune_state(
        self,
        state: dict,
        *,
        now: int,
        cooldown_hours: int,
    ) -> dict:
        processed = state.get("processed") if isinstance(state, dict) else {}
        if not isinstance(processed, dict):
            processed = {}
        expires_before = now - cooldown_hours * 3600
        return {
            str(key): item
            for key, item in processed.items()
            if isinstance(item, dict) and int(item.get("at") or 0) >= expires_before
        }

    async def _qzone_auto_save_state(
        self,
        state_key: str,
        state: dict,
        processed: dict,
        result: dict,
        *,
        run_at: int | None = None,
    ) -> None:
        state.update(
            {
                "processed": processed,
                "last_run_at": int(run_at or time.time()),
                "last_result": result,
            }
        )
        await self.db.set_state(state_key, state)

    def _qzone_find_parent_comment(self, post, comment, *, index: QzoneCommentIndex = None):
        index = index or QzoneCommentIndex.build(post, 0)
        parent = index.parent_of(comment)
        if parent is None:
            return None
        parent_tid = str(getattr(parent, "tid", "") or "").strip()
        post_tid = str(getattr(post, "tid", "") or "").strip()
        return None if not parent_tid or parent_tid == post_tid else parent

    async def _qzone_send_auto_reply_result(
        self,
        post,
        comment,
        processed: dict,
        result: dict,
        *,
        item_key: str,
        reply: str,
        processed_action: str,
        dashboard_action: str,
        log_label: str,
        parent_comment_id: str = "",
        parent_comment=None,
        result_count_key: str = "replied",
    ) -> dict:
        submit_result = None
        try:
            if not reply:
                _mark_qzone_processed(processed, item_key, QZONE_ACTION_SKIPPED)
                result["skipped"] += 1
                return _qzone_reply_skipped_payload(reply)

            submit_result = await self.plugin.qzone_service.reply_comment(
                post.key,
                comment,
                reply,
                parent_comment=parent_comment,
            )
        except Exception as exc:
            exc_text = str(exc or "")
            fields = _qzone_reply_exception_fields(
                comment,
                reply,
                exc,
                parent_comment_id=parent_comment_id,
            )

            verification_failed = bool(getattr(exc, "reply_verification_failed", False))
            if verification_failed:
                _qzone_copy_reply_verification_fields(fields, exc)
                _mark_qzone_processed(
                    processed,
                    item_key,
                    QZONE_ACTION_SKIPPED,
                    reason=exc_text,
                    **fields,
                )
                result["skipped"] += 1
                return _qzone_reply_skipped_payload(
                    reply,
                    fields=fields,
                    error=exc_text,
                    verification_failed=True,
                    parent_comment_id=parent_comment_id,
                )

            if "已被删除" in exc_text or _is_qzone_deleted_or_unavailable_error(exc):
                _mark_qzone_processed(
                    processed,
                    item_key,
                    QZONE_ACTION_SKIPPED,
                    reason=exc_text,
                    **fields,
                )
                result["skipped"] += 1
                logger.info(f"[每日分享] QQ 空间自动回评跳过不可用楼层: {exc}")
                return _qzone_reply_skipped_payload(
                    reply,
                    fields=fields,
                    error=exc_text,
                    parent_comment_id=parent_comment_id,
                )
            if _is_qzone_retry_later_error(exc):
                _mark_qzone_processed(
                    processed,
                    item_key,
                    QZONE_ACTION_RETRY_LATER,
                    content=reply,
                    reason=exc_text,
                )
                retry_exc = QzoneAutoInteractionRateLimited(exc_text)
                if fields["attempted_targets"]:
                    setattr(retry_exc, "attempted_targets", fields["attempted_targets"])
                if fields["attempts"]:
                    setattr(retry_exc, "attempts", fields["attempts"])
                raise retry_exc from exc
            raise

        fields = _qzone_submitted_reply_fields(
            comment,
            reply,
            submit_result,
            parent_comment_id=parent_comment_id,
        )

        _mark_qzone_processed(processed, item_key, processed_action, **fields)
        count_key = str(result_count_key or "replied")
        result[count_key] = int(result.get(count_key, 0) or 0) + 1
        self.plugin._page_emit_dashboard_event(
            "qzone",
            {
                "action": dashboard_action,
                "post_id": post.key,
                "comment_id": str(getattr(comment, "tid", "") or ""),
            },
        )
        logger.info(
            f"[每日分享] {log_label}: "
            f"{getattr(comment, 'nickname', '') or getattr(comment, 'uin', '')}"
        )
        await asyncio.sleep(_QZONE_REPLY_ACTION_DELAY_SECONDS)
        return _qzone_reply_success_payload(reply, fields, parent_comment_id=parent_comment_id)

    async def execute_qzone_auto_comment(self, *, emit_summary: bool = True) -> dict:
        return await execute_qzone_auto_comment_task(self, emit_summary=emit_summary)

    async def execute_qzone_auto_like(self, *, emit_summary: bool = True) -> dict:
        return await execute_qzone_auto_like_task(self, emit_summary=emit_summary)

    async def execute_qzone_auto_reply(self, *, emit_summary: bool = True) -> dict:
        return await execute_qzone_auto_reply_task(self, emit_summary=emit_summary)

    async def execute_qzone_auto_interaction(self) -> dict:
        result = _qzone_empty_interaction_result()
        if self.plugin._is_terminated:
            return result
        cfg = self._qzone_auto_config()
        if not cfg.enable_qzone:
            logger.debug("[每日分享] QQ 空间未开启，跳过自动互动。")
            return result
        if not cfg.interaction_enabled:
            logger.debug("[每日分享] QQ 空间自动互动未开启，跳过。")
            return result

        result["enabled"] = True
        if cfg.enable_like:
            result["like"] = await self.execute_qzone_auto_like(emit_summary=False)
        if cfg.enable_comment:
            result["comment"] = await self.execute_qzone_auto_comment(emit_summary=False)
        if cfg.enable_reply:
            result["reply"] = await self.execute_qzone_auto_reply(emit_summary=False)

        _qzone_merge_interaction_result(result, result["like"], result["comment"], result["reply"])
        if _qzone_should_log_interaction_summary(result):
            _qzone_log_interaction_summary(result)
        return result

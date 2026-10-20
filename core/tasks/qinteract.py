import asyncio
import time
from typing import TYPE_CHECKING, Any

from astrbot.api import logger

from .interact.comments import (
    QzoneCommentIndex,
)
from .interact.comments import (
    _comment_has_self_reply as _comment_has_self_reply,
)
from .interact.comments import (
    _comment_replies_to_self as _comment_replies_to_self,
)
from .interact.comments import (
    _post_has_self_comment as _post_has_self_comment,
)
from .interact.dialogue import QzoneAutoPromptService
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
from .interact.formatting import _clean_auto_comment_text as _clean_auto_comment_text
from .interact.formatting import (
    _qzone_summary_generation_failed_suffix as _qzone_summary_generation_failed_suffix,
)
from .interact.options import QzoneAutoInteractionConfig
from .interact.policy import QzoneAutoPolicyService
from .interact.receipt import record_qzone_interaction
from .interact.response import (
    _qzone_copy_reply_verification_fields,
    _qzone_reply_exception_fields,
    _qzone_reply_skipped_payload,
    _qzone_reply_success_payload,
    _qzone_submitted_reply_fields,
)
from .interact.task import _qzone_result_rate_limited, checkpoint_qzone_action
from .interact.totals import (
    _qzone_empty_interaction_result,
    _qzone_log_interaction_summary,
    _qzone_merge_interaction_result,
    _qzone_should_log_interaction_summary,
)
from .interact.tracker import (
    QZONE_ACTION_RETRY_LATER,
    QZONE_ACTION_SKIPPED,
    QZONE_COMMENT_REPLY_POST_PREFIX,
    _mark_qzone_post_processed,
    _mark_qzone_processed,
)
from .interact.tracker import (
    QZONE_AUTO_COMMENT_DEFAULT_COOLDOWN_HOURS as QZONE_AUTO_COMMENT_DEFAULT_COOLDOWN_HOURS,
)
from .interact.tracker import (
    QZONE_AUTO_COMMENT_DEFAULT_CRON as QZONE_AUTO_COMMENT_DEFAULT_CRON,
)
from .interact.tracker import (
    QZONE_AUTO_COMMENT_STATE_KEY as QZONE_AUTO_COMMENT_STATE_KEY,
)
from .interact.tracker import (
    QZONE_AUTO_INTERACTION_DEFAULT_CRON as QZONE_AUTO_INTERACTION_DEFAULT_CRON,
)
from .interact.tracker import (
    QZONE_AUTO_INTERACTION_STATE_KEY as QZONE_AUTO_INTERACTION_STATE_KEY,
)
from .interact.tracker import (
    QZONE_AUTO_LIKE_DEFAULT_COOLDOWN_HOURS as QZONE_AUTO_LIKE_DEFAULT_COOLDOWN_HOURS,
)
from .interact.tracker import (
    QZONE_AUTO_LIKE_STATE_KEY as QZONE_AUTO_LIKE_STATE_KEY,
)
from .interact.tracker import (
    QZONE_AUTO_REPLY_DEFAULT_COOLDOWN_HOURS as QZONE_AUTO_REPLY_DEFAULT_COOLDOWN_HOURS,
)
from .interact.tracker import (
    QZONE_AUTO_REPLY_DEFAULT_CRON as QZONE_AUTO_REPLY_DEFAULT_CRON,
)
from .interact.tracker import (
    QZONE_AUTO_REPLY_STATE_KEY as QZONE_AUTO_REPLY_STATE_KEY,
)
from .taskbase import TaskServiceBase

_QZONE_REPLY_ACTION_DELAY_SECONDS = 0.8


class TaskQzoneAutoCommentService(TaskServiceBase):
    """QQ 空间自动互动任务能力。"""

    if TYPE_CHECKING:

        @property
        def plugin(self) -> Any: ...

        @property
        def db(self) -> Any: ...

        @property
        def qzone_conf(self) -> dict: ...

    def _qzone_auto_config(self) -> QzoneAutoInteractionConfig:
        return QzoneAutoInteractionConfig.from_conf(self.qzone_conf)

    def qzone_auto_interaction_enabled(self) -> bool:
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
        await self.db.update_qzone_state(
            state_key,
            {key: value for key, value in state.items() if key != "image_vision_cache"},
        )

    def _qzone_find_parent_comment(
        self, post, comment, *, index: QzoneCommentIndex | None = None
    ):
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
        state: dict,
        state_key: str,
        parent_comment_id: str = "",
        parent_comment=None,
        result_count_key: str = "replied",
        processed_post_action: str = "",
    ) -> dict:
        submit_result = None

        def mark_post(action: str) -> None:
            if processed_post_action:
                _mark_qzone_post_processed(
                    processed,
                    post,
                    action,
                    key_prefix=QZONE_COMMENT_REPLY_POST_PREFIX,
                    comment_id=str(getattr(comment, "tid", "") or ""),
                )

        try:
            if not reply:
                _mark_qzone_processed(processed, item_key, QZONE_ACTION_SKIPPED)
                result["skipped"] += 1
                if processed_post_action:
                    mark_post(QZONE_ACTION_SKIPPED)
                    await checkpoint_qzone_action(
                        self, state_key, state, processed, result
                    )
                logger.debug(
                    f"[日常分享] QQ 空间自动回评跳过: 生成结果为空，"
                    f"目标={getattr(comment, 'nickname', '') or getattr(comment, 'uin', '')}"
                )
                return _qzone_reply_skipped_payload(reply)

            bridge = getattr(self.plugin, "daily_life_bridge", None)
            clean = getattr(bridge, "clean_expression_punctuation", None)
            if callable(clean):
                reply = await clean(reply, scene="qzone_reply")
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

            if int(getattr(post, "appid", 311) or 311) == 4 and getattr(
                exc, "submission_unknown", False
            ):
                _mark_qzone_processed(
                    processed,
                    item_key,
                    QZONE_ACTION_SKIPPED,
                    reason=exc_text,
                    submission_unknown=True,
                    **fields,
                )
                mark_post(QZONE_ACTION_SKIPPED)
                if processed_post_action:
                    _mark_qzone_post_processed(
                        processed, post, QZONE_ACTION_SKIPPED, submission_unknown=True
                    )
                result["skipped"] += 1
                await checkpoint_qzone_action(self, state_key, state, processed, result)
                logger.warning(
                    f"[日常分享] QQ 空间相册回评提交状态未知，已停止自动重试，请查看照片确认: {exc_text}"
                )
                return _qzone_reply_skipped_payload(
                    reply, fields=fields, error=exc_text
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
                mark_post(QZONE_ACTION_SKIPPED)
                result["skipped"] += 1
                await checkpoint_qzone_action(self, state_key, state, processed, result)
                logger.debug(
                    f"[日常分享] QQ 空间自动回评落点校验未通过，已跳过: {exc_text}"
                )
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
                mark_post(QZONE_ACTION_SKIPPED)
                result["skipped"] += 1
                logger.info(f"[日常分享] QQ 空间自动回评跳过不可用楼层: {exc}")
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
        mark_post(processed_post_action)
        count_key = str(result_count_key or "replied")
        result[count_key] = int(result.get(count_key, 0) or 0) + 1
        await checkpoint_qzone_action(self, state_key, state, processed, result)
        await record_qzone_interaction(
            self,
            post,
            reply,
            scene="qzone_reply",
            comment_id=str(getattr(comment, "tid", "") or ""),
            actor_id=str(getattr(comment, "uin", "") or ""),
        )
        self.plugin.emit_dashboard_event(
            "qzone",
            {
                "action": dashboard_action,
                "post_id": post.key,
                "comment_id": str(getattr(comment, "tid", "") or ""),
            },
        )
        logger.info(
            f"[日常分享] {log_label}: "
            f"{getattr(comment, 'nickname', '') or getattr(comment, 'uin', '')}"
        )
        await asyncio.sleep(_QZONE_REPLY_ACTION_DELAY_SECONDS)
        return _qzone_reply_success_payload(
            reply, fields, parent_comment_id=parent_comment_id
        )

    async def execute_qzone_auto_comment(
        self,
        *,
        emit_summary: bool = True,
        target_id: str = "",
        target_umo: str = "",
    ) -> dict:
        return await execute_qzone_auto_comment_task(
            self,
            emit_summary=emit_summary,
            target_id=target_id,
            target_umo=target_umo,
        )

    async def execute_qzone_auto_like(
        self, *, emit_summary: bool = True, target_id: str = ""
    ) -> dict:
        return await execute_qzone_auto_like_task(
            self, emit_summary=emit_summary, target_id=target_id
        )

    async def execute_qzone_auto_reply(self, *, emit_summary: bool = True) -> dict:
        return await execute_qzone_auto_reply_task(self, emit_summary=emit_summary)

    async def execute_qzone_auto_interaction(self) -> dict:
        result = _qzone_empty_interaction_result()
        if self.plugin._is_terminated:
            return result
        cfg = self._qzone_auto_config()
        if not cfg.enable_qzone:
            logger.debug("[日常分享] QQ 空间未开启，跳过自动互动。")
            return result
        if not cfg.interaction_enabled:
            logger.debug("[日常分享] QQ 空间自动互动未开启，跳过。")
            return result

        result["enabled"] = True
        if cfg.enable_like:
            result["like"] = await self.execute_qzone_auto_like(emit_summary=False)
        if cfg.enable_comment and not _qzone_result_rate_limited(result["like"]):
            result["comment"] = await self.execute_qzone_auto_comment(
                emit_summary=False
            )
        if cfg.enable_reply and not (
            _qzone_result_rate_limited(result["like"])
            or _qzone_result_rate_limited(result["comment"])
        ):
            result["reply"] = await self.execute_qzone_auto_reply(emit_summary=False)

        _qzone_merge_interaction_result(
            result, result["like"], result["comment"], result["reply"]
        )
        if _qzone_should_log_interaction_summary(result):
            _qzone_log_interaction_summary(result)
        return result

    @staticmethod
    def _qzone_is_official_qzone_post(post):
        return QzoneAutoPolicyService._qzone_is_official_qzone_post(post)

    def _qzone_auto_active_window_hours(self):
        return self.policy._qzone_auto_active_window_hours()

    def _qzone_auto_timestamp_in_active_window(self, timestamp):
        return self.policy._qzone_auto_timestamp_in_active_window(timestamp)

    def _qzone_auto_post_in_active_window(self, post):
        return self.policy._qzone_auto_post_in_active_window(post)

    def _qzone_auto_comment_in_active_window(self, post, comment):
        return self.policy._qzone_auto_comment_in_active_window(post, comment)

    def _qzone_auto_comment_candidate(self, post, *, self_uin, processed, index=None):
        return self.policy._qzone_auto_comment_candidate(
            post, self_uin=self_uin, processed=processed, index=index
        )

    def _qzone_auto_comment_reply_candidate(
        self, post, comment, *, self_uin, processed, index=None
    ):
        return self.policy._qzone_auto_comment_reply_candidate(
            post,
            comment,
            self_uin=self_uin,
            processed=processed,
            index=index,
        )

    def _qzone_auto_like_candidate(self, post, *, self_uin, processed):
        return self.policy._qzone_auto_like_candidate(
            post, self_uin=self_uin, processed=processed
        )

    def _qzone_auto_reply_skip_reason(
        self, post, comment, *, self_uin, processed, index=None
    ):
        return self.policy._qzone_auto_reply_skip_reason(
            post, comment, self_uin=self_uin, processed=processed, index=index
        )

    def _qzone_auto_reply_candidate(
        self, post, comment, *, self_uin, processed, index=None
    ):
        return self.policy._qzone_auto_reply_candidate(
            post, comment, self_uin=self_uin, processed=processed, index=index
        )

    def _qzone_auto_reply_thread_skip_reason(
        self, post, parent_comment, comment, *, self_uin, processed, index=None
    ):
        return self.policy._qzone_auto_reply_thread_skip_reason(
            post,
            parent_comment,
            comment,
            self_uin=self_uin,
            processed=processed,
            index=index,
        )

    def _qzone_reply_thread_base_skip_reason(
        self, post, parent_comment, comment, *, self_uin, processed
    ):
        return self.policy._qzone_reply_thread_base_skip_reason(
            post, parent_comment, comment, self_uin=self_uin, processed=processed
        )

    def _qzone_auto_reply_thread_candidate(
        self, post, parent_comment, comment, *, self_uin, processed, index=None
    ):
        return self.policy._qzone_auto_reply_thread_candidate(
            post,
            parent_comment,
            comment,
            self_uin=self_uin,
            processed=processed,
            index=index,
        )

    def _qzone_friend_comment_thread_skip_reason(
        self, post, parent_comment, comment, *, self_uin, processed, index=None
    ):
        return self.policy._qzone_friend_comment_thread_skip_reason(
            post,
            parent_comment,
            comment,
            self_uin=self_uin,
            processed=processed,
            index=index,
        )

    @staticmethod
    def _qzone_auto_comment_post_summary(post):
        return QzoneAutoPromptService._qzone_auto_comment_post_summary(post)

    async def _qzone_auto_interaction_system_prompt(
        self, task_prompt, *, output_rule="", scene="qzone_comment"
    ):
        return await self.dialogue._qzone_auto_interaction_system_prompt(
            task_prompt, output_rule=output_rule, scene=scene
        )

    async def _qzone_auto_interaction_persona_prompt(self):
        return await self.dialogue._qzone_auto_interaction_persona_prompt()

    async def _qzone_auto_life_context_prompt(self, actor, *, role):
        return await self.dialogue._qzone_auto_life_context_prompt(actor, role=role)

    async def _qzone_auto_interaction_llm(
        self, prompt, *, system_prompt, max_bytes=0, target_umo=""
    ):
        return await self.dialogue._qzone_auto_interaction_llm(
            prompt,
            system_prompt=system_prompt,
            max_bytes=max_bytes,
            target_umo=target_umo,
        )

    async def _qzone_auto_comment_prompt(self, post, image_context):
        return await self.dialogue._qzone_auto_comment_prompt(post, image_context)

    async def generate_qzone_auto_comment(self, post, *, state=None, target_umo=""):
        return await self.dialogue.generate_qzone_auto_comment(
            post, state=state, target_umo=target_umo
        )

    async def generate_qzone_auto_photo_comment(
        self, post, photo_posts, *, state=None, target_umo=""
    ):
        return await self.dialogue.generate_qzone_auto_photo_comment(
            post, photo_posts, state=state, target_umo=target_umo
        )

    async def _generate_qzone_auto_reply(
        self,
        post,
        comment,
        *,
        state=None,
        target_umo="",
        as_post_owner=True,
        self_uin=0,
    ):
        return await self.dialogue._generate_qzone_auto_reply(
            post,
            comment,
            state=state,
            target_umo=target_umo,
            as_post_owner=as_post_owner,
            self_uin=self_uin,
        )

    async def _generate_qzone_auto_reply_thread(
        self, post, parent_comment, comment, *, state=None, target_umo=""
    ):
        return await self.dialogue._generate_qzone_auto_reply_thread(
            post, parent_comment, comment, state=state, target_umo=target_umo
        )

    def __init__(self, runtime, config, state) -> None:
        super().__init__(runtime, config, state)
        self.policy = QzoneAutoPolicyService(self)
        self.dialogue = QzoneAutoPromptService(self)

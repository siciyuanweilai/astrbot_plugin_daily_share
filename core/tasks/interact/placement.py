from ...space.reply.plans import QzoneReplyPlanService
from ...space.reply.recipients import QzoneReplyTargetService


def _reply_submit_targets(owner, post, comment, *, parent_comment=None) -> list[dict]:
    targets = QzoneReplyTargetService._reply_submit_targets(
        post, comment, parent_comment=parent_comment
    )
    if parent_comment is not None:
        targets = QzoneReplyTargetService._filter_thread_reply_targets(
            post,
            comment,
            parent_comment=parent_comment,
            targets=targets,
        )
    return targets


def _unsafe_thread_target_reason(owner, comment, *, parent_comment=None) -> str:
    return str(
        QzoneReplyTargetService.unsafe_thread_reply_target_reason(
            comment, parent_comment=parent_comment
        )
        or ""
    )


def _has_thread_reply_submit_plan(owner, post, comment, *, parent_comment=None) -> bool:
    if parent_comment is None:
        return False
    targets = _reply_submit_targets(owner, post, comment, parent_comment=parent_comment)
    return bool(
        QzoneReplyPlanService._thread_reply_payload_variants(
            post, comment, parent_comment, targets
        )
    )

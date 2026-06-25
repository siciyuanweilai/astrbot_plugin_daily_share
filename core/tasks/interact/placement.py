from .task import _qzone_service


def _reply_submit_targets(owner, post, comment, *, parent_comment=None) -> list[dict]:
    service = _qzone_service(owner)
    builder = getattr(service, "_reply_submit_targets", None)
    if not callable(builder):
        return []
    try:
        targets = builder(post, comment, parent_comment=parent_comment)
        if parent_comment is not None:
            filter_targets = getattr(service, "_filter_thread_reply_targets", None)
            if callable(filter_targets):
                targets = filter_targets(
                    post,
                    comment,
                    parent_comment=parent_comment,
                    targets=targets,
                )
        return targets
    except Exception:
        return []


def _unsafe_thread_target_reason(owner, comment, *, parent_comment=None) -> str:
    service = _qzone_service(owner)
    checker = getattr(service, "unsafe_thread_reply_target_reason", None)
    if not callable(checker):
        return ""
    try:
        return str(checker(comment, parent_comment=parent_comment) or "")
    except Exception:
        return ""


def _has_thread_reply_submit_plan(owner, post, comment, *, parent_comment=None) -> bool:
    if parent_comment is None:
        return False
    service = _qzone_service(owner)
    checker = getattr(service, "has_thread_reply_submit_plan", None)
    if callable(checker):
        try:
            return bool(checker(post, comment, parent_comment=parent_comment))
        except Exception:
            return False
    variant_builder = getattr(service, "_thread_reply_payload_variants", None)
    try:
        if not callable(variant_builder):
            return False
        targets = _reply_submit_targets(owner, post, comment, parent_comment=parent_comment)
        return bool(variant_builder(post, comment, parent_comment, targets))
    except Exception:
        return False

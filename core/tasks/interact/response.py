from __future__ import annotations

from typing import Any


QZONE_REPLY_VERIFICATION_FIELDS = (
    "verification_status",
    "verified_reply_tid",
    "verified_reply_to_tid",
    "verified_reply_to_uin",
    "verification_candidates",
    "verification_target_ids",
    "verification_parent_ids",
    "verification_error",
    "verification_cleanup",
)


def _qzone_dict_list(value: Any) -> list[dict]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _qzone_reply_base_fields(comment, reply: str, *, parent_comment_id: str = "") -> dict:
    fields = {
        "content": reply,
        "commenter": str(getattr(comment, "nickname", "") or getattr(comment, "uin", "") or ""),
    }
    if parent_comment_id:
        fields["parent_comment_id"] = parent_comment_id
    return fields


def _qzone_reply_exception_fields(comment, reply: str, exc: Exception, *, parent_comment_id: str = "") -> dict:
    fields = _qzone_reply_base_fields(comment, reply, parent_comment_id=parent_comment_id)
    fields["attempted_targets"] = _qzone_dict_list(getattr(exc, "attempted_targets", None))
    fields["attempts"] = _qzone_dict_list(getattr(exc, "attempts", None))
    return fields


def _qzone_copy_reply_verification_fields(fields: dict, source: Any) -> None:
    for key in QZONE_REPLY_VERIFICATION_FIELDS:
        if isinstance(source, dict):
            if key in source:
                fields[key] = source.get(key)
        elif hasattr(source, key):
            fields[key] = getattr(source, key)


def _qzone_submitted_reply_fields(comment, reply: str, submit_result: Any, *, parent_comment_id: str = "") -> dict:
    fields = _qzone_reply_base_fields(comment, reply, parent_comment_id=parent_comment_id)
    if not isinstance(submit_result, dict):
        return fields

    submitted_comment_id = str(submit_result.get("comment_id") or "").strip()
    submitted_comment_uin = int(submit_result.get("comment_uin") or 0)
    submitted_transport = str(submit_result.get("transport") or "").strip()
    if submitted_comment_id:
        fields["submitted_comment_id"] = submitted_comment_id
    if submitted_comment_uin:
        fields["submitted_comment_uin"] = submitted_comment_uin
    if submitted_transport:
        fields["submitted_transport"] = submitted_transport
    attempted_targets = _qzone_dict_list(submit_result.get("attempted_targets"))
    attempts = _qzone_dict_list(submit_result.get("attempts"))
    if attempted_targets:
        fields["attempted_targets"] = attempted_targets
    if attempts:
        fields["attempts"] = attempts
    _qzone_copy_reply_verification_fields(fields, submit_result)
    return fields


def _qzone_reply_skipped_payload(
    reply: str,
    *,
    fields: dict | None = None,
    error: str = "",
    verification_failed: bool = False,
    parent_comment_id: str = "",
) -> dict:
    fields = fields or {}
    payload = {
        "sent": False,
        "skipped": True,
        "reply": reply,
        "attempted_targets": fields.get("attempted_targets", []),
        "attempts": fields.get("attempts", []),
    }
    if error:
        payload["error"] = error
    if verification_failed:
        payload.update(
            {
                "verification_failed": True,
                "verification_status": fields.get("verification_status", ""),
                "verified_reply_tid": fields.get("verified_reply_tid", ""),
                "verified_reply_to_tid": fields.get("verified_reply_to_tid", ""),
                "verified_reply_to_uin": fields.get("verified_reply_to_uin", 0),
                "verification_candidates": fields.get("verification_candidates", []),
                "verification_cleanup": fields.get("verification_cleanup", {}),
            }
        )
    if parent_comment_id:
        payload["parent_comment_id"] = parent_comment_id
    return payload


def _qzone_reply_success_payload(reply: str, fields: dict, *, parent_comment_id: str = "") -> dict:
    return {
        "sent": True,
        "skipped": False,
        "reply": reply,
        "submitted_comment_id": fields.get("submitted_comment_id", ""),
        "submitted_comment_uin": fields.get("submitted_comment_uin", 0),
        "submitted_transport": fields.get("submitted_transport", ""),
        "verification_status": fields.get("verification_status", ""),
        "verified_reply_tid": fields.get("verified_reply_tid", ""),
        "verified_reply_to_tid": fields.get("verified_reply_to_tid", ""),
        "verified_reply_to_uin": fields.get("verified_reply_to_uin", 0),
        "verification_candidates": fields.get("verification_candidates", []),
        "attempted_targets": fields.get("attempted_targets", []),
        "attempts": fields.get("attempts", []),
        "parent_comment_id": parent_comment_id,
    }

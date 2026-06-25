import time
from typing import Any

from .comments import _comment_created_at, _comment_tid, _comment_uin


QZONE_AUTO_LIKE_POLICY_VERSION = 3
QZONE_AUTO_COMMENT_STATE_KEY = "qzone_auto_comment"
QZONE_AUTO_COMMENT_DEFAULT_CRON = "0 */2 * * *"
QZONE_AUTO_COMMENT_DEFAULT_INTERVAL_MINUTES = 60
QZONE_AUTO_COMMENT_DEFAULT_LIMIT = 3
QZONE_AUTO_COMMENT_DEFAULT_COOLDOWN_HOURS = 168
QZONE_AUTO_INTERACTION_STATE_KEY = "qzone_auto_interaction"
QZONE_AUTO_INTERACTION_DEFAULT_CRON = "0 */2 * * *"
QZONE_AUTO_INTERACTION_DEFAULT_INTERVAL_MINUTES = 45
QZONE_AUTO_LIKE_STATE_KEY = "qzone_auto_like"
QZONE_AUTO_LIKE_DEFAULT_LIMIT = 3
QZONE_AUTO_LIKE_DEFAULT_COOLDOWN_HOURS = 168
QZONE_AUTO_REPLY_STATE_KEY = "qzone_auto_reply"
QZONE_AUTO_REPLY_DEFAULT_CRON = "30 */2 * * *"
QZONE_AUTO_REPLY_DEFAULT_INTERVAL_MINUTES = 30
QZONE_AUTO_REPLY_DEFAULT_LIMIT = 3
QZONE_AUTO_REPLY_DEFAULT_COOLDOWN_HOURS = 168
QZONE_AUTO_INTERACTION_RATE_LIMIT_COOLDOWN_SECONDS = 600
QZONE_ACTION_SKIPPED = "skipped"
QZONE_ACTION_COMMENTED = "commented"
QZONE_ACTION_THREAD_COMMENTED = "thread_commented"
QZONE_ACTION_LIKED = "liked"
QZONE_ACTION_REPLIED = "replied"
QZONE_ACTION_THREAD_REPLIED = "thread_replied"
QZONE_ACTION_RETRY_LATER = "retry_later"


def _comment_key(post, comment) -> str:
    post_key = str(getattr(post, "key", "") or "").strip()
    comment_tid = _comment_tid(comment)
    if comment_tid:
        return f"{post_key}:{comment_tid}"
    content = str(getattr(comment, "content", "") or "").strip()
    created_at = _comment_created_at(comment)
    uin = _comment_uin(comment)
    return f"{post_key}:{uin}:{created_at}:{content[:32]}"


def _post_key(post) -> str:
    return str(getattr(post, "key", "") or "").strip()


def _mark_qzone_processed(processed: dict, key: Any, action: str, **fields: Any) -> None:
    item_key = str(key or "").strip()
    if not item_key:
        return
    processed[item_key] = {
        "at": int(time.time()),
        "action": action,
        **fields,
    }


def _mark_qzone_rate_limited(
    state: dict,
    *,
    reason: str,
    now: int,
    cooldown_seconds: int = QZONE_AUTO_INTERACTION_RATE_LIMIT_COOLDOWN_SECONDS,
) -> None:
    if not isinstance(state, dict):
        return
    cooldown = max(60, int(cooldown_seconds or QZONE_AUTO_INTERACTION_RATE_LIMIT_COOLDOWN_SECONDS))
    state["rate_limited_until"] = int(now or time.time()) + cooldown
    state["rate_limited_reason"] = str(reason or "").strip()


def _qzone_processed_action(processed: dict, key: Any) -> str:
    item = processed.get(str(key or "").strip()) if isinstance(processed, dict) else None
    return str(item.get("action") or "") if isinstance(item, dict) else ""


def _qzone_pending_reply(processed: dict, key: Any) -> str:
    item = processed.get(str(key or "").strip()) if isinstance(processed, dict) else None
    if not isinstance(item, dict) or str(item.get("action") or "") != QZONE_ACTION_RETRY_LATER:
        return ""
    return str(item.get("content") or "").strip()


def _qzone_like_processed_action(processed: dict, key: Any) -> str:
    item_key = str(key or "").strip()
    item = processed.get(item_key) if isinstance(processed, dict) else None
    if not isinstance(item, dict):
        return ""
    action = str(item.get("action") or "")
    if action == QZONE_ACTION_SKIPPED and int(item.get("policy_version") or 0) < QZONE_AUTO_LIKE_POLICY_VERSION:
        processed.pop(item_key, None)
        return ""
    return action


def _qzone_processed_thread_has_self_reply(post, parent_comment, processed: dict) -> bool:
    if not isinstance(processed, dict):
        return False
    parent_key = _comment_key(post, parent_comment)
    parent_item = processed.get(parent_key)
    if isinstance(parent_item, dict) and str(parent_item.get("action") or "") == QZONE_ACTION_REPLIED:
        return True

    parent_tid = str(getattr(parent_comment, "tid", "") or "").strip()
    if not parent_tid:
        return False
    for item in processed.values():
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or "")
        if action == QZONE_ACTION_THREAD_REPLIED and str(item.get("parent_comment_id") or "") == parent_tid:
            return True
    return False

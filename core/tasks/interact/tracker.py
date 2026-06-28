import hashlib
import time
from typing import Any

from .comments import _comment_created_at, _comment_tid, _comment_uin
from .formatting import _qzone_post_plain_text


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


def _post_stable_body_key(post) -> str:
    uin = str(getattr(post, "uin", "") or "").strip()
    appid = str(getattr(post, "appid", "") or "").strip()
    created_at = int(getattr(post, "create_time", 0) or 0)
    if not uin or not created_at:
        return ""
    content = _qzone_post_plain_text(post)
    images = getattr(post, "images", None) or []
    videos = getattr(post, "videos", None) or []
    if not content and not images and not videos:
        return ""
    identity = "|".join(
        (
            uin,
            appid,
            str(created_at),
            content[:260],
            str(len(images)),
            str(len(videos)),
        )
    )
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]
    return f"post:{uin}:{appid}:body:{digest}"


def _post_alias_keys(post) -> list[str]:
    keys = [_post_key(post)]
    uin = str(getattr(post, "uin", "") or "").strip()
    appid = str(getattr(post, "appid", "") or "").strip()
    for name in ("unikey", "curkey", "feed_key", "tid"):
        value = str(getattr(post, name, "") or "").strip()
        if not value:
            continue
        keys.append(f"post:{uin}:{appid}:{name}:{value}")
    keys.append(_post_stable_body_key(post))
    return list(dict.fromkeys(key for key in keys if key))


def _mark_qzone_processed(processed: dict, key: Any, action: str, **fields: Any) -> None:
    item_key = str(key or "").strip()
    if not item_key:
        return
    processed[item_key] = {
        "at": int(time.time()),
        "action": action,
        **fields,
    }


def _mark_qzone_post_processed(processed: dict, post, action: str, **fields: Any) -> None:
    keys = _post_alias_keys(post)
    if not keys:
        return
    primary_key = keys[0]
    alias_keys = keys[1:]
    payload_fields = {"post_alias_keys": alias_keys, **fields}
    _mark_qzone_processed(processed, primary_key, action, **payload_fields)
    for key in alias_keys:
        _mark_qzone_processed(processed, key, action, **fields)


def _qzone_processed_action(processed: dict, key: Any) -> str:
    item = processed.get(str(key or "").strip()) if isinstance(processed, dict) else None
    return str(item.get("action") or "") if isinstance(item, dict) else ""


def _qzone_post_processed_action(processed: dict, post) -> str:
    if not isinstance(processed, dict):
        return ""
    for key in _post_alias_keys(post):
        action = _qzone_processed_action(processed, key)
        if action:
            return action
    return ""


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


def _qzone_like_post_processed_action(processed: dict, post) -> str:
    if not isinstance(processed, dict):
        return ""
    for key in _post_alias_keys(post):
        action = _qzone_like_processed_action(processed, key)
        if action:
            return action
    return ""


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

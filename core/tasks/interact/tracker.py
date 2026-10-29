import hashlib
import time
from typing import Any

from .comments import _comment_created_at, _comment_tid, _comment_uin
from .formatting import _qzone_post_plain_text

QZONE_AUTO_COMMENT_STATE_KEY = "qzone_auto_comment"
QZONE_AUTO_COMMENT_DEFAULT_LIMIT = 3
QZONE_AUTO_COMMENT_DEFAULT_COOLDOWN_HOURS = 168
QZONE_AUTO_INTERACTION_STATE_KEY = "qzone_auto_interaction"
QZONE_AUTO_INTERACTION_DEFAULT_CRON = "0 */2 * * *"
QZONE_AUTO_LIKE_STATE_KEY = "qzone_auto_like"
QZONE_AUTO_LIKE_DEFAULT_LIMIT = 3
QZONE_AUTO_LIKE_DEFAULT_COOLDOWN_HOURS = 168
QZONE_AUTO_REPLY_STATE_KEY = "qzone_auto_reply"
QZONE_AUTO_REPLY_DEFAULT_LIMIT = 3
QZONE_AUTO_REPLY_DEFAULT_COOLDOWN_HOURS = 168
QZONE_ACTION_SKIPPED = "skipped"
QZONE_ACTION_COMMENTED = "commented"
QZONE_ACTION_COMMENT_REPLIED = "comment_replied"
QZONE_COMMENT_REPLY_POST_PREFIX = "comment-reply:"
QZONE_ACTION_THREAD_COMMENTED = "thread_commented"
QZONE_ACTION_LIKED = "liked"
QZONE_ACTION_REPLIED = "replied"
QZONE_ACTION_THREAD_REPLIED = "thread_replied"
QZONE_ACTION_RETRY_LATER = "retry_later"


def _comment_key(post, comment) -> str:
    post_key = str(getattr(post, "key", "") or "").strip()
    if int(getattr(post, "appid", 311) or 311) == 4:
        photos = getattr(post, "photo_targets", []) or []
        if (
            getattr(post, "photo_comment_scope", "photo") != "batch"
            and len(photos) == 1
            and photos[0].album_id
            and photos[0].pic_key
        ):
            post_key = f"{post.uin}:photo:{photos[0].album_id}:{photos[0].pic_key}"
    comment_tid = _comment_tid(comment)
    if comment_tid:
        return f"{post_key}:{comment_tid}"
    content = str(getattr(comment, "content", "") or "").strip()
    created_at = _comment_created_at(comment)
    uin = _comment_uin(comment)
    return f"{post_key}:{uin}:{created_at}:{content[:32]}"


def _post_key(post) -> str:
    return str(getattr(post, "key", "") or "").strip()


def _photo_batch_key(post) -> str:
    if int(getattr(post, "appid", 311) or 311) != 4:
        return ""
    key = str(getattr(post, "photo_batch_key", "") or "").strip()
    if key:
        return key
    photos = getattr(post, "photo_targets", []) or []
    if len(photos) == 1 and photos[0].batch_id:
        return f"{post.uin}:photo-batch:{photos[0].album_id}:{photos[0].batch_id}"
    return ""


def _photo_target_key(post) -> str:
    if int(getattr(post, "appid", 311) or 311) != 4:
        return ""
    if getattr(post, "photo_comment_scope", "photo") == "batch":
        return f"batch:{post.photo_batch_topic_id}"
    photos = getattr(post, "photo_targets", []) or []
    return photos[0].key if len(photos) == 1 else ""


def _post_stable_body_key(post) -> str:
    uin = str(getattr(post, "uin", "") or "").strip()
    appid = str(getattr(post, "appid", "") or "").strip()
    created_at = int(getattr(post, "create_time", 0) or 0)
    if not uin or not created_at:
        return ""
    content = _qzone_post_plain_text(post)
    images = getattr(post, "images", None) or []
    rt_images = getattr(post, "rt_images", None) or []
    videos = getattr(post, "videos", None) or []
    if not content and not images and not rt_images and not videos:
        return ""
    identity = "|".join(
        (
            uin,
            appid,
            str(created_at),
            content[:260],
            str(len(images)),
            str(len(rt_images)),
            str(len(videos)),
        )
    )
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]
    return f"post:{uin}:{appid}:body:{digest}"


def _post_alias_keys(post) -> list[str]:
    keys = [_post_key(post)]
    uin = str(getattr(post, "uin", "") or "").strip()
    appid = str(getattr(post, "appid", "") or "").strip()
    if appid == "4":
        photos = getattr(post, "photo_targets", []) or []
        if (
            getattr(post, "photo_comment_scope", "photo") != "batch"
            and len(photos) == 1
            and photos[0].album_id
            and photos[0].pic_key
        ):
            keys.append(f"{uin}:photo:{photos[0].album_id}:{photos[0].pic_key}")
        keys.append(_photo_batch_key(post))
        if getattr(post, "photo_batch_key", "") and getattr(post, "feed_key", ""):
            keys.append(f"{uin}:{post.feed_key}")
    for name in ("unikey", "curkey", "feed_key", "tid"):
        value = str(getattr(post, name, "") or "").strip()
        if not value:
            continue
        keys.append(f"post:{uin}:{appid}:{name}:{value}")
    keys.append(_post_stable_body_key(post))
    return list(dict.fromkeys(key for key in keys if key))


def _mark_qzone_processed(
    processed: dict, key: Any, action: str, **fields: Any
) -> None:
    item_key = str(key or "").strip()
    if not item_key:
        return
    processed[item_key] = {
        "at": int(time.time()),
        "action": action,
        **fields,
    }


def _mark_qzone_post_processed(
    processed: dict, post, action: str, *, key_prefix: str = "", **fields: Any
) -> None:
    keys = [key_prefix + key for key in _post_alias_keys(post)]
    if not keys:
        return
    if not key_prefix:
        for key in keys:
            previous = processed.get(key)
            if (
                isinstance(previous, dict)
                and previous.get("action") == QZONE_ACTION_COMMENT_REPLIED
            ):
                processed.setdefault(
                    QZONE_COMMENT_REPLY_POST_PREFIX + key, dict(previous)
                )
    primary_key = keys[0]
    alias_keys = keys[1:]
    payload_fields = {"post_alias_keys": alias_keys, **fields}
    _mark_qzone_processed(processed, primary_key, action, **payload_fields)
    for key in alias_keys:
        _mark_qzone_processed(processed, key, action, **fields)


def _qzone_processed_action(processed: dict, key: Any) -> str:
    item = (
        processed.get(str(key or "").strip()) if isinstance(processed, dict) else None
    )
    return str(item.get("action") or "") if isinstance(item, dict) else ""


def _qzone_post_processed_action(processed: dict, post) -> str:
    if not isinstance(processed, dict):
        return ""
    for key in _post_alias_keys(post):
        action = _qzone_processed_action(processed, key)
        if action:
            return action
    return ""


def _qzone_comment_reply_participation(
    processed: dict, post
) -> tuple[set[int], int, bool]:
    """同一动态/上传批次已参与的用户、旧记录保留名额及暂停状态。"""
    users: set[int] = set()
    reserved = 0
    blocked = False
    for key in _post_alias_keys(post):
        previous = processed.get(key)
        if isinstance(previous, dict) and previous.get("submission_unknown"):
            blocked = True
        records = [processed.get(QZONE_COMMENT_REPLY_POST_PREFIX + key)]
        if (
            not isinstance(records[0], dict)
            and _qzone_processed_action(processed, key) == QZONE_ACTION_COMMENT_REPLIED
        ):
            records.append(previous)
        for item in records:
            if not isinstance(item, dict):
                continue
            if item.get("action") != QZONE_ACTION_COMMENT_REPLIED:
                blocked = True
                continue
            if isinstance(item.get("reply_users"), list):
                users.update(
                    int(uin)
                    for uin in item["reply_users"]
                    if str(uin).isdigit() and int(uin) > 0
                )
                reserved = max(reserved, int(item.get("reserved_reply_slots") or 0))
                continue
            # 旧版每条动态最多参与一人；优先从原提交记录恢复账号。
            comment_id = str(item.get("comment_id") or "")
            legacy_uin = 0
            for alias in [key, *(item.get("post_alias_keys") or [])]:
                target = processed.get(f"{alias}:{comment_id}")
                if isinstance(target, dict):
                    legacy_uin = int(target.get("submitted_comment_uin") or 0)
                    if legacy_uin:
                        break
            if not legacy_uin and comment_id:
                legacy_uin = next(
                    (
                        _comment_uin(comment)
                        for comment in post.comments
                        if _comment_tid(comment) == comment_id
                    ),
                    0,
                )
            if legacy_uin:
                users.add(legacy_uin)
            else:
                reserved = max(reserved, 1)
    return users, reserved, blocked


def _mark_qzone_comment_reply_post(processed: dict, post, comment, action: str) -> None:
    users, reserved, _ = _qzone_comment_reply_participation(processed, post)
    if action == QZONE_ACTION_COMMENT_REPLIED:
        users.add(_comment_uin(comment))
    _mark_qzone_post_processed(
        processed,
        post,
        action,
        key_prefix=QZONE_COMMENT_REPLY_POST_PREFIX,
        comment_id=_comment_tid(comment),
        reply_users=sorted(users - {0}),
        reserved_reply_slots=reserved,
    )


def _qzone_pending_reply(processed: dict, key: Any) -> str:
    item = (
        processed.get(str(key or "").strip()) if isinstance(processed, dict) else None
    )
    if (
        not isinstance(item, dict)
        or str(item.get("action") or "") != QZONE_ACTION_RETRY_LATER
    ):
        return ""
    return str(item.get("content") or "").strip()


def _qzone_like_processed_action(processed: dict, key: Any) -> str:
    item_key = str(key or "").strip()
    item = processed.get(item_key) if isinstance(processed, dict) else None
    if not isinstance(item, dict):
        return ""
    return str(item.get("action") or "")


def _qzone_like_post_processed_action(processed: dict, post) -> str:
    if not isinstance(processed, dict):
        return ""
    for key in _post_alias_keys(post):
        action = _qzone_like_processed_action(processed, key)
        if action:
            return action
    return ""


def _qzone_processed_thread_has_self_reply(
    post, parent_comment, processed: dict
) -> bool:
    if not isinstance(processed, dict):
        return False
    parent_key = _comment_key(post, parent_comment)
    parent_item = processed.get(parent_key)
    if isinstance(parent_item, dict) and str(parent_item.get("action") or "") in {
        QZONE_ACTION_REPLIED,
        QZONE_ACTION_COMMENT_REPLIED,
    }:
        return True

    parent_tid = str(getattr(parent_comment, "tid", "") or "").strip()
    if not parent_tid:
        return False
    photo_prefix = ""
    if int(getattr(post, "appid", 311) or 311) == 4:
        photos = getattr(post, "photo_targets", []) or []
        if len(photos) != 1:
            return False
        photo_prefix = (
            f"{post.key}:"
            if getattr(post, "photo_comment_scope", "photo") == "batch"
            else f"{post.uin}:photo:{photos[0].album_id}:{photos[0].pic_key}:"
        )
    for key, item in processed.items():
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or "")
        if (
            action == QZONE_ACTION_THREAD_REPLIED
            and str(item.get("parent_comment_id") or "") == parent_tid
            and (not photo_prefix or str(key).startswith(photo_prefix))
        ):
            return True
    return False

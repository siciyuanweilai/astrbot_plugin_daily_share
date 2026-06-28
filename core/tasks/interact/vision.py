from __future__ import annotations

import hashlib
from urllib.parse import quote, unquote, urlencode, urlsplit, urlunsplit

from astrbot.api import logger

from .formatting import _clean_auto_comment_text, _qzone_post_plain_text
from .tracker import QZONE_AUTO_COMMENT_STATE_KEY


QZONE_AUTO_COMMENT_IMAGE_VISION_CACHE_KEY = "image_vision_cache"
QZONE_AUTO_COMMENT_IMAGE_VISION_CACHE_MAX_ITEMS = 200
QZONE_IMAGE_ID_QUERY_KEYS = {
    "id",
    "fid",
    "tid",
    "uin",
    "pic",
    "picid",
    "pic_id",
    "photo",
    "photoid",
    "photo_id",
    "lloc",
    "sloc",
    "albumid",
    "album_id",
    "aid",
    "bo",
    "picbo",
}


def _qzone_image_vision_config(owner) -> tuple[bool, int, str]:
    getter = getattr(owner, "_qzone_auto_config", None)
    cfg = getter() if callable(getter) else None
    if cfg is not None and hasattr(cfg, "comment_image_vision_enabled"):
        return (
            bool(getattr(cfg, "comment_image_vision_enabled", False)),
            max(1, min(9, int(getattr(cfg, "comment_image_vision_limit", 1) or 1))),
            str(getattr(cfg, "comment_image_vision_provider", "") or "").strip(),
        )
    return False, 1, ""


def _qzone_post_image_urls(post, *, limit: int) -> list[str]:
    urls = []
    seen = set()
    for image in getattr(post, "images", []) or []:
        url = str(image or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
        if len(urls) >= limit:
            break
    return urls


def _qzone_image_vision_cache(state: dict | None) -> dict:
    if not isinstance(state, dict):
        return {}
    cache = state.get(QZONE_AUTO_COMMENT_IMAGE_VISION_CACHE_KEY)
    if not isinstance(cache, dict):
        cache = {}
        state[QZONE_AUTO_COMMENT_IMAGE_VISION_CACHE_KEY] = cache
    return cache


def _stable_qzone_image_url(image_url: str) -> str:
    raw = str(image_url or "").strip()
    if raw.startswith("//"):
        raw = f"https:{raw}"
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return raw

    query_items: list[tuple[str, str]] = []
    bare_items: list[str] = []
    for item in (parts.query or "").split("&"):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            if "/" in item or len(item) >= 16:
                bare_items.append(item)
            continue
        key, value = item.split("=", 1)
        key = key.strip().lower()
        if key in QZONE_IMAGE_ID_QUERY_KEYS:
            query_items.append((key, unquote(value.strip())))

    stable_query = "&".join(
        [quote(unquote(item), safe="/:._~-") for item in bare_items]
        + [urlencode(sorted(query_items), doseq=True)]
    ).strip("&")
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            quote(unquote(parts.path or "/"), safe="/:._~-"),
            stable_query,
            "",
        )
    )


def _qzone_image_url_cache_key(image_url: str) -> str:
    return hashlib.sha1(_stable_qzone_image_url(image_url).encode("utf-8")).hexdigest()[:16]


def _qzone_post_stable_identities(post) -> list[str]:
    identities = []
    seen = set()
    for name in ("unikey", "curkey", "feed_key", "tid"):
        value = str(getattr(post, name, "") or "").strip()
        identity = f"{name}:{value}" if value else ""
        if identity and identity not in seen:
            seen.add(identity)
            identities.append(identity)
    return identities


def _qzone_image_context_hash(*parts: object) -> str:
    identity = "|".join(str(part or "") for part in parts)
    return hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]


def _qzone_post_body_cache_identity(post) -> str:
    uin = str(getattr(post, "uin", "") or "").strip()
    appid = str(getattr(post, "appid", "") or "").strip()
    created_at = int(getattr(post, "create_time", 0) or 0)
    content = _qzone_post_plain_text(post)
    images = getattr(post, "images", None) or []
    videos = getattr(post, "videos", None) or []
    if not uin or not created_at or (not content and not images and not videos):
        return ""
    return _qzone_image_context_hash(
        "body",
        uin,
        appid,
        created_at,
        content[:260],
        len(images),
        len(videos),
    )


def _qzone_image_context_cache_keys(post, *, index: int, total: int) -> list[str]:
    prefix = (
        str(getattr(post, "uin", "") or ""),
        str(getattr(post, "name", "") or ""),
        str(getattr(post, "appid", "") or ""),
        str(index),
        str(total),
    )
    keys = [
        _qzone_image_context_hash(*prefix, "post", identity)
        for identity in _qzone_post_stable_identities(post)
    ]
    created_at = int(getattr(post, "create_time", 0) or 0)
    content = _qzone_post_plain_text(post)
    if created_at or content:
        keys.append(_qzone_image_context_hash(*prefix, "body", created_at, content[:260]))
    body_identity = _qzone_post_body_cache_identity(post)
    if body_identity:
        keys.append(_qzone_image_context_hash(*prefix, "post_body", body_identity))
    return list(dict.fromkeys(keys))


def _qzone_image_context_cache_key(post, *, index: int, total: int) -> str:
    keys = _qzone_image_context_cache_keys(post, index=index, total=total)
    return keys[0] if keys else ""


def _qzone_image_vision_cache_keys(post, image_url: str, *, index: int, total: int) -> list[str]:
    keys = [_qzone_image_url_cache_key(image_url)]
    keys.extend(_qzone_image_context_cache_keys(post, index=index, total=total))
    keys = list(dict.fromkeys(key for key in keys if key))
    return keys


def _prune_qzone_image_vision_cache(cache: dict) -> None:
    overflow = len(cache) - QZONE_AUTO_COMMENT_IMAGE_VISION_CACHE_MAX_ITEMS
    if overflow <= 0:
        return
    for key in list(cache.keys())[:overflow]:
        cache.pop(key, None)


async def _save_qzone_image_vision_cache(owner, state: dict | None) -> None:
    if not isinstance(state, dict):
        return
    db = getattr(owner, "db", None)
    get_state = getattr(db, "get_state", None)
    set_state = getattr(db, "set_state", None)
    if not callable(set_state):
        return
    try:
        source_cache = dict(_qzone_image_vision_cache(state))
        if not source_cache:
            return
        latest = await get_state(QZONE_AUTO_COMMENT_STATE_KEY, {}) if callable(get_state) else {}
        if not isinstance(latest, dict):
            latest = {}
        latest_cache = _qzone_image_vision_cache(latest)
        latest_cache.update(source_cache)
        state[QZONE_AUTO_COMMENT_IMAGE_VISION_CACHE_KEY] = latest_cache
        await set_state(QZONE_AUTO_COMMENT_STATE_KEY, latest)
    except Exception as exc:
        logger.debug(f"[每日分享] QQ 空间好友动态配图识别缓存保存失败: {exc}")


def _qzone_completion_text(resp: object) -> str:
    if resp is None:
        return ""
    if isinstance(resp, str):
        return resp.strip()
    if isinstance(resp, dict):
        for key in ("completion_text", "completion", "text", "content"):
            value = resp.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for key in ("completion_text", "completion", "text", "content"):
        value = getattr(resp, key, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _qzone_provider_label(context, provider_id: str) -> str:
    provider_id = str(provider_id or "").strip()
    if not provider_id:
        return ""
    provider = None
    getter = getattr(context, "get_provider_by_id", None)
    if callable(getter):
        provider = getter(provider_id)
    if provider is None:
        provider_mgr = getattr(context, "provider_manager", None)
        provider = (getattr(provider_mgr, "inst_map", {}) or {}).get(provider_id)
    meta_call = getattr(provider, "meta", None)
    if callable(meta_call):
        try:
            meta = meta_call()
            model = str(getattr(meta, "model", "") or "").strip()
            provider_type = str(getattr(meta, "type", "") or "").strip()
            if model and provider_type:
                return f"{provider_id}({provider_type}/{model})"
            if model:
                return f"{provider_id}({model})"
        except Exception:
            pass
    return provider_id


def _qzone_default_provider_id(context) -> str:
    try:
        provider = context.get_using_provider() if hasattr(context, "get_using_provider") else None
    except Exception:
        provider = None
    meta_call = getattr(provider, "meta", None)
    if callable(meta_call):
        try:
            return str(getattr(meta_call(), "id", "") or "").strip()
        except Exception:
            return ""
    return ""


def _qzone_vision_provider_id(owner) -> tuple[str, str]:
    _enabled, _limit, vision_provider_id = _qzone_image_vision_config(owner)
    context = getattr(getattr(owner, "plugin", None), "context", None)
    if not context:
        return "", "missing_context"
    if vision_provider_id:
        return vision_provider_id, "qzone_vision"
    return _qzone_default_provider_id(context), "default"


async def _describe_qzone_image(owner, image_url: str) -> str:
    plugin = getattr(owner, "plugin", None)
    context = getattr(plugin, "context", None)
    provider_id, provider_source = _qzone_vision_provider_id(owner)
    if not context or not provider_id:
        logger.debug("[每日分享] QQ 空间好友动态配图识别跳过: 未找到可用视觉模型")
        return ""
    llm_generate = getattr(context, "llm_generate", None)

    prompt = (
        "请简要识别这张 QQ 空间动态配图。"
        "只写可见事实、可见文字和整体氛围，不要猜身份、关系、地点隐私或回复建议。"
        "输出 8-60 字中文短句。"
    )
    provider_label = _qzone_provider_label(context, provider_id)
    logger.debug(
        f"[每日分享] QQ 空间好友动态配图识别调用模型: {provider_label or provider_id}，来源={provider_source}"
    )
    if not callable(llm_generate):
        logger.debug("[每日分享] QQ 空间好友动态配图识别跳过: 当前运行环境缺少多模态调用接口")
        return ""
    result = await llm_generate(
        chat_provider_id=provider_id,
        prompt=prompt,
        image_urls=[image_url],
    )

    description = _clean_auto_comment_text(_qzone_completion_text(result), max_bytes=180)
    if not description:
        logger.debug("[每日分享] QQ 空间好友动态配图识别返回空，已按纯文字评论")
    return description


async def _qzone_auto_comment_image_context(owner, post, *, state: dict | None = None) -> str:
    enabled, limit, _provider_id = _qzone_image_vision_config(owner)
    if not enabled:
        return ""

    image_urls = _qzone_post_image_urls(post, limit=limit)
    if not image_urls:
        author = getattr(post, "name", "") or getattr(post, "uin", "") or ""
        logger.debug(f"[每日分享] QQ 空间好友动态配图识别已开启，但未解析到图片: {author}")
        return ""

    author = getattr(post, "name", "") or getattr(post, "uin", "") or ""
    logger.debug(f"[每日分享] QQ 空间好友动态配图识别开始: {author}，图片 {len(image_urls)} 张")
    cache = _qzone_image_vision_cache(state)
    descriptions = []
    cache_changed = False
    for index, image_url in enumerate(image_urls, start=1):
        cache_keys = _qzone_image_vision_cache_keys(post, image_url, index=index, total=len(image_urls))
        cached = next((str(cache.get(key) or "").strip() for key in cache_keys if cache.get(key)), "")
        if cached:
            for key in cache_keys:
                if not cache.get(key):
                    cache[key] = cached
                    cache_changed = True
            logger.debug(f"[每日分享] QQ 空间好友动态配图识别命中缓存: 图{index}，{cached}")
            descriptions.append(cached)
            continue
        try:
            description = await _describe_qzone_image(owner, image_url)
        except Exception as exc:
            logger.debug(f"[每日分享] QQ 空间好友动态配图识别跳过: {exc}")
            continue
        if not description:
            continue
        for key in cache_keys:
            cache[key] = description
        cache_changed = True
        descriptions.append(description)
        logger.debug(f"[每日分享] QQ 空间好友动态配图识别成功: 图{index}，{description}")

    before_prune_size = len(cache)
    _prune_qzone_image_vision_cache(cache)
    if cache_changed or len(cache) != before_prune_size:
        await _save_qzone_image_vision_cache(owner, state)
    if not descriptions:
        logger.debug(f"[每日分享] QQ 空间好友动态配图识别未获得有效摘要，按纯文字评论: {author}")
        return ""
    lines = [f"图{index}: {description}" for index, description in enumerate(descriptions, start=1)]
    return "【配图识别】\n" + "\n".join(lines)

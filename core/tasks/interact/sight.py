from __future__ import annotations

import asyncio
import hashlib
from urllib.parse import quote, unquote, urlencode, urlsplit, urlunsplit

from astrbot.api import logger

from .formatting import _clean_auto_comment_text, _qzone_post_plain_text
from .tracker import QZONE_AUTO_COMMENT_STATE_KEY, QZONE_AUTO_REPLY_STATE_KEY

QZONE_AUTO_COMMENT_IMAGE_VISION_CACHE_KEY = "image_vision_cache"
QZONE_AUTO_COMMENT_IMAGE_VISION_CACHE_MAX_ITEMS = 200
QZONE_IMAGE_VISION_TIMEOUT_SECONDS = 60.0
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
    cfg = owner._qzone_auto_config()
    return (
        bool(cfg.comment_image_vision_enabled),
        max(1, min(9, int(cfg.comment_image_vision_limit or 1))),
        str(cfg.comment_image_vision_provider or "").strip(),
    )


def _qzone_post_image_refs(post, *, limit: int) -> list[tuple[object, str, str]]:
    refs: list[tuple[object, str, str]] = []
    seen: set[str] = set()

    def add(scope: str, images) -> None:
        for image in images or []:
            url = str(image or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            refs.append((post, scope, url))
            if len(refs) >= limit:
                return

    add("正文配图", getattr(post, "images", []) or [])
    if len(refs) < limit:
        add("转发配图", getattr(post, "rt_images", []) or [])
    return refs


def _qzone_comment_image_refs(
    *items: tuple[object, str], limit: int
) -> list[tuple[object, str, str]]:
    refs: list[tuple[object, str, str]] = []
    seen: set[str] = set()
    for comment, scope in items:
        for image in getattr(comment, "images", []) or []:
            url = str(image or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            refs.append((comment, scope, url))
            if len(refs) >= limit:
                return refs
    return refs


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
    return hashlib.sha1(_stable_qzone_image_url(image_url).encode("utf-8")).hexdigest()[
        :16
    ]


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
    rt_images = getattr(post, "rt_images", None) or []
    videos = getattr(post, "videos", None) or []
    if (
        not uin
        or not created_at
        or (not content and not images and not rt_images and not videos)
    ):
        return ""
    return _qzone_image_context_hash(
        "body",
        uin,
        appid,
        created_at,
        content[:260],
        len(images),
        len(rt_images),
        len(videos),
    )


def _qzone_image_context_cache_keys(
    post, *, index: int, total: int, scope: str = ""
) -> list[str]:
    prefix = (
        str(getattr(post, "uin", "") or ""),
        str(getattr(post, "name", "") or getattr(post, "nickname", "") or ""),
        str(getattr(post, "appid", "") or ""),
        str(scope or ""),
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
        keys.append(
            _qzone_image_context_hash(*prefix, "body", created_at, content[:260])
        )
    body_identity = _qzone_post_body_cache_identity(post)
    if body_identity:
        keys.append(_qzone_image_context_hash(*prefix, "post_body", body_identity))
    return list(dict.fromkeys(keys))


def _qzone_image_context_cache_key(
    post, *, index: int, total: int, scope: str = ""
) -> str:
    keys = _qzone_image_context_cache_keys(post, index=index, total=total, scope=scope)
    return keys[0] if keys else ""


def _qzone_image_vision_cache_keys(
    post, image_url: str, *, index: int, total: int, scope: str = ""
) -> list[str]:
    keys = [_qzone_image_url_cache_key(image_url)]
    keys.extend(
        _qzone_image_context_cache_keys(post, index=index, total=total, scope=scope)
    )
    keys = list(dict.fromkeys(key for key in keys if key))
    return keys


def _prune_qzone_image_vision_cache(cache: dict) -> None:
    overflow = len(cache) - QZONE_AUTO_COMMENT_IMAGE_VISION_CACHE_MAX_ITEMS
    if overflow <= 0:
        return
    for key in list(cache.keys())[:overflow]:
        cache.pop(key, None)


async def _save_qzone_image_vision_cache(
    owner,
    state: dict | None,
    *,
    state_key: str = QZONE_AUTO_COMMENT_STATE_KEY,
) -> None:
    if not isinstance(state, dict):
        return
    try:
        source_cache = dict(_qzone_image_vision_cache(state))
        if not source_cache:
            return
        latest = await owner.db.get_qzone_state(state_key, {})
        if not isinstance(latest, dict):
            latest = {}
        latest_cache = _qzone_image_vision_cache(latest)
        latest_cache.update(source_cache)
        state[QZONE_AUTO_COMMENT_IMAGE_VISION_CACHE_KEY] = latest_cache
        await owner.db.set_qzone_state(state_key, latest)
    except Exception as exc:
        logger.debug(f"[日常分享] QQ 空间说说配图识别缓存保存失败: {exc}")


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
    try:
        provider = context.get_provider_by_id(provider_id)
    except (AttributeError, LookupError):
        return provider_id
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
        except Exception as exc:
            logger.debug(f"[日常分享] 读取 QQ 空间配图识别模型信息失败: {exc}")
    return provider_id


async def _qzone_session_provider_id(context, target_umo: str = "") -> str:
    target = str(target_umo or "").strip()
    if not target:
        return ""
    try:
        return str(await context.get_current_chat_provider_id(target) or "").strip()
    except Exception as exc:
        logger.debug(f"[日常分享] QQ 空间说说配图识别读取当前会话模型失败: {exc}")
        return ""


def _qzone_system_default_provider_id(context) -> str:
    try:
        cfg = context.get_config()
    except Exception as exc:
        logger.debug(f"[日常分享] QQ 空间说说配图识别读取默认模型配置失败: {exc}")
        cfg = None
    if isinstance(cfg, dict):
        provider_settings = cfg.get("provider_settings", {})
        if isinstance(provider_settings, dict):
            provider_id = str(
                provider_settings.get("default_provider_id") or ""
            ).strip()
            if provider_id:
                return provider_id
        for item in cfg.get("provider", []) or []:
            if not isinstance(item, dict) or not item.get("enable", False):
                continue
            provider_type = str(item.get("provider_type", "chat") or "")
            if "chat" in provider_type:
                return str(item.get("id") or "").strip()
    return ""


def _qzone_runtime_provider_id(context) -> str:
    try:
        provider = context.get_using_provider()
    except Exception:
        provider = None
    meta_call = getattr(provider, "meta", None)
    if callable(meta_call):
        try:
            return str(getattr(meta_call(), "id", "") or "").strip()
        except Exception:
            return ""
    return ""


async def _qzone_vision_provider_candidates(
    owner, *, target_umo: str = ""
) -> list[tuple[str, str]]:
    _enabled, _limit, vision_provider_id = _qzone_image_vision_config(owner)
    context = owner.plugin.context
    candidates: list[tuple[str, str]] = [
        (vision_provider_id, "qzone_vision"),
        (await _qzone_session_provider_id(context, target_umo), "session"),
        (_qzone_system_default_provider_id(context), "default"),
        (_qzone_runtime_provider_id(context), "default"),
    ]
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for provider_id, source in candidates:
        provider = str(provider_id or "").strip()
        if not provider or provider in seen:
            continue
        seen.add(provider)
        result.append((provider, source))
    return result


def _qzone_vision_fallback_log(
    previous_source: str, next_source: str, exc: Exception | None = None
) -> str:
    reason = f": {exc}" if exc else ""
    return (
        "[日常分享] QQ 空间说说配图识别模型不可用"
        f"（来源={previous_source}）{reason}，尝试降级使用{next_source}模型"
    )


async def _describe_qzone_image(owner, image_url: str, *, target_umo: str = "") -> str:
    context = owner.plugin.context
    provider_candidates = await _qzone_vision_provider_candidates(
        owner, target_umo=target_umo
    )
    if not provider_candidates:
        logger.debug("[日常分享] QQ 空间说说配图识别跳过: 未找到可用视觉模型")
        return ""

    prompt = (
        "请简要识别这张 QQ 空间动态配图。"
        "只写可见事实、可见文字和整体氛围，不要猜身份、关系、地点隐私或回复建议。"
        "输出 8-60 字中文短句。"
    )
    deadline = (
        asyncio.get_running_loop().time() + QZONE_IMAGE_VISION_TIMEOUT_SECONDS
    )
    for index, (provider_id, provider_source) in enumerate(provider_candidates):
        provider_label = _qzone_provider_label(context, provider_id)
        logger.debug(
            f"[日常分享] QQ 空间说说配图识别调用模型: {provider_label or provider_id}，来源={provider_source}"
        )
        try:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError
            result = await asyncio.wait_for(
                context.llm_generate(
                    chat_provider_id=provider_id,
                    prompt=prompt,
                    image_urls=[image_url],
                ),
                timeout=remaining,
            )
        except Exception as exc:
            next_item = (
                provider_candidates[index + 1]
                if index + 1 < len(provider_candidates)
                else None
            )
            if next_item:
                logger.debug(
                    _qzone_vision_fallback_log(provider_source, next_item[1], exc)
                )
                continue
            logger.debug(f"[日常分享] QQ 空间说说配图识别跳过: {exc}")
            return ""

        description = _clean_auto_comment_text(
            _qzone_completion_text(result), max_bytes=180
        )
        if description:
            return description
        next_item = (
            provider_candidates[index + 1]
            if index + 1 < len(provider_candidates)
            else None
        )
        if next_item:
            logger.debug(_qzone_vision_fallback_log(provider_source, next_item[1]))
            continue
        logger.debug("[日常分享] QQ 空间说说配图识别返回空，已按纯文字评论")
        return ""
    return ""


async def _qzone_image_refs_context(
    owner,
    image_refs: list[tuple[object, str, str]],
    *,
    state: dict | None = None,
    target_umo: str = "",
    state_key: str = QZONE_AUTO_COMMENT_STATE_KEY,
    label: str = "QQ 空间说说配图",
    heading: str = "配图识别",
    author: str = "",
    log_missing: bool = True,
) -> str:
    enabled_refs = _enabled_qzone_image_refs(
        owner, image_refs, label=label, author=author, log_missing=log_missing
    )
    if enabled_refs is None:
        return ""
    image_refs = enabled_refs

    logger.debug(f"[日常分享] {label}识别开始: {author}，图片 {len(image_refs)} 张")
    cache = _qzone_image_vision_cache(state)
    descriptions = []
    cache_changed = False
    for index, (source, scope, image_url) in enumerate(image_refs, start=1):
        cache_keys = _qzone_image_vision_cache_keys(
            source, image_url, index=index, total=len(image_refs), scope=scope
        )
        cached = next(
            (str(cache.get(key) or "").strip() for key in cache_keys if cache.get(key)),
            "",
        )
        if cached:
            changed = _fill_qzone_image_cache_aliases(cache, cache_keys, cached)
            cache_changed = cache_changed or changed
            logger.debug(
                f"[日常分享] {label}识别命中缓存: 图{index}（{scope}），{cached}"
            )
            descriptions.append((scope, cached))
            continue
        try:
            description = await _describe_qzone_image(
                owner, image_url, target_umo=target_umo
            )
        except Exception as exc:
            logger.debug(f"[日常分享] {label}识别跳过: {exc}")
            continue
        if not description:
            continue
        for key in cache_keys:
            cache[key] = description
        cache_changed = True
        descriptions.append((scope, description))
        logger.debug(f"[日常分享] {label}识别成功: 图{index}（{scope}），{description}")

    before_prune_size = len(cache)
    _prune_qzone_image_vision_cache(cache)
    if cache_changed or len(cache) != before_prune_size:
        await _save_qzone_image_vision_cache(owner, state, state_key=state_key)
    if not descriptions:
        logger.debug(f"[日常分享] {label}识别未获得有效摘要，按纯文字评论: {author}")
        return ""
    lines = [
        f"图{index}（{scope}）: {description}"
        for index, (scope, description) in enumerate(descriptions, start=1)
    ]
    return f"【{heading}】\n" + "\n".join(lines)


def _fill_qzone_image_cache_aliases(cache: dict, keys: list[str], value: str) -> bool:
    changed = False
    for key in keys:
        if not cache.get(key):
            cache[key] = value
            changed = True
    return changed


def _enabled_qzone_image_refs(
    owner, image_refs, *, label: str, author: str, log_missing: bool
) -> list | None:
    enabled, limit, _provider_id = _qzone_image_vision_config(owner)
    if not enabled:
        return None
    refs = list(image_refs or [])[:limit]
    if not refs:
        if log_missing:
            logger.debug(f"[日常分享] {label}识别已开启，但未解析到图片: {author}")
        return None
    return refs


async def _qzone_auto_comment_image_context(
    owner,
    post,
    *,
    state: dict | None = None,
    target_umo: str = "",
) -> str:
    _enabled, limit, _provider_id = _qzone_image_vision_config(owner)
    author = getattr(post, "name", "") or getattr(post, "uin", "") or ""
    return await _qzone_image_refs_context(
        owner,
        _qzone_post_image_refs(post, limit=limit),
        state=state,
        target_umo=target_umo,
        label="QQ 空间说说配图",
        heading="配图识别",
        author=author,
    )


async def _qzone_auto_reply_image_context(
    owner,
    *comments,
    state: dict | None = None,
    target_umo: str = "",
    thread: bool = False,
) -> str:
    _enabled, limit, _provider_id = _qzone_image_vision_config(owner)
    if thread and len(comments) >= 2:
        refs = _qzone_comment_image_refs(
            (comments[-1], "新的二级回复配图"),
            (comments[0], "一级评论配图"),
            limit=limit,
        )
        author = (
            getattr(comments[-1], "nickname", "")
            or getattr(comments[-1], "uin", "")
            or ""
        )
    else:
        comment = comments[0] if comments else None
        refs = (
            _qzone_comment_image_refs((comment, "评论配图"), limit=limit)
            if comment is not None
            else []
        )
        author = getattr(comment, "nickname", "") or getattr(comment, "uin", "") or ""
    return await _qzone_image_refs_context(
        owner,
        refs,
        state=state,
        target_umo=target_umo,
        state_key=QZONE_AUTO_REPLY_STATE_KEY,
        label="QQ 空间评论配图",
        heading="评论配图识别",
        author=author,
        log_missing=False,
    )

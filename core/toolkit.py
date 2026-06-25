import asyncio
import inspect
import os
from typing import Optional

from astrbot.api import logger


_MEDIA_LABELS = {"image": "配图", "video": "视频", "audio": "语音"}
_MEDIA_RESULT_ATTRS = {"image": "path", "video": "url", "audio": "path"}


def _find_star_plugin(context, keyword: str):
    needle = str(keyword or "").strip()
    if not needle:
        return None
    try:
        stars = context.get_all_stars()
    except Exception as exc:
        log_exception(f"[每日分享] 查找插件失败: {needle}", exc, level="debug", with_traceback=False)
        return None
    for star in stars or []:
        values = (
            getattr(star, "root_dir_name", ""),
            getattr(star, "module_path", ""),
            getattr(star, "name", ""),
            getattr(star, "display_name", ""),
        )
        if any(needle in str(value or "") for value in values):
            return getattr(star, "star_cls", None)
    return None


def _daily_life_runtime(context):
    plugin = _find_star_plugin(context, "astrbot_plugin_daily_life") or _find_star_plugin(context, "daily_life")
    runtime = getattr(plugin, "runtime", None)
    return runtime if runtime and getattr(runtime, "media", None) else None


def _format_exception(exc: Exception) -> str:
    detail = str(exc).strip()
    exc_name = type(exc).__name__
    return f"{exc_name}: {detail}" if detail else exc_name


def format_exception(exc: Exception) -> str:
    return _format_exception(exc)


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def log_exception(
    message: str,
    exc: Exception,
    *,
    level: str = "error",
    with_traceback: Optional[bool] = None,
) -> None:
    log_method = getattr(logger, str(level or "").lower(), logger.error)
    kwargs = {}
    if with_traceback is None:
        with_traceback = str(level or "").lower() == "error"
    if with_traceback:
        kwargs["exc_info"] = (type(exc), exc, exc.__traceback__)
    log_method(f"{message}: {_format_exception(exc)}", **kwargs)


def _media_label(media_kind: str) -> str:
    return _MEDIA_LABELS.get(str(media_kind or ""), "媒体")


def _media_result_ref(media_kind: str, generated) -> str:
    attr = _MEDIA_RESULT_ATTRS.get(str(media_kind or ""))
    if not attr:
        return ""
    value = getattr(generated, attr, "")
    if not value and isinstance(generated, dict):
        value = generated.get(attr)
    return str(value or "").strip()


def _log_daily_life_media_unavailable(media_kind: str, reason: str, *, level: str = "warning") -> None:
    log_method = getattr(logger, str(level or "").lower(), logger.warning)
    log_method(f"[每日分享] daily_life 默认{_media_label(media_kind)}工具不可用: {reason}")


async def call_default_daily_life_media_tool(
    context,
    *,
    media_kind: str,
    prompt: str,
    image_ref: str = "",
    text: str = "",
    emotion: str = "",
    emotion_category: str = "",
) -> Optional[str]:
    """直接调用 daily_life 媒体服务，只生成媒体，不在生成阶段发送。"""
    runtime = _daily_life_runtime(context)
    if not runtime:
        _log_daily_life_media_unavailable(media_kind, "未找到 astrbot_plugin_daily_life 或媒体运行时")
        return None
    media = getattr(runtime, "media", None)

    try:
        if media_kind == "image":
            image_service = getattr(media, "image", None)
            generate_image = getattr(image_service, "generate_image", None)
            if not callable(generate_image):
                _log_daily_life_media_unavailable(media_kind, "缺少 image.generate_image 方法")
                return None
            generated = await _maybe_await(generate_image(prompt))
            path = _media_result_ref(media_kind, generated)
            if path:
                return path
            _log_daily_life_media_unavailable(media_kind, "generate_image 未返回有效 path")
            return None

        if media_kind == "video":
            video_service = getattr(media, "video", None)
            generate_video = getattr(video_service, "generate_video", None)
            if not callable(generate_video):
                _log_daily_life_media_unavailable(media_kind, "缺少 video.generate_video 方法")
                return None
            image_bytes = None
            ref = str(image_ref or "").strip()
            if ref and os.path.exists(ref):
                image_bytes = await asyncio.to_thread(_read_file_bytes, ref)
            elif ref:
                logger.debug(f"[每日分享] daily_life 默认视频工具未读取到参考图: {ref}")
            generated = await _maybe_await(generate_video(prompt, image_bytes=image_bytes))
            url = _media_result_ref(media_kind, generated)
            if url:
                return url
            _log_daily_life_media_unavailable(media_kind, "generate_video 未返回有效 url")
            return None

        if media_kind == "audio":
            voice_service = getattr(media, "voice", None)
            synthesize = getattr(voice_service, "synthesize", None)
            if not callable(synthesize):
                _log_daily_life_media_unavailable(media_kind, "缺少 voice.synthesize 方法")
                return None
            generated = await _maybe_await(synthesize(
                str(text or prompt or "").strip(),
                emotion=emotion,
                emotion_category=emotion_category,
            ))
            path = _media_result_ref(media_kind, generated)
            if path:
                return path
            _log_daily_life_media_unavailable(media_kind, "synthesize 未返回有效 path")
            return None

        _log_daily_life_media_unavailable(media_kind, f"不支持的媒体类型 {media_kind!r}")
    except Exception as exc:
        log_exception(
            f"[每日分享] daily_life 默认{_media_label(media_kind)}工具调用失败",
            exc,
            with_traceback=False,
        )
        return None

    return None


def _read_file_bytes(path: str) -> bytes:
    with open(path, "rb") as file:
        return file.read()

from astrbot.api import logger

from .integrations import DailyLifeBridge

_MEDIA_LABELS = {"image": "配图", "video": "视频", "audio": "语音"}


def _format_exception(exc: Exception) -> str:
    detail = str(exc).strip()
    exc_name = type(exc).__name__
    return f"{exc_name}: {detail}" if detail else exc_name


def format_exception(exc: Exception) -> str:
    return _format_exception(exc)


def log_exception(
    message: str,
    exc: Exception,
    *,
    level: str = "error",
    with_traceback: bool | None = None,
) -> None:
    log_method = {
        "debug": logger.debug,
        "info": logger.info,
        "warning": logger.warning,
        "error": logger.error,
    }.get(str(level or "").lower(), logger.error)
    kwargs = {}
    if with_traceback is None:
        with_traceback = str(level or "").lower() == "error"
    if with_traceback:
        kwargs["exc_info"] = (type(exc), exc, exc.__traceback__)
    log_method(f"{message}: {_format_exception(exc)}", **kwargs)


def _media_label(media_kind: str) -> str:
    return _MEDIA_LABELS.get(str(media_kind or ""), "媒体")


def _log_daily_life_media_unavailable(
    media_kind: str, reason: str, *, level: str = "warning"
) -> None:
    log_method = {
        "debug": logger.debug,
        "info": logger.info,
        "warning": logger.warning,
        "error": logger.error,
    }.get(str(level or "").lower(), logger.warning)
    log_method(f"[日常分享] 生活插件默认{_media_label(media_kind)}工具不可用: {reason}")


async def call_default_daily_life_media_tool(
    context,
    *,
    media_kind: str,
    prompt: str,
    image_ref: str = "",
    text: str = "",
    emotion: str = "",
    emotion_category: str = "",
    event=None,
    contains_character: bool = False,
    bridge: DailyLifeBridge | None = None,
) -> str | None:
    """直接调用生活插件媒体服务，只生成媒体，不在生成阶段发送。"""
    bridge = bridge or DailyLifeBridge(context)
    if media_kind == "image":
        return (
            await bridge.generate_image(
                event,
                prompt,
                contains_character=contains_character,
            )
            or None
        )
    if media_kind == "video":
        return (
            await bridge.generate_video(
                event,
                prompt,
                reference_image=image_ref,
            )
            or None
        )
    if media_kind == "audio":
        return (
            await bridge.generate_voice(
                str(text or prompt or "").strip(),
                emotion=emotion,
                emotion_category=emotion_category,
            )
            or None
        )
    _log_daily_life_media_unavailable(
        media_kind, f"不支持的媒体类型：{_media_label(media_kind)}"
    )
    return None

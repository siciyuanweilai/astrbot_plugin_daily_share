"""读取 AI 配置与已加载聊天模型，不把会话偏好当成系统配置。"""

from astrbot.api import logger


def chat_model_defaults(context, umo: str | None = None) -> list[tuple[str, str]]:
    config = {}
    try:
        config = context.get_config(umo) if umo else context.get_config()
    except Exception as exc:
        logger.debug(f"[日常分享] 读取 AI 对话模型配置失败: {type(exc).__name__}")
    configured = ""
    if isinstance(config, dict):
        runner = config.get("agent_runner") or {}
        if runner.get("runner_type") == "local":
            configured = str(
                ((runner.get("config") or {}).get("model") or {}).get("provider_id")
                or ""
            ).strip()
        elif not runner:
            configured = str(
                (config.get("provider_settings") or {}).get("default_provider_id") or ""
            ).strip()
    first = ""
    try:
        # 框架已排除禁用、加载失败、语音及嵌入模型，保持实际加载顺序。
        providers = context.get_all_providers() or []
        if providers:
            first = str(providers[0].meta().id or "").strip()
    except Exception as exc:
        logger.debug(f"[日常分享] 读取已加载对话模型失败: {type(exc).__name__}")
    return list(
        dict.fromkeys(
            (provider, source)
            for provider, source in ((configured, "ai_config"), (first, "first_chat"))
            if provider
        )
    )

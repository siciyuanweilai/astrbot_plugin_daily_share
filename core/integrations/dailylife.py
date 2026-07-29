from __future__ import annotations

from typing import Any

from astrbot.api import logger


DAILY_LIFE_PLUGIN_ID = "astrbot_plugin_daily_life"


class DailyLifeBridge:
    """每日分享与生活插件之间唯一的公开调用边界。"""

    def __init__(self, context: Any):
        self.context = context
        self._search_notices: set[str] = set()

    def _plugin(self):
        try:
            stars = self.context.get_all_stars()
        except Exception as exc:
            logger.debug(f"[日常分享] 读取生活插件状态失败: {exc}")
            return None

        for metadata in stars or []:
            if (
                str(metadata.root_dir_name or "").strip() != DAILY_LIFE_PLUGIN_ID
                and str(metadata.name or "").strip() != DAILY_LIFE_PLUGIN_ID
            ):
                continue
            if not metadata.activated or metadata.star_cls is None:
                return None
            return metadata.star_cls
        return None

    async def get_life_context(self, target_umo: str) -> dict:
        plugin = self._plugin()
        method = getattr(plugin, "get_life_context", None) if plugin else None
        if not callable(method):
            return {}
        try:
            result = await method(str(target_umo or "").strip())
            return result if isinstance(result, dict) else {}
        except Exception as exc:
            logger.warning(f"[上下文] 读取生活插件目标上下文失败: {exc}")
            return {}

    def search_available(self) -> bool:
        plugin = self._plugin()
        return (
            callable(getattr(plugin, "search_share_evidence", None))
            if plugin
            else False
        )

    def _log_search_notice(
        self, key: str, message: str, *, warning: bool = False
    ) -> None:
        if key in self._search_notices:
            return
        self._search_notices.add(key)
        log = logger.warning if warning else logger.info
        log(message)

    async def search_evidence(
        self,
        query: str,
        *,
        category: str,
        target_umo: str = "",
    ) -> dict:
        """通过生活插件公开契约获取联网检索证据。"""
        plugin = self._plugin()
        method = getattr(plugin, "search_share_evidence", None) if plugin else None
        if not callable(method):
            self._log_search_notice(
                "unavailable",
                "[内容服务] 生活插件联网检索不可用，本次分享跳过联网补充资料。",
            )
            return {
                "status": "unavailable",
                "content": "",
                "error": "生活插件联网检索不可用",
            }
        try:
            result = await method(
                str(query or "").strip(),
                category=str(category or "").strip(),
                target_umo=str(target_umo or "").strip(),
            )
        except Exception as exc:
            detail = str(exc).strip()
            error_text = type(exc).__name__ + (f": {detail}" if detail else "")
            logger.warning(
                f"[内容服务] 生活插件联网检索失败，已跳过补充资料: {error_text}"
            )
            return {"status": "error", "content": "", "error": error_text}

        if not isinstance(result, dict):
            self._log_search_notice(
                "invalid-result",
                "[内容服务] 生活插件联网检索返回格式无效，已跳过补充资料。",
                warning=True,
            )
            return {
                "status": "error",
                "content": "",
                "error": "生活插件联网检索返回格式无效",
            }

        payload = dict(result)
        status = str(payload.get("status") or "error").strip().lower()
        content = str(payload.get("content") or "").strip()
        payload["status"] = status
        payload["content"] = content
        if status == "disabled":
            self._log_search_notice(
                "disabled",
                "[内容服务] 生活插件未启用联网检索，本次分享跳过联网补充资料。",
            )
        elif status != "ok":
            reason = str(payload.get("error") or "未返回可用结果").strip()
            logger.warning(
                f"[内容服务] 生活插件联网检索未完成，已跳过补充资料: {reason}"
            )
        elif not content:
            self._log_search_notice(
                "empty-result",
                "[内容服务] 生活插件联网检索未返回有效内容，已跳过补充资料。",
                warning=True,
            )
        return payload

    async def generate_image(
        self,
        event: Any,
        prompt: str,
        *,
        contains_character: bool = False,
    ) -> str:
        return await self._call_media(
            "generate_share_image",
            "配图",
            event,
            prompt,
            contains_character=contains_character,
        )

    async def generate_video(
        self,
        event: Any,
        prompt: str,
        *,
        reference_image: str = "",
    ) -> str:
        return await self._call_media(
            "generate_share_video",
            "视频",
            event,
            prompt,
            reference_image=str(reference_image or "").strip(),
        )

    async def generate_voice(
        self,
        text: str,
        *,
        emotion: str = "",
        emotion_category: str = "",
    ) -> str:
        return await self._call_media(
            "generate_share_voice",
            "语音",
            text,
            emotion=emotion,
            emotion_category=emotion_category,
        )

    async def _call_media(self, method_name: str, label: str, *args, **kwargs) -> str:
        plugin = self._plugin()
        method = getattr(plugin, method_name, None) if plugin else None
        if not callable(method):
            logger.warning(f"[日常分享] 生活插件默认{label}工具不可用")
            return ""
        try:
            result = await method(*args, **kwargs)
            value = str(result or "").strip()
            if not value:
                logger.warning(f"[日常分享] 生活插件默认{label}工具未返回有效结果")
            return value
        except Exception as exc:
            detail = str(exc).strip()
            error_text = type(exc).__name__ + (f": {detail}" if detail else "")
            logger.warning(f"[日常分享] 生活插件默认{label}工具调用失败: {error_text}")
            return ""

    async def record_external_activity(
        self,
        target_umo: str,
        content: str,
        *,
        image_description: str = "",
        image_sent: bool = False,
        media_kind: str = "",
        reason: str,
        sync_memory: bool,
    ) -> bool:
        plugin = self._plugin()
        method = getattr(plugin, "record_external_activity", None) if plugin else None
        if not callable(method):
            return False
        try:
            return bool(
                await method(
                    str(target_umo or "").strip(),
                    str(content or "").strip(),
                    image_description=str(image_description or "").strip(),
                    image_sent=bool(image_sent),
                    media_kind=str(media_kind or "").strip(),
                    reason=str(reason or "").strip(),
                    sync_memory=bool(sync_memory),
                )
            )
        except Exception as exc:
            logger.warning(f"[上下文] 回传生活插件主动行为失败: {exc}")
            return False


__all__ = ["DAILY_LIFE_PLUGIN_ID", "DailyLifeBridge"]

import asyncio
from collections.abc import Callable
from typing import Optional

from astrbot.api import logger

from ..toolkit import log_exception


class LlmService:
    """负责模型选择、调用、超时和重试。"""

    def __init__(
        self,
        context,
        basic_conf: dict,
        is_terminated: Callable[[], bool],
    ) -> None:
        self.context = context
        self.basic_conf = basic_conf
        self._is_terminated = is_terminated

    def _llm_system_default_provider(self) -> str:
        try:
            config = self.context.get_config()
            provider_id = config.get("provider_settings", {}).get(
                "default_provider_id", ""
            )
            if provider_id:
                return str(provider_id)
            for provider in config.get("provider", []):
                enabled = provider.get("enable", False)
                provider_type = provider.get("provider_type", "chat")
                if enabled and "chat" in provider_type:
                    return str(provider.get("id") or "")
        except Exception as exc:
            log_exception(
                "[日常分享] 读取默认模型服务提供商失败",
                exc,
                level="debug",
                with_traceback=False,
            )
        return ""

    async def _llm_session_provider(self, umo: str | None) -> str:
        if not umo:
            return ""
        try:
            return str(await self.context.get_current_chat_provider_id(umo) or "")
        except Exception as exc:
            log_exception(
                "[日常分享] 读取会话模型服务提供商失败",
                exc,
                level="debug",
                with_traceback=False,
            )
            return ""

    async def _llm_primary_provider(self, umo: str | None) -> tuple[str, str]:
        configured = str(self.basic_conf.get("llm_provider_id", "") or "").strip()
        session = "" if configured else await self._llm_session_provider(umo)
        provider_id = configured or session or self._llm_system_default_provider()
        return provider_id, configured

    def _llm_config_timeout(self, timeout: int | None) -> int:
        try:
            configured = int(self.basic_conf.get("llm_timeout", 60))
        except (TypeError, ValueError):
            configured = 60
        requested = int(timeout or configured)
        return max(1, min(requested, configured))

    def _llm_switch_to_default(self, current_provider_id: str, *, reason: str) -> str:
        default_provider_id = self._llm_system_default_provider()
        if not default_provider_id or default_provider_id == current_provider_id:
            return current_provider_id
        logger.info(
            f"[日常分享] {reason}，改用默认模型服务提供商 ({default_provider_id})"
        )
        return default_provider_id

    async def call(
        self,
        prompt: str,
        system_prompt: str | None = None,
        timeout: int = 60,
        max_retries: int = 2,
        tools: list | None = None,
        umo: str | None = None,
    ) -> Optional[str]:
        """调用模型，并对超时和可恢复错误进行有限重试。"""
        if self._is_terminated():
            return None

        primary_provider_id, _ = await self._llm_primary_provider(umo)
        if not primary_provider_id:
            logger.error("[日常分享] 没有可用的模型服务提供商，无法生成内容")
            return None
        if tools:
            logger.debug("[日常分享] 当前文本生成接口不接受工具列表，已忽略该参数")

        current_provider_id = primary_provider_id
        actual_timeout = self._llm_config_timeout(timeout)
        for attempt in range(max_retries + 1):
            if self._is_terminated():
                return None
            result, current_provider_id, should_stop = await self._llm_attempt(
                prompt=prompt,
                system_prompt=system_prompt,
                timeout=actual_timeout,
                attempt=attempt,
                max_retries=max_retries,
                primary_provider_id=primary_provider_id,
                current_provider_id=current_provider_id,
            )
            if result or should_stop:
                return result
            if attempt < max_retries:
                await asyncio.sleep(2)

        logger.error(f"[日常分享] 模型调用失败（已重试 {max_retries} 次）")
        return None

    async def _llm_attempt(
        self,
        *,
        prompt: str,
        system_prompt: str | None,
        timeout: int,
        attempt: int,
        max_retries: int,
        primary_provider_id: str,
        current_provider_id: str,
    ) -> tuple[str | None, str, bool]:
        if self._llm_should_fallback_on_last_attempt(
            attempt,
            max_retries=max_retries,
            primary_provider_id=primary_provider_id,
            current_provider_id=current_provider_id,
        ):
            current_provider_id = self._llm_switch_to_default(
                current_provider_id,
                reason="指定模型服务提供商连续调用失败",
            )
        try:
            result = await self._llm_generate_once(
                prompt=prompt,
                system_prompt=system_prompt,
                provider_id=current_provider_id,
                timeout=timeout,
            )
            return result or None, current_provider_id, False
        except asyncio.TimeoutError:
            logger.warning(
                f"[日常分享] 模型请求超时（{timeout} 秒，"
                f"尝试 {attempt + 1}/{max_retries + 1}）"
            )
            return None, current_provider_id, False
        except Exception as exc:
            action, next_provider_id = self._llm_exception_action(
                exc,
                prompt=prompt,
                attempt=attempt,
                max_retries=max_retries,
                primary_provider_id=primary_provider_id,
                current_provider_id=current_provider_id,
            )
            return None, next_provider_id, action == "stop"

    @staticmethod
    def _llm_should_fallback_on_last_attempt(
        attempt: int,
        *,
        max_retries: int,
        primary_provider_id: str,
        current_provider_id: str,
    ) -> bool:
        return (
            attempt == max_retries
            and attempt > 0
            and bool(primary_provider_id)
            and current_provider_id == primary_provider_id
        )

    async def _llm_generate_once(
        self,
        *,
        prompt: str,
        system_prompt: str | None,
        provider_id: str,
        timeout: int,
    ) -> str:
        kwargs = {"prompt": prompt, "chat_provider_id": provider_id}
        if system_prompt:
            kwargs["system_prompt"] = system_prompt
        response = await asyncio.wait_for(
            self.context.llm_generate(**kwargs), timeout=timeout
        )
        return response.completion_text.strip() if response else ""

    def _llm_exception_action(
        self,
        exc: Exception,
        *,
        prompt: str,
        attempt: int,
        max_retries: int,
        primary_provider_id: str,
        current_provider_id: str,
    ) -> tuple[str, str]:
        message = str(exc)
        if "PROHIBITED_CONTENT" in message or "blocked" in message:
            logger.error(f"[日常分享] 内容被模型安全策略拦截: {prompt[:50]}...")
            return "stop", current_provider_id
        if "401" in message:
            logger.error("[日常分享] 模型调用鉴权失败，请检查密钥配置")
            if attempt >= max_retries or current_provider_id != primary_provider_id:
                return "stop", current_provider_id
            next_provider_id = self._llm_switch_to_default(
                current_provider_id, reason="模型鉴权失败"
            )
            action = "retry" if next_provider_id != current_provider_id else "stop"
            return action, next_provider_id

        log_exception(
            f"[日常分享] 模型调用异常（第 {attempt + 1} 次尝试）",
            exc,
            with_traceback=False,
        )
        action = "retry" if attempt < max_retries else "stop"
        return action, current_provider_id

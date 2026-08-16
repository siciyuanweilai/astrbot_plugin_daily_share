import asyncio
from collections.abc import Callable
from time import monotonic

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
    ) -> str | None:
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
        deadline = monotonic() + actual_timeout
        for attempt in range(max_retries + 1):
            if self._is_terminated():
                return None
            remaining_timeout = deadline - monotonic()
            if remaining_timeout <= 0:
                logger.error(
                    f"[日常分享] 模型调用超过总时限（{actual_timeout} 秒，包含重试）"
                )
                return None
            attempted_provider_id = current_provider_id
            result, current_provider_id, should_stop = await self._llm_attempt(
                prompt=prompt,
                system_prompt=system_prompt,
                timeout=remaining_timeout,
                attempt=attempt,
                max_retries=max_retries,
                primary_provider_id=primary_provider_id,
                current_provider_id=current_provider_id,
            )
            if result or should_stop:
                return result
            if attempt < max_retries and current_provider_id == attempted_provider_id:
                remaining_timeout = deadline - monotonic()
                if remaining_timeout <= 0:
                    logger.error(
                        f"[日常分享] 模型调用超过总时限（{actual_timeout} 秒，包含重试）"
                    )
                    return None
                await asyncio.sleep(min(2.0, remaining_timeout))

        logger.error(f"[日常分享] 模型调用失败（已重试 {max_retries} 次）")
        return None

    async def _llm_attempt(
        self,
        *,
        prompt: str,
        system_prompt: str | None,
        timeout: float,
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
                f"[日常分享] 模型请求超时（剩余时限 {timeout:.1f} 秒，"
                f"尝试 {attempt + 1}/{max_retries + 1}）"
            )
            return None, current_provider_id, False
        except Exception as exc:
            action, next_provider_id = self._llm_exception_action(
                exc,
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
        timeout: float,
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
        attempt: int,
        max_retries: int,
        primary_provider_id: str,
        current_provider_id: str,
    ) -> tuple[str, str]:
        message = str(exc)
        if "PROHIBITED_CONTENT" in message or "blocked" in message:
            logger.error("[日常分享] 内容被模型安全策略拦截")
            return "stop", current_provider_id

        permanent_reason = self._llm_permanent_error_reason(exc)
        if permanent_reason:
            log_exception(
                f"[日常分享] {permanent_reason}，当前模型服务提供商不再重试",
                exc,
                with_traceback=False,
            )
            if attempt >= max_retries or current_provider_id != primary_provider_id:
                return "stop", current_provider_id
            next_provider_id = self._llm_switch_to_default(
                current_provider_id, reason=permanent_reason
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

    @staticmethod
    def _llm_permanent_error_reason(exc: Exception) -> str:
        """识别重试无法恢复的鉴权、账户及模型配置错误。"""
        message = str(exc)
        message_lower = message.lower()
        status_code = getattr(exc, "status_code", None)
        if status_code == 401 or "401" in message:
            return "模型调用鉴权失败，请检查密钥配置"

        body = getattr(exc, "body", None)
        if not isinstance(body, dict):
            body = {}
        error_body = body.get("error")
        if isinstance(error_body, dict):
            body = {**body, **error_body}
        error_code = (
            str(body.get("code") or getattr(exc, "code", "") or "").strip().upper()
        )

        code_reasons = {
            "GROUP_DELETED": "模型服务分组已删除",
            "INVALID_API_KEY": "模型服务密钥无效",
            "MODEL_NOT_FOUND": "指定模型不存在",
            "INVALID_MODEL": "指定模型无效",
            "INSUFFICIENT_QUOTA": "模型服务额度不足",
            "INSUFFICIENT_BALANCE": "模型服务余额不足",
            "ACCOUNT_DEACTIVATED": "模型服务账户已停用",
            "ACCOUNT_DISABLED": "模型服务账户已停用",
        }
        if error_code in code_reasons:
            return code_reasons[error_code]

        message_reasons = (
            (("group_deleted", "分组已删除"), "模型服务分组已删除"),
            (
                ("invalid api key", "incorrect api key", "密钥无效"),
                "模型服务密钥无效",
            ),
            (
                ("model_not_found", "invalid model", "模型不存在", "无效模型"),
                "指定模型无效或不存在",
            ),
            (
                ("insufficient_quota", "insufficient balance", "余额不足", "额度不足"),
                "模型服务余额或额度不足",
            ),
            (
                ("account_deactivated", "account disabled", "账户已停用"),
                "模型服务账户已停用",
            ),
        )
        for markers, reason in message_reasons:
            if any(marker in message_lower or marker in message for marker in markers):
                return reason
        return ""

import asyncio
import re
from collections.abc import Callable
from time import monotonic

from astrbot.api import logger

from ..toolkit import log_exception
from ..integrations.mediajob import current_share_job
from .providers import chat_model_defaults


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
        self.token_usage = {
            "reported_calls": 0,
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
        }
        self.token_usage_by_provider: dict[str, dict[str, int]] = {}
        self.token_usage_by_purpose: dict[str, dict[str, dict[str, int]]] = {}
        self.unreported_usage_calls = 0
        self.unreported_usage_by_purpose: dict[str, dict[str, int]] = {}

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

    def _llm_config_timeout(self, timeout: int | None) -> int:
        try:
            configured = int(self.basic_conf.get("llm_timeout", 60))
        except (TypeError, ValueError):
            configured = 60
        requested = configured if timeout is None else int(timeout)
        return max(1, min(requested, configured))

    async def call(
        self,
        prompt: str,
        system_prompt: str | None = None,
        timeout: int | None = None,
        max_retries: int = 2,
        tools: list | None = None,
        umo: str | None = None,
        purpose: str = "text",
    ) -> str | None:
        """调用模型，并对超时和可恢复错误进行有限重试。"""
        if self._is_terminated():
            return None

        configured = str(self.basic_conf.get("llm_provider_id", "") or "").strip()
        primary = configured or await self._llm_session_provider(umo)
        candidates = [(primary, "primary"), *chat_model_defaults(self.context, umo)]
        providers = {}
        for provider, source in candidates:
            if provider:
                providers.setdefault(provider, source)
        if not providers:
            logger.error("[日常分享] 没有可用的模型服务提供商，无法生成内容")
            return None
        if tools:
            logger.debug("[日常分享] 当前文本生成接口不接受工具列表，已忽略该参数")

        provider_ids = list(providers)
        current_index = 0
        max_retries = max(0, int(max_retries))
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
            current_provider_id = provider_ids[current_index]
            has_fallback = (
                current_index + 1 < len(provider_ids) and attempt < max_retries
            )
            # 给后续模型留出真实调用预算，避免首个请求独占总时限。
            attempt_timeout = (
                remaining_timeout / 2 if has_fallback else remaining_timeout
            )
            result, _, should_stop = await self._llm_attempt(
                prompt=prompt,
                system_prompt=system_prompt,
                timeout=attempt_timeout,
                attempt=attempt,
                max_retries=max_retries,
                primary_provider_id=provider_ids[0],
                current_provider_id=current_provider_id,
                has_fallback=has_fallback,
                purpose=purpose,
            )
            if result or should_stop:
                return result
            if has_fallback:
                current_index += 1
                next_id = provider_ids[current_index]
                logger.info(
                    f"[日常分享] 模型 {current_provider_id} 调用失败，"
                    f"降级到 {providers[next_id]} 模型 ({next_id})"
                )
            elif attempt < max_retries:
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
        has_fallback: bool = False,
        purpose: str = "text",
    ) -> tuple[str | None, str, bool]:
        try:
            result = await self._llm_generate_once(
                prompt=prompt,
                system_prompt=system_prompt,
                provider_id=current_provider_id,
                timeout=timeout,
                purpose=purpose,
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
                has_fallback=has_fallback,
            )
            return None, next_provider_id, action == "stop"

    async def _llm_generate_once(
        self,
        *,
        prompt: str,
        system_prompt: str | None,
        provider_id: str,
        timeout: float,
        purpose: str = "text",
    ) -> str:
        kwargs = {"prompt": prompt, "chat_provider_id": provider_id}
        if system_prompt:
            kwargs["system_prompt"] = system_prompt
        response = await asyncio.wait_for(
            self.context.llm_generate(**kwargs), timeout=timeout
        )
        self.record_token_usage(response, provider_id, purpose=purpose)
        return response.completion_text.strip() if response else ""

    def _record_token_usage(self, response, provider_id: str) -> None:
        self.record_token_usage(response, provider_id)

    def record_token_usage(
        self, response, provider_id: str, *, purpose: str = "text"
    ) -> None:
        """只统计框架归一化的服务端用量，识图调用也使用同一口径。"""
        usage = getattr(response, "usage", None)
        if usage is None:
            self._record_unreported_usage(provider_id, purpose)
            return
        try:

            def value(name: str) -> int:
                raw = (
                    usage.get(name, 0)
                    if isinstance(usage, dict)
                    else getattr(usage, name, 0)
                )
                return max(0, int(raw or 0))

            cached = value("input_cached")
            total_input = value("input_other") + cached
            output = value("output")
        except (TypeError, ValueError):
            self._record_unreported_usage(provider_id, purpose)
            return
        if not (total_input or output):
            # 部分提供商返回默认的全零 TokenUsage，不能视为已报告未命中。
            self._record_unreported_usage(provider_id, purpose)
            return
        self.token_usage["reported_calls"] += 1
        self.token_usage["input_tokens"] += total_input
        self.token_usage["cached_input_tokens"] += cached
        self.token_usage["output_tokens"] += output
        provider_usage = self.token_usage_by_provider.setdefault(
            provider_id,
            {
                "reported_calls": 0,
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "cached_calls": 0,
            },
        )
        provider_usage["reported_calls"] += 1
        provider_usage["input_tokens"] += total_input
        provider_usage["cached_input_tokens"] += cached
        provider_usage["output_tokens"] += output
        provider_usage["cached_calls"] += int(cached > 0)
        scene_usage = self.token_usage_by_purpose.setdefault(purpose, {}).setdefault(
            provider_id, dict.fromkeys(provider_usage, 0)
        )
        for key, value_ in (
            ("reported_calls", 1),
            ("input_tokens", total_input),
            ("cached_input_tokens", cached),
            ("output_tokens", output),
            ("cached_calls", int(cached > 0)),
        ):
            scene_usage[key] += value_
        job = current_share_job.get()
        job_id = str(job.get("id") or "") if job else ""
        cache_ratio = (
            f"{cached / total_input:.1%}" if total_input else "未报告输入 token"
        )
        cumulative_input = provider_usage["input_tokens"]
        cumulative_ratio = (
            f"{provider_usage['cached_input_tokens'] / cumulative_input:.1%}"
            if cumulative_input
            else "未报告输入 token"
        )
        logger.debug(
            f"[日常分享] 模型用量：服务提供商={provider_id}，"
            f"输入 token={total_input}，缓存输入 token（cached_input）={cached}，"
            f"输出 token={output}，来源={purpose}，缓存 token 占比={cache_ratio}，"
            f"该服务累计缓存 token 占比={cumulative_ratio}，"
            f"有缓存调用={provider_usage['cached_calls']}/{provider_usage['reported_calls']}，"
            f"任务={job_id or '独立调用'}"
        )

    def _record_unreported_usage(self, provider_id: str, purpose: str) -> None:
        self.unreported_usage_calls += 1
        providers = self.unreported_usage_by_purpose.setdefault(purpose, {})
        providers[provider_id] = providers.get(provider_id, 0) + 1

    def usage_snapshot(self) -> dict:
        """只返回计数，不暴露提示词、凭据或生成内容。"""
        from copy import deepcopy

        snapshot = deepcopy(
            {
                "total": self.token_usage,
                "providers": self.token_usage_by_provider,
                "purposes": self.token_usage_by_purpose,
                "unreported_calls": self.unreported_usage_calls,
                "unreported_by_purpose": self.unreported_usage_by_purpose,
            }
        )
        snapshot["total"]["cached_calls"] = sum(
            usage["cached_calls"] for usage in snapshot["providers"].values()
        )
        for usage in (
            snapshot["total"],
            *snapshot["providers"].values(),
            *(
                u
                for providers in snapshot["purposes"].values()
                for u in providers.values()
            ),
        ):
            usage["cached_input_ratio"] = (
                usage["cached_input_tokens"] / usage["input_tokens"]
                if usage["input_tokens"]
                else None
            )
            usage["cached_call_ratio"] = (
                usage["cached_calls"] / usage["reported_calls"]
                if usage["reported_calls"]
                else None
            )
        return snapshot

    def _llm_exception_action(
        self,
        exc: Exception,
        *,
        attempt: int,
        max_retries: int,
        primary_provider_id: str,
        current_provider_id: str,
        has_fallback: bool = False,
    ) -> tuple[str, str]:
        if self._llm_content_blocked(exc):
            logger.error("[日常分享] 内容被模型安全策略拦截")
            return "stop", current_provider_id

        permanent_reason = self._llm_permanent_error_reason(exc)
        if permanent_reason:
            log_exception(
                f"[日常分享] {permanent_reason}，当前模型服务提供商不再重试",
                exc,
                with_traceback=False,
            )
            return ("retry" if has_fallback else "stop"), current_provider_id

        log_exception(
            f"[日常分享] 模型调用异常（第 {attempt + 1} 次尝试）",
            exc,
            with_traceback=False,
        )
        action = "retry" if attempt < max_retries else "stop"
        return action, current_provider_id

    @staticmethod
    def _llm_content_blocked(exc: Exception) -> bool:
        body = getattr(exc, "body", None)
        body = body if isinstance(body, dict) else {}
        error = body.get("error")
        if isinstance(error, dict):
            body = {**body, **error}
        codes = {
            str(body.get(field) or "").upper()
            for field in ("code", "type", "finish_reason")
        }
        codes.add(str(getattr(exc, "code", "") or "").upper())
        blocked_codes = {
            "PROHIBITED_CONTENT",
            "CONTENT_FILTER",
            "CONTENT_POLICY_VIOLATION",
            "SAFETY",
        }
        if codes & blocked_codes:
            return True
        message = str(exc).lower()
        return bool(
            re.search(
                r"\b(?:prohibited_content|content_filter|content_policy_violation)\b",
                message,
            )
            or re.search(
                r"\bblocked\b.*\b(?:safety|content (?:filter|policy))\b", message
            )
            or re.search(
                r"\b(?:safety|content (?:filter|policy))\b.*\bblocked\b", message
            )
        )

    @staticmethod
    def _llm_permanent_error_reason(exc: Exception) -> str:
        """识别重试无法恢复的鉴权、账户及模型配置错误。"""
        message = str(exc)
        message_lower = message.lower()
        status_code = getattr(exc, "status_code", None)
        if str(status_code) == "401" or re.search(
            r"(?:^401\b|\b(?:http(?:\s+error)?|status(?:_code)?|error\s+code)\s*[:=]?\s*401\b)",
            message_lower,
        ):
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

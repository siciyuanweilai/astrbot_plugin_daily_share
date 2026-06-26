import asyncio
from typing import Optional

from astrbot.api import logger

from ..toolkit import log_exception


class PluginLlmMixin:
    """主插件的大语言模型调用包装能力。"""

    def _llm_system_default_provider(self) -> str:
        try:
            cfg = self.context.get_config()
            if cfg:
                pid = cfg.get("provider_settings", {}).get("default_provider_id", "")
                if pid:
                    return str(pid)
                for provider in cfg.get("provider", []):
                    if provider.get("enable", False) and "chat" in provider.get("provider_type", "chat"):
                        return str(provider.get("id") or "")
        except Exception as e:
            log_exception("[每日分享] 读取默认大语言模型服务提供商失败", e, level="debug", with_traceback=False)
        return ""

    async def _llm_session_provider(self, umo: str | None) -> str:
        if not umo:
            return ""
        try:
            getter = getattr(self.context, "get_current_chat_provider_id", None)
            if callable(getter):
                return str(await getter(umo) or "")
        except Exception as e:
            log_exception("[每日分享] 读取会话大语言模型服务提供商失败", e, level="debug", with_traceback=False)
        return ""

    async def _llm_primary_provider(self, umo: str | None) -> tuple[str, str]:
        configured = str(self.llm_conf.get("llm_provider_id", "") or "").strip()
        session = "" if configured else await self._llm_session_provider(umo)
        return configured or session or self._llm_system_default_provider(), configured

    def _llm_active_provider(self, primary_provider_id: str, configured_provider_id: str) -> str:
        if not configured_provider_id or not self._temp_fallback_provider:
            return primary_provider_id

        now = asyncio.get_running_loop().time()
        if now < self._temp_fallback_until:
            return str(self._temp_fallback_provider or "")

        logger.info("[每日分享] 大语言模型临时降级已过期，恢复尝试指定模型。")
        self._temp_fallback_provider = None
        self._temp_fallback_until = 0.0
        return primary_provider_id

    def _llm_config_timeout(self, timeout: int | None) -> int:
        try:
            config_timeout = int(self.llm_conf.get("llm_timeout", 60))
        except Exception:
            config_timeout = 60
        return max(int(timeout or 60), config_timeout)

    def _llm_switch_to_default(
        self,
        current_provider_id: str,
        configured_provider_id: str,
        *,
        reason: str,
    ) -> str:
        default_pid = self._llm_system_default_provider()
        if not default_pid or default_pid == current_provider_id:
            return current_provider_id
        logger.info(f"[每日分享] {reason}，降级使用默认的第一个模型({default_pid})...")
        if configured_provider_id:
            self._temp_fallback_provider = default_pid
            self._temp_fallback_until = asyncio.get_running_loop().time() + self._fallback_ttl_seconds
        return default_pid

    async def _call_llm_wrapper(
        self,
        prompt: str,
        system_prompt: str = None,
        timeout: int = 60,
        max_retries: int = 2,
        tools: list = None,
        umo: str = None,
    ) -> Optional[str]:
        """大语言模型调用包装器（支持失败重试与自动降级）"""
        if self._is_terminated:
            return None

        primary_provider_id, configured_provider_id = await self._llm_primary_provider(umo)
        current_provider_id = self._llm_active_provider(primary_provider_id, configured_provider_id)
        actual_timeout = self._llm_config_timeout(timeout)
        if tools:
            logger.debug("[每日分享] 当前 AstrBot 文本生成接口不支持工具名列表，已忽略工具参数。")
        if not current_provider_id:
            logger.error("[每日分享] 未找到可用的大语言模型服务提供商，无法生成内容。")
            return None

        for attempt in range(max_retries + 1):
            if self._is_terminated:
                return None

            is_last_attempt = attempt == max_retries
            if is_last_attempt and attempt > 0 and primary_provider_id and current_provider_id == primary_provider_id:
                current_provider_id = self._llm_switch_to_default(
                    current_provider_id,
                    configured_provider_id,
                    reason="指定大语言模型已达到重试次数",
                )

            try:
                kwargs = {"prompt": prompt}
                if system_prompt is not None and system_prompt != "":
                    kwargs["system_prompt"] = system_prompt
                if current_provider_id:
                    kwargs["chat_provider_id"] = current_provider_id

                resp = await asyncio.wait_for(
                    self.context.llm_generate(**kwargs),
                    timeout=actual_timeout,
                )

                if resp and hasattr(resp, "completion_text"):
                    result = resp.completion_text.strip()
                    if result:
                        return result

            except asyncio.TimeoutError:
                logger.warning(f"[每日分享] 大语言模型请求超时（{actual_timeout} 秒，尝试 {attempt + 1}/{max_retries + 1}）")
                if attempt < max_retries:
                    await asyncio.sleep(2)
                    continue
            except Exception as e:
                err_str = str(e)
                if "PROHIBITED_CONTENT" in err_str or "blocked" in err_str:
                    logger.error(f"[每日分享] 内容被模型安全策略拦截 (敏感词): {prompt[:50]}...")
                    return None

                if "401" in err_str:
                    logger.error("[每日分享] 大语言模型调用失败，请检查密钥配置。")
                    if attempt < max_retries and primary_provider_id and current_provider_id == primary_provider_id:
                        next_provider_id = self._llm_switch_to_default(
                            current_provider_id,
                            configured_provider_id,
                            reason="遇到 401 错误",
                        )
                        if next_provider_id != current_provider_id:
                            current_provider_id = next_provider_id
                            await asyncio.sleep(2)
                            continue
                        return None
                    return None

                log_exception(f"[每日分享] 大语言模型调用异常（第 {attempt + 1} 次尝试）", e, with_traceback=False)
                if attempt < max_retries:
                    await asyncio.sleep(2)
                    continue

        logger.error(f"[每日分享] 大语言模型调用失败（已重试 {max_retries} 次）")
        return None

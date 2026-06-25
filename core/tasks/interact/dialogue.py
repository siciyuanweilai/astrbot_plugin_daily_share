from astrbot.api import logger

from ...prompt import build_qzone_interaction_rules
from .formatting import (
    _clean_auto_comment_text,
    _compact_qzone_auto_life_context,
    _is_skip_auto_comment,
    _qzone_auto_comment_post_summary,
    _qzone_auto_interaction_time_context,
    _qzone_auto_reply_comment_summary,
    _qzone_auto_reply_thread_summary,
)


class QzoneAutoPromptMixin:
    @staticmethod
    def _qzone_auto_comment_post_summary(post) -> str:
        return _qzone_auto_comment_post_summary(post)

    async def _qzone_auto_interaction_system_prompt(self, task_prompt: str) -> str:
        rules = build_qzone_interaction_rules(task_prompt)
        persona_prompt = await self._qzone_auto_interaction_persona_prompt()
        if not persona_prompt:
            return rules
        return f"{persona_prompt}\n\n{rules}"

    async def _qzone_auto_interaction_persona_prompt(self) -> str:
        llm_conf = getattr(self.plugin, "llm_conf", None) or {}
        if isinstance(llm_conf, dict) and not bool(llm_conf.get("use_persona", True)):
            return ""

        content_service = getattr(self.plugin, "content_service", None)
        get_persona_info = getattr(content_service, "_get_persona_info", None)
        if callable(get_persona_info):
            try:
                info = await get_persona_info()
                if isinstance(info, dict):
                    return str(info.get("prompt") or "").strip()
            except Exception as exc:
                logger.debug(f"[每日分享] 读取 QQ 空间互动人设失败: {exc}")
        return ""

    async def _qzone_auto_life_context_prompt(self) -> str:
        ctx_service = getattr(self, "ctx_service", None)
        get_life_context = getattr(ctx_service, "get_life_context", None)
        if not callable(get_life_context):
            return ""
        try:
            value = await get_life_context()
        except Exception as exc:
            logger.debug(f"[每日分享] 读取生活状态参考失败: {exc}")
            return ""
        compact = _compact_qzone_auto_life_context(value)
        if not compact:
            return ""
        return (
            "【当前生活状态参考】\n"
            f"{compact}\n"
            "不要主动透露具体地点、行程、关系、备忘录等隐私细节。"
        )

    async def _qzone_auto_interaction_llm(
        self,
        prompt: str,
        *,
        system_prompt: str,
        max_bytes: int = 0,
    ) -> str:
        call_llm = getattr(self.plugin, "_call_llm_wrapper", None)
        if not callable(call_llm):
            raise RuntimeError("缺少可用的 LLM 调用器")
        result = await call_llm(prompt=prompt, system_prompt=system_prompt)
        text = _clean_auto_comment_text(result, max_bytes=max_bytes)
        if not text:
            raise RuntimeError("LLM 未返回有效内容")
        return text

    async def _generate_qzone_auto_comment(self, post) -> str:
        prompt_parts = [
            "请以真实好友的语气，给这条好友 QQ 空间动态写一条自然、简短、有人味的评论。",
            _qzone_auto_interaction_time_context(),
            self._qzone_auto_comment_post_summary(post),
        ]
        life_context = await self._qzone_auto_life_context_prompt()
        if life_context:
            prompt_parts.append(life_context)
        prompt_parts.append("如果不适合评论，请只输出“跳过”。")
        prompt = "\n\n".join(part for part in prompt_parts if part)
        system_prompt = await self._qzone_auto_interaction_system_prompt(
            "请以真实好友的语气，只输出评论正文或“跳过”。"
        )
        result = await self._qzone_auto_interaction_llm(prompt, system_prompt=system_prompt)
        return "" if _is_skip_auto_comment(result) else result

    async def _generate_qzone_auto_reply(self, post, comment) -> str:
        prompt_parts = [
            "请以真实 QQ 空间主人身份，对这条评论写一条自然、简短的回评。",
            _qzone_auto_interaction_time_context(),
            _qzone_auto_reply_comment_summary(post, comment),
        ]
        life_context = await self._qzone_auto_life_context_prompt()
        if life_context:
            prompt_parts.append(life_context)
        prompt_parts.append("如果不适合回复，请只输出“跳过”。")
        prompt = "\n\n".join(part for part in prompt_parts if part)
        system_prompt = await self._qzone_auto_interaction_system_prompt(
            "请以真实 QQ 空间主人身份，只输出回复正文或“跳过”。"
        )
        result = await self._qzone_auto_interaction_llm(prompt, system_prompt=system_prompt)
        return "" if _is_skip_auto_comment(result) else result

    async def _generate_qzone_auto_reply_thread(self, post, parent_comment, comment) -> str:
        prompt_parts = [
            "请以真实 QQ 空间主人身份，在同一评论楼中结合前文，只对最后列出的“新的二级回复”写一条自然、简短的回评。",
            _qzone_auto_interaction_time_context(),
            _qzone_auto_reply_thread_summary(post, parent_comment, comment),
        ]
        life_context = await self._qzone_auto_life_context_prompt()
        if life_context:
            prompt_parts.append(life_context)
        prompt_parts.append("如果不适合回复，请只输出“跳过”。")
        prompt = "\n\n".join(part for part in prompt_parts if part)
        system_prompt = await self._qzone_auto_interaction_system_prompt(
            "请以真实 QQ 空间主人身份，只输出回复正文或“跳过”。"
        )
        result = await self._qzone_auto_interaction_llm(prompt, system_prompt=system_prompt)
        return "" if _is_skip_auto_comment(result) else result

from typing import TYPE_CHECKING, Any

from astrbot.api import logger

from ...database.keys import QZONE_TARGET_ID
from ...prompt import build_qzone_interaction_rules
from .formatting import (
    _clean_auto_comment_text,
    _compact_qzone_auto_life_context,
    _qzone_auto_comment_post_summary,
    _qzone_auto_interaction_time_context,
    _qzone_auto_reply_comment_summary,
    _qzone_auto_reply_thread_summary,
)
from .vision import _qzone_auto_comment_image_context, _qzone_auto_reply_image_context
from .policy import QzoneAutoPolicyService


QZONE_AUTO_STYLE_PROMPT_LIMIT = 1200


def _qzone_auto_style_prompt(label: str, value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return (
        f"【{label}】\n"
        f"{text[:QZONE_AUTO_STYLE_PROMPT_LIMIT]}\n"
        "请在不违背上方任务、人设、身份、关系边界、上下文事实和 QQ 空间互动规则的前提下参考这段风格补充。"
    )


class QzoneAutoPromptService(QzoneAutoPolicyService):
    if TYPE_CHECKING:
        plugin: Any
        ctx_service: Any

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
        try:
            info = await self.plugin.content_service.get_persona_info()
            if isinstance(info, dict):
                return str(info.get("prompt") or "").strip()
        except Exception as exc:
            logger.debug(f"[日常分享] 读取 QQ 空间互动人设失败: {exc}")
        return ""

    async def _qzone_auto_life_context_prompt(self) -> str:
        try:
            value = await self.ctx_service.get_life_context(QZONE_TARGET_ID)
        except Exception as exc:
            logger.debug(f"[日常分享] 读取生活状态参考失败: {exc}")
            return ""
        compact = _compact_qzone_auto_life_context(value)
        if not compact:
            return ""
        return f"【当前生活状态参考】\n{compact}"

    def _qzone_auto_comment_style_prompt(self) -> str:
        cfg = self._qzone_auto_config()
        return _qzone_auto_style_prompt(
            "自动评论风格补充", getattr(cfg, "comment_prompt", "") if cfg else ""
        )

    def _qzone_auto_reply_style_prompt(self) -> str:
        cfg = self._qzone_auto_config()
        return _qzone_auto_style_prompt(
            "自动回评风格补充", getattr(cfg, "reply_prompt", "") if cfg else ""
        )

    async def _qzone_auto_interaction_llm(
        self,
        prompt: str,
        *,
        system_prompt: str,
        max_bytes: int = 0,
        target_umo: str = "",
    ) -> str:
        result = await self.plugin.call_llm(
            prompt=prompt, system_prompt=system_prompt, umo=target_umo or None
        )
        text = _clean_auto_comment_text(result, max_bytes=max_bytes)
        if not text:
            raise RuntimeError("大语言模型未返回有效内容")
        return text

    async def generate_qzone_auto_comment(
        self,
        post,
        *,
        state: dict | None = None,
        target_umo: str = "",
    ) -> str:
        author = getattr(post, "name", "") or getattr(post, "uin", "") or ""
        logger.debug(f"[日常分享] QQ 空间自动评论生成开始: {author}")
        prompt_parts = [
            (
                "请以真实好友的语气，给这条好友 QQ 空间动态写一条自然、简短、有人味的评论。"
                "优先回应发布者正文和转发语境；配图识别只作为辅助细节。"
                "文字很少或文字明确围绕图片时，可以把图片作为主要回应点。"
            ),
            _qzone_auto_interaction_time_context(),
            self._qzone_auto_comment_post_summary(post),
        ]
        style_prompt = self._qzone_auto_comment_style_prompt()
        if style_prompt:
            prompt_parts.append(style_prompt)
        image_context = await _qzone_auto_comment_image_context(
            self, post, state=state, target_umo=target_umo
        )
        if image_context:
            prompt_parts.append(image_context)
        life_context = await self._qzone_auto_life_context_prompt()
        if life_context:
            prompt_parts.append(life_context)
        prompt = "\n\n".join(part for part in prompt_parts if part)
        system_prompt = await self._qzone_auto_interaction_system_prompt(
            "请以真实好友的语气，只输出一句自然评论；内容优先级为发布者正文、转发语境、配图识别。"
        )
        result = await self._qzone_auto_interaction_llm(
            prompt,
            system_prompt=system_prompt,
            target_umo=target_umo,
        )
        logger.debug(f"[日常分享] QQ 空间自动评论生成完成: {author}")
        return result

    async def _generate_qzone_auto_reply(
        self,
        post,
        comment,
        *,
        state: dict | None = None,
        target_umo: str = "",
    ) -> str:
        prompt_parts = [
            "请以真实 QQ 空间主人身份，对这条评论写一条自然、简短的回评。",
            _qzone_auto_interaction_time_context(),
            _qzone_auto_reply_comment_summary(post, comment),
        ]
        style_prompt = self._qzone_auto_reply_style_prompt()
        if style_prompt:
            prompt_parts.append(style_prompt)
        image_context = await _qzone_auto_reply_image_context(
            self, comment, state=state, target_umo=target_umo
        )
        if image_context:
            prompt_parts.append(image_context)
        life_context = await self._qzone_auto_life_context_prompt()
        if life_context:
            prompt_parts.append(life_context)
        prompt = "\n\n".join(part for part in prompt_parts if part)
        system_prompt = await self._qzone_auto_interaction_system_prompt(
            "请以真实 QQ 空间主人身份，只输出一句自然回评。"
        )
        return await self._qzone_auto_interaction_llm(
            prompt, system_prompt=system_prompt, target_umo=target_umo
        )

    async def _generate_qzone_auto_reply_thread(
        self,
        post,
        parent_comment,
        comment,
        *,
        state: dict | None = None,
        target_umo: str = "",
    ) -> str:
        prompt_parts = [
            "请以真实 QQ 空间主人身份，在同一评论楼中结合前文，只对最后列出的“新的二级回复”写一条自然、简短的回评。",
            _qzone_auto_interaction_time_context(),
            _qzone_auto_reply_thread_summary(post, parent_comment, comment),
        ]
        style_prompt = self._qzone_auto_reply_style_prompt()
        if style_prompt:
            prompt_parts.append(style_prompt)
        image_context = await _qzone_auto_reply_image_context(
            self,
            parent_comment,
            comment,
            state=state,
            target_umo=target_umo,
            thread=True,
        )
        if image_context:
            prompt_parts.append(image_context)
        life_context = await self._qzone_auto_life_context_prompt()
        if life_context:
            prompt_parts.append(life_context)
        prompt = "\n\n".join(part for part in prompt_parts if part)
        system_prompt = await self._qzone_auto_interaction_system_prompt(
            "请以真实 QQ 空间主人身份，只输出一句自然回评。"
        )
        return await self._qzone_auto_interaction_llm(
            prompt, system_prompt=system_prompt, target_umo=target_umo
        )

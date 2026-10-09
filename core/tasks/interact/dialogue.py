import json
import re
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
from .identity import qzone_actor_uin, qzone_relationship_target
from .policy import QzoneAutoPolicyService
from .sight import (
    _qzone_auto_comment_image_context,
    _qzone_auto_reply_image_context,
    _qzone_image_descriptions_context,
    _qzone_image_refs_descriptions,
    _qzone_image_vision_config,
)


def _parse_qzone_photo_comment(
    value: str, allowed_indices: set[int]
) -> tuple[int, str]:
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(value or "").strip()).strip()
    try:
        data = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "相册评论未返回有效的照片编号和正文，停止提交以免落到错误照片"
        ) from exc
    if not isinstance(data, dict):
        raise RuntimeError("相册评论结果不是对象，不能确认照片落点")
    index = data.get("photo_index")
    if type(index) is not int or index not in allowed_indices:
        raise RuntimeError("相册评论照片编号不属于本批已识别照片，停止提交")
    content = data.get("comment")
    if not isinstance(content, str) or not (
        content := _clean_auto_comment_text(content)
    ):
        raise RuntimeError("相册评论未返回有效正文")
    return index, content


class QzoneAutoPromptService(QzoneAutoPolicyService):
    if TYPE_CHECKING:
        plugin: Any
        ctx_service: Any

    @staticmethod
    def _qzone_auto_comment_post_summary(post) -> str:
        return _qzone_auto_comment_post_summary(post)

    async def _qzone_auto_interaction_system_prompt(
        self, task_prompt: str, *, output_rule: str = "", scene: str = "qzone_comment"
    ) -> str:
        rules = build_qzone_interaction_rules(task_prompt, output_rule=output_rule)
        content_service = getattr(self.plugin, "content_service", None)
        style_getter = getattr(content_service, "get_qzone_chat_style_prompt", None)
        if callable(style_getter):
            style_prompt = await style_getter(scene=scene)
            if style_prompt:
                rules += f"\n\n{style_prompt}"
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

    async def _qzone_auto_life_context_prompt(self, actor, *, role: str) -> str:
        target = qzone_relationship_target(self, actor)
        uin = qzone_actor_uin(actor)
        name = " ".join(
            str(
                getattr(actor, "nickname", "") or getattr(actor, "name", "") or ""
            ).split()
        )[:60]
        parts = [
            f"【本次互动对象】\n{role}：{name or '未知昵称'}（QQ：{uin or '未确认'}）"
        ]
        data = {}
        try:
            data = await self.ctx_service.get_qzone_interaction_context(
                target or QZONE_TARGET_ID
            )
        except Exception as exc:
            logger.debug(f"[日常分享] 读取生活状态参考失败: {exc}")
        relation = str(data.get("relationship_context") or "").strip() if target else ""
        if relation:
            parts.append(f"【当前互动对象关系】\n{relation}")
        else:
            parts.append(
                "【当前互动对象关系】\n未确认关系；使用昵称或中性称呼，不凭昵称猜测身份、亲密程度或关系。"
            )
        # 关系段独立保留，不参与生活状态的 900 字截断。
        compact = _compact_qzone_auto_life_context(data.get("life_context"))
        if compact:
            parts.append(f"【当前生活状态参考】\n{compact}")
        return "\n\n".join(parts)

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

    async def _qzone_auto_comment_prompt(self, post, image_context: str) -> str:
        prompt_parts = [
            (
                "请以真实好友的语气，给这条好友 QQ 空间动态写一条自然、简短、有人味的评论。"
                "优先回应发布者正文和转发语境；配图识别只作为辅助细节。"
                "文字很少或文字明确围绕图片时，可以把图片作为主要回应点。"
            ),
            _qzone_auto_interaction_time_context(),
            self._qzone_auto_comment_post_summary(post),
        ]
        if image_context:
            prompt_parts.append(image_context)
        life_context = await self._qzone_auto_life_context_prompt(post, role="动态作者")
        if life_context:
            prompt_parts.append(life_context)
        return "\n\n".join(part for part in prompt_parts if part)

    async def generate_qzone_auto_comment(
        self,
        post,
        *,
        state: dict | None = None,
        target_umo: str = "",
    ) -> str:
        author = getattr(post, "name", "") or getattr(post, "uin", "") or ""
        logger.debug(f"[日常分享] QQ 空间自动评论生成开始: {author}")
        image_context = await _qzone_auto_comment_image_context(
            self, post, state=state, target_umo=target_umo
        )
        prompt = await self._qzone_auto_comment_prompt(post, image_context)
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

    async def generate_qzone_auto_photo_comment(
        self,
        post,
        photo_posts: list,
        *,
        state: dict | None = None,
        target_umo: str = "",
    ) -> tuple[str, str]:
        author = getattr(post, "name", "") or getattr(post, "uin", "") or ""
        logger.debug(f"[日常分享] QQ 空间相册自动评论生成开始: {author}")
        _enabled, limit, _provider_id = _qzone_image_vision_config(self)
        candidates = {}
        for item in photo_posts:
            for image in item.images:
                if image:
                    candidates.setdefault(image, item)
        image_refs = [
            (item, "候选评论照片", image)
            for image, item in list(candidates.items())[:limit]
        ]
        descriptions = await _qzone_image_refs_descriptions(
            self,
            image_refs,
            state=state,
            target_umo=target_umo,
            label="QQ 空间相册配图",
            author=author,
        )
        prompt = await self._qzone_auto_comment_prompt(
            post, _qzone_image_descriptions_context(descriptions)
        )
        if not descriptions:
            # 没有可靠视觉摘要时仅回应正文，不猜测任意照片的画面。
            prompt += "\n\n未获得有效配图识别；仅回应发布者正文，不描述照片细节。"
            system_prompt = await self._qzone_auto_interaction_system_prompt(
                "请以真实好友的语气，只输出一句自然评论。"
            )
            content = await self._qzone_auto_interaction_llm(
                prompt, system_prompt=system_prompt, target_umo=target_umo
            )
            return post.photo_targets[0].key, content

        allowed_indices = {index for index, _scope, _description in descriptions}
        output_rule = (
            '输出要求：只输出 JSON 对象 {"photo_index": 整数, "comment": "一句自然评论"}，'
            "不要解释或添加其他文字。comment 保持原有自然聊天语气，照片编号不得写进正文。"
        )
        prompt += (
            "\n\n【相册评论落点】\n"
            "本批照片只发一条综合评论。默认结合本批全部已识别图片形成整组感受，"
            "不是只评价提交落点这一张，也不必逐张罗列。"
            "接口必须选择一张照片挂载这条整组评论，从以下编号中选择提交落点："
            + "、".join(str(index) for index in sorted(allowed_indices))
            + "。photo_index 必须使用配图识别中的原始图号，不能重新编号；"
            "综合多张场景时使用‘这组照片’、‘这一组’等整组措辞，"
            "不能把多张不同画面都混称为‘这张’。"
            "若文案具体聚焦某张的画面、穿搭或动作，提交落点就选择对应的照片；"
            "其他照片细节仍可作为整组背景，但不能写成落点照片自身的内容。\n"
            + output_rule
        )
        system_prompt = await self._qzone_auto_interaction_system_prompt(
            "请以真实好友的语气综合同批全部已识别图片写一条评论，选定一张照片挂载；"
            "整组评论明确指向这一组，具体聚焦单张时正文与照片编号必须对应。",
            output_rule=output_rule,
        )
        raw = await self.plugin.call_llm(
            prompt=prompt, system_prompt=system_prompt, umo=target_umo or None
        )
        index, content = _parse_qzone_photo_comment(raw, allowed_indices)
        selected = image_refs[index - 1][0]
        photo_key = selected.photo_targets[0].key
        logger.debug(
            f"[日常分享] QQ 空间相册自动评论生成完成: {author}，"
            f"选中图{index}，照片={photo_key}"
        )
        return photo_key, content

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
        image_context = await _qzone_auto_reply_image_context(
            self, comment, state=state, target_umo=target_umo
        )
        if image_context:
            prompt_parts.append(image_context)
        life_context = await self._qzone_auto_life_context_prompt(
            comment, role="被回复的评论人"
        )
        if life_context:
            prompt_parts.append(life_context)
        prompt = "\n\n".join(part for part in prompt_parts if part)
        system_prompt = await self._qzone_auto_interaction_system_prompt(
            "请以真实 QQ 空间主人身份，只输出一句自然回评。", scene="qzone_reply"
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
            "请以你自己的身份，在同一评论楼中结合前文，只对最后列出的“新的二级回复”写一条自然、简短的回评；动态可能属于好友，不要把动态作者的经历当成你自己的。",
            _qzone_auto_interaction_time_context(),
            _qzone_auto_reply_thread_summary(post, parent_comment, comment),
        ]
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
        life_context = await self._qzone_auto_life_context_prompt(
            comment, role="被回复的二级回复人"
        )
        if life_context:
            prompt_parts.append(life_context)
        prompt = "\n\n".join(part for part in prompt_parts if part)
        system_prompt = await self._qzone_auto_interaction_system_prompt(
            "请以你自己在 QQ 空间互动的身份，只输出一句自然回评；不要冒充动态作者或同楼其他人。",
            scene="qzone_reply",
        )
        return await self._qzone_auto_interaction_llm(
            prompt, system_prompt=system_prompt, target_umo=target_umo
        )

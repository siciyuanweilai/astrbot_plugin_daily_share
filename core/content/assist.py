import re
from typing import Any

from astrbot.api import logger

from ..config import TimePeriod
from ..database.keys import QZONE_TARGET_ID
from ..persona import selected_share_persona
from ..prompt import build_private_target_prompt, build_qzone_post_prompt
from .contentbase import ContentComponent


class ContentSupportService(ContentComponent):
    """内容生成支撑能力。"""

    async def _call_llm(self, *args, target_umo: str | None = None, **kwargs):
        if target_umo:
            kwargs["umo"] = target_umo
        return await self.call_llm(*args, **kwargs)

    async def _generate_qzone_post(
        self, ctx: dict, task: str, material: str = ""
    ) -> str | None:
        result = await self._call_llm(
            prompt=build_qzone_post_prompt(ctx, task, material),
            system_prompt=ctx["system_prompt"],
            target_umo=ctx.get("target_id"),
        )
        if not result:
            return None
        bridge = getattr(self.service, "daily_life_bridge", None)
        prepare = getattr(bridge, "prepare_expression", None)
        if callable(prepare):
            expression = await prepare(result, scene="qzone_post")
            result = str(expression.get("text") or result).strip()
        if len(result) > 80:
            logger.info("[内容服务] QQ 空间正文仍过长，跳过本次发布，不机械截断")
            return None
        normalized = "".join(result.split())
        if any(
            normalized == "".join(text.split())
            for text in ctx.get("recent_post_contents", [])
        ):
            logger.info("[内容服务] QQ 空间正文与近期已发布内容重复，跳过本次发布")
            return None
        return result

    async def _review_share_expression(
        self, text: str | None, ctx: dict, *, required_terms=()
    ) -> str | None:
        """只检查当前分享正文；题目、受众及独立格式不能被二次润色覆盖。"""
        if not text:
            return None
        bridge = getattr(self.service, "daily_life_bridge", None)
        prepare = getattr(bridge, "prepare_expression", None)
        if not callable(prepare):
            return text
        scene = "share_group" if ctx.get("is_group") else "share_private"
        protected = list(
            dict.fromkeys(
                [
                    *(
                        str(term)
                        for term in required_terms
                        if term and str(term) in text
                    ),
                    *re.findall(r"【[^\n【】]+】", text),
                ]
            )
        )
        output_format = str(ctx.get("output_format_hint") or "")
        try:
            expression = await prepare(
                text,
                scene=scene,
                requirements={
                    "share_type": ctx.get("share_type", ""),
                    "target_umo": ctx.get("target_id", ""),
                    "output_format": output_format,
                    "required_terms": protected,
                },
            )
            rewritten = expression.get("text") if isinstance(expression, dict) else None
            if not isinstance(rewritten, str) or not rewritten.strip():
                return text
            rewritten = rewritten.strip()
            if any(term not in rewritten for term in protected):
                return text
            if output_format and len(rewritten.splitlines()) != len(text.splitlines()):
                return text
            return rewritten
        except Exception as exc:
            logger.debug(
                f"[内容服务] 分享表达检查不可用，保留原文：{type(exc).__name__}"
            )
            return text

    def parse_category_config(self, data: Any) -> dict[str, list[str]]:
        result = {}
        if isinstance(data, dict):
            for name, tags_data in data.items():
                name = str(name or "").strip()
                tags = self._parse_category_tags(tags_data)
                if name and tags:
                    result[name] = tags
            return result

        if isinstance(data, list):
            for item in data:
                if isinstance(item, str):
                    item = item.replace("，", ":")
                    if ":" in item:
                        name, tags_str = item.split(":", 1)
                        name = name.strip()
                        tags = self._parse_category_tags(tags_str)
                        if name and tags:
                            result[name] = tags
        return result

    def _parse_category_tags(self, tags_data: Any) -> list[str]:
        if isinstance(tags_data, list):
            raw_tags = tags_data
        else:
            raw_tags = str(tags_data or "").replace("，", ",").split(",")
        return [str(tag).strip() for tag in raw_tags if str(tag).strip()]

    def _get_period_label(self, period: TimePeriod) -> str:
        labels = {
            TimePeriod.DAWN: "凌晨",
            TimePeriod.MORNING: "早晨",
            TimePeriod.FORENOON: "上午",
            TimePeriod.NOON: "中午",
            TimePeriod.AFTERNOON: "下午",
            TimePeriod.EVENING: "傍晚",
            TimePeriod.NIGHT: "夜晚",
            TimePeriod.LATE_NIGHT: "深夜",
        }
        return labels.get(period, "现在")

    async def get_persona_info(self, target_umo: str | None = None) -> dict:
        info = {"prompt": "", "bot_name": "", "user_name": ""}
        try:
            personality = await selected_share_persona(self.context, target_umo)
            if personality:
                info["prompt"] = personality.get("prompt", "")
                info["bot_name"] = personality.get("bot_name", "")
                info["user_name"] = personality.get("user_name", "")
            return info
        except Exception as e:
            logger.error(f"[内容服务] 获取人设失败: {e}")
            return info

    def _build_user_prompt(
        self, call_name: str, detect_name: str = "", target_id: str = ""
    ) -> str:
        return build_private_target_prompt(call_name, detect_name, target_id)

    def _build_recent_dynamics_prompt(self, recent_dynamics: str) -> str:
        if not str(recent_dynamics or "").strip():
            return ""
        return (
            f"\n【你最近发过的动态回顾】\n{recent_dynamics}\n"
            "(注：请保持人设连贯，可以偶尔自然呼应之前的心情，但不要重复发过的内容)"
        )

    def _build_structured_history_prompt(self, structured_history: str) -> str:
        structured_history = str(structured_history or "").strip()
        if not structured_history:
            return ""
        return (
            "\n【最近的真实消息流】\n"
            f"{structured_history}\n"
            "（注：优先按这段消息流判断谁在对谁说话、谁在回复谁、是否 @、是否带图。）"
        )

    def _build_output_format_prompt(self, target_id: str = "") -> str:
        target = str(target_id or "").strip()
        if target == QZONE_TARGET_ID:
            return ""
        general_format = str(
            self.basic_conf.get("share_output_format", "") or ""
        ).strip()
        output_format = general_format
        if not output_format:
            return ""

        label = "分享文案输出格式"
        output_format = output_format[:1200]
        return (
            f"\n【{label}】\n"
            f"{output_format}\n"
            "请在不违背上方任务、事实边界和受众关系的前提下遵守这个输出格式。"
        )

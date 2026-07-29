from typing import Any, Dict, List

from astrbot.api import logger

from ..config import TimePeriod
from ..prompt import build_private_target_prompt
from .contentbase import ContentComponent


class ContentSupportService(ContentComponent):
    """内容生成支撑能力。"""

    async def _call_llm(self, *args, target_umo: str | None = None, **kwargs):
        if target_umo:
            kwargs["umo"] = target_umo
        return await self.call_llm(*args, **kwargs)

    def parse_category_config(self, data: Any) -> Dict[str, List[str]]:
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

    def _parse_category_tags(self, tags_data: Any) -> List[str]:
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

    async def get_persona_info(self) -> dict:
        info = {"prompt": "", "bot_name": "", "user_name": ""}
        try:
            personality = await self.context.persona_manager.get_default_persona_v3()
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

    def _build_output_format_prompt(self, is_qzone: bool = False) -> str:
        general_format = str(
            self.basic_conf.get("share_output_format", "") or ""
        ).strip()
        qzone_format = ""
        if is_qzone:
            qzone_format = str(
                self.qzone_conf.get("qzone_share_output_format", "") or ""
            ).strip()

        output_format = qzone_format or general_format
        if not output_format:
            return ""

        label = "QQ 空间说说输出格式" if qzone_format else "分享文案输出格式"
        output_format = output_format[:1200]
        return (
            f"\n【{label}】\n"
            f"{output_format}\n"
            "请在不违背上方任务、事实边界和受众关系的前提下遵守这个输出格式。"
        )

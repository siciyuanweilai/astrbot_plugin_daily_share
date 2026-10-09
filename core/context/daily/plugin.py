from __future__ import annotations

from ...database.keys import QZONE_TARGET_ID
from ...platform import parse_platform_session
from ..contextbase import ContextComponent


class ContextLifePluginService(ContextComponent):
    """读取生活插件上下文。"""

    async def get_life_context(self, target_umo: str = "") -> str | None:
        """获取生活上下文，支持解析结构化数据。"""
        raw_data = await self.service.daily_life_bridge.get_share_context(target_umo)
        if not raw_data:
            return None
        if self.is_group_chat(target_umo):
            return self.service.life_parse._parse_group_life_data(raw_data)
        return self._parse_life_data(raw_data)

    async def get_qzone_share_context(self) -> dict[str, str]:
        """同一次读取分别提供配图材料与当前说说材料。"""
        empty = {"life_context": "", "post_context": ""}
        raw_data = await self.service.daily_life_bridge.get_share_context(
            QZONE_TARGET_ID
        )
        if not raw_data:
            return empty
        return {
            "life_context": self._parse_life_data(raw_data),
            "post_context": self.service.life_parse._parse_qzone_post_data(raw_data),
        }

    async def get_qzone_interaction_context(self, target_umo: str) -> dict[str, str]:
        """分开返回公开互动的生活状态与目标关系，不携带私聊历史。"""
        empty = {"life_context": "", "relationship_context": ""}
        session = parse_platform_session(target_umo)
        scoped = bool(session and not session.is_group)
        scope = str(session) if scoped else QZONE_TARGET_ID
        raw_data = await self.service.daily_life_bridge.get_share_context(scope)
        if not raw_data:
            return empty
        # 私聊摘要、备忘录、约定和完整日程不能因修复身份识别而进入公开评论。
        public_data = {
            key: raw_data[key]
            for key in (
                "weather",
                "outfit",
                "meta",
                "state",
                "subject",
                "timeline",
                "current_facts",
            )
            if key in raw_data
        }
        return {
            "life_context": "\n\n".join(
                part
                for part in (
                    self._parse_life_data(public_data),
                    self.service.life_parse._public_expression(raw_data),
                )
                if part
            ),
            "relationship_context": (
                self.service.life_memory.format_qzone_relationship(
                    raw_data.get("relationships", [])
                )
                if scoped
                else ""
            ),
        }

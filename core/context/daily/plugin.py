from __future__ import annotations

from ..contextbase import ContextComponent


class ContextLifePluginService(ContextComponent):
    """读取生活插件上下文。"""

    async def get_life_context(self, target_umo: str = "") -> str | None:
        """获取生活上下文，支持解析结构化数据。"""
        if not self.life_conf.get("enable_life_context", True):
            return None
        raw_data = await self.service.daily_life_bridge.get_share_context(target_umo)
        return self._parse_life_data(raw_data) if raw_data else None

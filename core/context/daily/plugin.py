from __future__ import annotations

from ..shared import Optional, logger


class ContextLifePluginMixin:
    """读取 daily_life 插件上下文。"""

    LIFE_PLUGIN_KEYWORDS = ("astrbot_plugin_daily_life", "daily_life")

    def _get_life_plugin(self):
        """获取 daily_life 插件实例。"""
        if not self._life_plugin:
            for keyword in self.LIFE_PLUGIN_KEYWORDS:
                self._life_plugin = self._find_plugin(keyword)
                if self._life_plugin:
                    break
        return self._life_plugin

    async def get_life_context(self) -> Optional[str]:
        """获取生活上下文 (支持解析 JSON 数据)。"""
        if not self.life_conf.get("enable_life_context", True):
            return None

        plugin = self._get_life_plugin()
        if not plugin:
            return None

        get_context = getattr(plugin, "get_life_context", None)
        if not callable(get_context):
            return None
        try:
            raw_data = await get_context()
            if isinstance(raw_data, dict):
                return self._parse_life_data(raw_data)
        except Exception as e:
            logger.warning(f"[上下文] 生活日程插件方法调用出错: {e}")
        return None

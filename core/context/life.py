from __future__ import annotations

from .daily import (
    ContextLifeFormatMixin,
    ContextLifeMemoryMixin,
    ContextLifeParseMixin,
    ContextLifePluginMixin,
)


class ContextLifeMixin(
    ContextLifePluginMixin,
    ContextLifeParseMixin,
    ContextLifeMemoryMixin,
    ContextLifeFormatMixin,
):
    """生活上下文读取、解析与提示格式化能力。"""


__all__ = ["ContextLifeMixin"]

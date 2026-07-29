from __future__ import annotations

from typing import Any


class CommandServiceBase:
    """分享指令所需依赖的显式宿主契约。"""

    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin
        self.db = plugin.db
        self.config: dict = plugin.config
        self.basic_conf: dict = plugin.basic_conf
        self.extra_shares_conf: dict = plugin.extra_shares_conf
        self.qzone_conf: dict = plugin.qzone_conf


__all__ = ["CommandServiceBase"]

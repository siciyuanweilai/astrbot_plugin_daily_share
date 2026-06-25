from __future__ import annotations

from .routing import (
    PluginShareBriefingRouteMixin,
    PluginShareMainRouteMixin,
    PluginShareStartRouteMixin,
    PluginShareTypedRouteMixin,
)


class PluginShareRouteMixin(
    PluginShareMainRouteMixin,
    PluginShareTypedRouteMixin,
    PluginShareStartRouteMixin,
    PluginShareBriefingRouteMixin,
):
    """/分享 手动指令路由能力。"""


__all__ = ["PluginShareRouteMixin"]

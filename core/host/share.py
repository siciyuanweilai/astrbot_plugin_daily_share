from __future__ import annotations

from .image import PluginImageShareMixin
from .job import PluginShareJobMixin
from .manual import PluginManualShareMixin
from .route import PluginShareRouteMixin


class PluginShareMixin(
    PluginShareRouteMixin,
    PluginImageShareMixin,
    PluginShareJobMixin,
    PluginManualShareMixin,
):
    """/分享 命令入口组合。"""

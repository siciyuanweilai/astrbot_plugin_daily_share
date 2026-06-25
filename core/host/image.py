from __future__ import annotations

from .outbox import (
    ImageDeliveryShareMixin,
    ImageNewsShareMixin,
    ImageStaticShareMixin,
)


class PluginImageShareMixin(
    ImageStaticShareMixin,
    ImageDeliveryShareMixin,
    ImageNewsShareMixin,
):
    """手动图片分享能力。"""


__all__ = ["PluginImageShareMixin"]

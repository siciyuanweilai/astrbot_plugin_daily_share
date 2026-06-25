from __future__ import annotations

import random

from .transmit import (
    TaskDeliveryChainMixin,
    TaskDeliveryDelayMixin,
    TaskDeliveryMediaMixin,
    TaskDeliverySendMixin,
    TaskDeliveryStatusMixin,
)


class TaskDeliveryMixin(
    TaskDeliverySendMixin,
    TaskDeliveryMediaMixin,
    TaskDeliveryChainMixin,
    TaskDeliveryDelayMixin,
    TaskDeliveryStatusMixin,
):
    """平台发送与投递结果处理。"""


__all__ = ["TaskDeliveryMixin", "random"]

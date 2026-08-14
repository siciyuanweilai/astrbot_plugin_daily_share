from __future__ import annotations

import random

from .transmit import TaskDeliverySendService


class TaskDeliveryService(TaskDeliverySendService):
    """平台发送与投递结果处理。"""
__all__ = ["TaskDeliveryService", "random"]

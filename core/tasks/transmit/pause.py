from __future__ import annotations

import asyncio
import random


class TaskDeliveryDelayMixin:
    def _separate_send_delay_seconds(self) -> float:
        delay_str = self.image_conf.get("separate_send_delay", "1.0-2.0")
        try:
            text = str(delay_str or "").strip()
            if "-" in text:
                left, right = text.split("-", 1)
                d_min, d_max = float(left), float(right)
                if d_min > d_max:
                    d_min, d_max = d_max, d_min
                return random.uniform(max(0.0, d_min), max(0.0, d_max))
            return max(0.0, float(text))
        except (TypeError, ValueError):
            return 1.5

    async def random_sleep(self):
        """随机延迟"""
        if self.plugin._is_terminated:
            return
        await asyncio.sleep(self._separate_send_delay_seconds())

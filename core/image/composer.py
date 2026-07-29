from __future__ import annotations

from .vision.instruction import ImageVisualPromptService
from .vision.json import _extract_json_object


class ImageVisualService(ImageVisualPromptService):
    """图片视觉分析和提示词组装能力。"""


__all__ = ["ImageVisualService", "_extract_json_object"]

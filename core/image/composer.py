from __future__ import annotations

from .vision import (
    ImageVisualExtractMixin,
    ImageVisualFrameMixin,
    ImageVisualJudgeMixin,
    ImageVisualPersonaMixin,
    ImageVisualPromptMixin,
    _extract_json_object,
)


class ImageVisualMixin(
    ImageVisualPromptMixin,
    ImageVisualPersonaMixin,
    ImageVisualJudgeMixin,
    ImageVisualExtractMixin,
    ImageVisualFrameMixin,
):
    """图片视觉分析和提示词组装能力。"""


__all__ = ["ImageVisualMixin", "_extract_json_object"]

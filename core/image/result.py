from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GeneratedImage:
    """单次配图生成结果，不在服务上保存跨任务状态。"""

    path: str
    description: str
    contains_character: bool


__all__ = ["GeneratedImage"]

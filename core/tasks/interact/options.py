from dataclasses import dataclass
from typing import Any

from .tracker import (
    QZONE_AUTO_COMMENT_DEFAULT_LIMIT,
    QZONE_AUTO_LIKE_DEFAULT_LIMIT,
    QZONE_AUTO_REPLY_DEFAULT_LIMIT,
)


def _int_between(value: Any, default: int, *, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(min_value, min(max_value, parsed))


@dataclass(frozen=True)
class QzoneAutoInteractionConfig:
    enable_qzone: bool = False
    enable_interaction: bool = False
    enable_like: bool = False
    enable_comment: bool = False
    enable_reply: bool = False
    like_limit: int = QZONE_AUTO_LIKE_DEFAULT_LIMIT
    comment_limit: int = QZONE_AUTO_COMMENT_DEFAULT_LIMIT
    reply_limit: int = QZONE_AUTO_REPLY_DEFAULT_LIMIT
    comment_image_vision_enabled: bool = False
    comment_image_vision_limit: int = 1
    comment_image_vision_provider: str = ""

    @classmethod
    def from_conf(cls, conf: dict | None) -> "QzoneAutoInteractionConfig":
        source = conf if isinstance(conf, dict) else {}
        return cls(
            enable_qzone=bool(source.get("enable_qzone", False)),
            enable_interaction=bool(source.get("qzone_enable_auto_interaction", False)),
            enable_like=bool(source.get("qzone_enable_auto_like", False)),
            enable_comment=bool(source.get("qzone_enable_auto_comment", False)),
            enable_reply=bool(source.get("qzone_enable_auto_reply", False)),
            like_limit=_int_between(
                source.get("qzone_auto_like_limit", QZONE_AUTO_LIKE_DEFAULT_LIMIT),
                QZONE_AUTO_LIKE_DEFAULT_LIMIT,
                min_value=1,
                max_value=10,
            ),
            comment_limit=_int_between(
                source.get("qzone_auto_comment_limit", QZONE_AUTO_COMMENT_DEFAULT_LIMIT),
                QZONE_AUTO_COMMENT_DEFAULT_LIMIT,
                min_value=1,
                max_value=10,
            ),
            reply_limit=_int_between(
                source.get("qzone_auto_reply_limit", QZONE_AUTO_REPLY_DEFAULT_LIMIT),
                QZONE_AUTO_REPLY_DEFAULT_LIMIT,
                min_value=1,
                max_value=10,
            ),
            comment_image_vision_enabled=bool(source.get("qzone_enable_auto_comment_image_vision", False)),
            comment_image_vision_limit=_int_between(
                source.get("qzone_auto_comment_image_vision_limit", 1),
                1,
                min_value=1,
                max_value=9,
            ),
            comment_image_vision_provider=str(source.get("qzone_auto_comment_image_vision_provider", "") or "").strip(),
        )

    @property
    def child_enabled(self) -> bool:
        return bool(self.enable_like or self.enable_comment or self.enable_reply)

    @property
    def interaction_enabled(self) -> bool:
        return bool(self.enable_qzone and self.enable_interaction and self.child_enabled)

from dataclasses import dataclass
from typing import Any

from .tracker import (
    QZONE_AUTO_COMMENT_DEFAULT_LIMIT,
    QZONE_AUTO_INTERACTION_RATE_LIMIT_COOLDOWN_SECONDS,
    QZONE_AUTO_LIKE_DEFAULT_LIMIT,
    QZONE_AUTO_REPLY_DEFAULT_LIMIT,
)


QZONE_RATE_LIMIT_POLICY_RECORD_ONLY = "record_only"
QZONE_RATE_LIMIT_POLICY_COOLDOWN = "cooldown"


def _int_between(value: Any, default: int, *, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(min_value, min(max_value, parsed))


def _rate_limit_policy(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"cooldown", "pause", "block", "block_until_cooldown"}:
        return QZONE_RATE_LIMIT_POLICY_COOLDOWN
    return QZONE_RATE_LIMIT_POLICY_RECORD_ONLY


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
    rate_limit_policy: str = QZONE_RATE_LIMIT_POLICY_RECORD_ONLY
    rate_limit_cooldown_seconds: int = QZONE_AUTO_INTERACTION_RATE_LIMIT_COOLDOWN_SECONDS

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
            rate_limit_policy=_rate_limit_policy(
                source.get("qzone_auto_interaction_rate_limit_policy", QZONE_RATE_LIMIT_POLICY_RECORD_ONLY)
            ),
            rate_limit_cooldown_seconds=_int_between(
                source.get(
                    "qzone_auto_interaction_rate_limit_cooldown_seconds",
                    QZONE_AUTO_INTERACTION_RATE_LIMIT_COOLDOWN_SECONDS,
                ),
                QZONE_AUTO_INTERACTION_RATE_LIMIT_COOLDOWN_SECONDS,
                min_value=60,
                max_value=86400,
            ),
        )

    @property
    def child_enabled(self) -> bool:
        return bool(self.enable_like or self.enable_comment or self.enable_reply)

    @property
    def interaction_enabled(self) -> bool:
        return bool(self.enable_qzone and self.enable_interaction and self.child_enabled)

    def rate_limited_until(self, state: dict, *, now: int) -> int:
        if self.rate_limit_policy != QZONE_RATE_LIMIT_POLICY_COOLDOWN or not isinstance(state, dict):
            return 0
        try:
            until = int(state.get("rate_limited_until") or 0)
        except Exception:
            return 0
        return until if until > int(now or 0) else 0

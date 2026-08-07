from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from typing import Any

_TARGET_FIELDS: dict[str, tuple[str, ...]] = {
    "receiver": ("groups", "users"),
    "extra_shares": ("briefing_groups", "briefing_users"),
}


def _revision(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _section(config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = config.get(key)
    return value if isinstance(value, Mapping) else {}


def target_config_snapshot(config: Mapping[str, Any]) -> dict[str, list[Any]]:
    receiver = _section(config, "receiver")
    extra = _section(config, "extra_shares")
    return {
        "groups": list(receiver.get("groups") or []),
        "users": list(receiver.get("users") or []),
        "briefing_groups": list(extra.get("briefing_groups") or []),
        "briefing_users": list(extra.get("briefing_users") or []),
    }


def target_config_revision(config: Mapping[str, Any]) -> str:
    return _revision(target_config_snapshot(config))


def is_target_config_field(section_key: str, field_key: str) -> bool:
    return field_key in _TARGET_FIELDS.get(section_key, ())


def settings_config_snapshot(config: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = copy.deepcopy(dict(config))
    for section_key, field_keys in _TARGET_FIELDS.items():
        section = snapshot.get(section_key)
        if not isinstance(section, dict):
            continue
        for field_key in field_keys:
            section.pop(field_key, None)
        if not section:
            snapshot.pop(section_key, None)
    return snapshot


def settings_config_revision(config: Mapping[str, Any]) -> str:
    return _revision(settings_config_snapshot(config))


def require_current_revision(
    provided: object,
    current: str,
    *,
    conflict_message: str,
) -> None:
    if str(provided or "").strip() != current:
        raise RuntimeError(conflict_message)

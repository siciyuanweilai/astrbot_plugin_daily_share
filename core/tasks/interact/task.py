from __future__ import annotations

import time

from astrbot.api import logger

from .options import QzoneAutoInteractionConfig
from .formatting import _qzone_summary_generation_failed_suffix
from .tracker import _mark_qzone_rate_limited


QZONE_QUERY_MAX_POSTS = 20
QZONE_QUERY_MIN_POSTS = 5


def _qzone_auto_result(**extra: int | bool) -> dict:
    result = {
        "enabled": False,
        "scanned": 0,
        "skipped": 0,
        "failed": 0,
        "generation_failed": 0,
    }
    result.update(extra)
    return result


def _qzone_service(owner):
    return getattr(getattr(owner, "plugin", None), "qzone_service", None)


def _qzone_query_fetch_count(limit: int, multiplier: int) -> int:
    return min(QZONE_QUERY_MAX_POSTS, max(QZONE_QUERY_MIN_POSTS, int(limit or 0) * multiplier))


def _qzone_auto_config(owner) -> QzoneAutoInteractionConfig:
    getter = getattr(owner, "_qzone_auto_config", None)
    if callable(getter):
        return getter()
    return QzoneAutoInteractionConfig.from_conf(getattr(owner, "qzone_conf", {}))


def _qzone_should_log_summary(result: dict, *success_keys: str) -> bool:
    if not isinstance(result, dict):
        return False
    if any(int(result.get(key, 0) or 0) > 0 for key in success_keys):
        return True
    return bool(int(result.get("failed", 0) or 0) or int(result.get("generation_failed", 0) or 0))


async def _qzone_finish_task(
    owner,
    *,
    state_key: str,
    state: dict,
    processed: dict,
    result: dict,
    emit_summary: bool,
    task_label: str,
    count_label: str,
    count_key: str,
    success_keys: tuple[str, ...],
    run_at: int | None = None,
) -> None:
    await owner._qzone_auto_save_state(state_key, state, processed, result, run_at=run_at)
    if not (emit_summary and _qzone_should_log_summary(result, *success_keys)):
        return
    logger.info(
        f"[每日分享] QQ 空间{task_label}完成: "
        f"查询 {result['scanned']} 条，{count_label} {result[count_key]} 条，"
        f"跳过 {result['skipped']} 条"
        f"{_qzone_summary_generation_failed_suffix(result)}"
    )


async def _qzone_abort_query_failure(
    owner,
    *,
    state_key: str,
    state: dict,
    processed: dict,
    result: dict,
    run_at: int,
    message: str,
    error: Exception,
) -> dict:
    result["failed"] += 1
    logger.warning(f"{message}: {error}")
    await owner._qzone_auto_save_state(state_key, state, processed, result, run_at=run_at)
    return result


async def _qzone_prepare_task(
    owner,
    *,
    result: dict,
    enabled: bool,
    state_key: str,
    cooldown_hours: int,
    disabled_log: str,
) -> tuple[bool, dict, dict, int]:
    cfg = _qzone_auto_config(owner)
    if owner.plugin._is_terminated:
        return False, {}, {}, int(time.time())
    if not cfg.enable_qzone:
        logger.debug("[每日分享] QQ 空间未开启，跳过自动互动。")
        return False, {}, {}, int(time.time())
    if not enabled:
        logger.debug(disabled_log)
        return False, {}, {}, int(time.time())

    result["enabled"] = True
    now = int(time.time())
    state = await owner.db.get_state(state_key, {})
    if not isinstance(state, dict):
        state = {}
    processed = owner._qzone_auto_comment_prune_state(
        state,
        now=now,
        cooldown_hours=cooldown_hours,
    )
    if await _qzone_save_rate_limited_skip(
        owner,
        state_key=state_key,
        state=state,
        processed=processed,
        result=result,
        run_at=now,
    ):
        return False, state, processed, now
    return True, state, processed, now


async def _qzone_save_rate_limited_skip(
    owner,
    *,
    state_key: str,
    state: dict,
    processed: dict,
    result: dict,
    run_at: int,
) -> bool:
    cfg = _qzone_auto_config(owner)
    until = cfg.rate_limited_until(state, now=run_at)
    if not until:
        return False
    result["skipped"] += 1
    await owner._qzone_auto_save_state(state_key, state, processed, result, run_at=run_at)
    logger.debug(f"[每日分享] QQ 空间自动互动仍在限流冷却中，跳过本轮: {until}")
    return True


def _mark_current_qzone_rate_limited(owner, state: dict, exc: Exception) -> None:
    cfg = _qzone_auto_config(owner)
    _mark_qzone_rate_limited(
        state,
        reason=str(exc),
        now=int(time.time()),
        cooldown_seconds=cfg.rate_limit_cooldown_seconds,
    )

from astrbot.api import logger

from .formatting import _qzone_summary_generation_failed_suffix


_QZONE_INTERACTION_TOTAL_KEYS = (
    "scanned",
    "liked",
    "commented",
    "replied",
    "skipped",
    "failed",
    "generation_failed",
)
_QZONE_INTERACTION_REPORT_KEYS = ("liked", "commented", "replied", "failed", "generation_failed")


def _qzone_empty_interaction_result() -> dict:
    return {
        "enabled": False,
        "like": {},
        "comment": {},
        "reply": {},
        **{key: 0 for key in _QZONE_INTERACTION_TOTAL_KEYS},
    }


def _qzone_merge_interaction_result(result: dict, *sections: dict) -> None:
    for section in sections:
        if not isinstance(section, dict):
            continue
        for key in _QZONE_INTERACTION_TOTAL_KEYS:
            result[key] += int(section.get(key, 0) or 0)


def _qzone_should_log_interaction_summary(result: dict) -> bool:
    return any(int(result.get(key, 0) or 0) > 0 for key in _QZONE_INTERACTION_REPORT_KEYS)


def _qzone_log_interaction_summary(result: dict) -> None:
    logger.info(
        "[每日分享] QQ 空间自动互动完成: "
        f"查询 {result['scanned']} 条，点赞 {result['liked']} 条，评论 {result['commented']} 条，"
        f"回评 {result['replied']} 条，跳过 {result['skipped']} 条"
        f"{_qzone_summary_generation_failed_suffix(result)}"
    )

class QzoneAutoInteractionRateLimited(RuntimeError):
    """QQ 空间要求自动互动稍后重试时抛出。"""


def _is_qzone_deleted_or_unavailable_error(exc: Exception) -> bool:
    text = str(exc or "")
    return any(token in text for token in ("原文已经被删除", "无法查看", "deleted", "not found"))


def _is_qzone_retry_later_error(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return any(
        token in text
        for token in (
            "使用人数过多",
            "该条内容已被删除",
            "稍后再试",
            "请稍后",
            "操作频繁",
            "过于频繁",
            "风控",
            "rate limit",
            "too many",
            "try again later",
        )
    )

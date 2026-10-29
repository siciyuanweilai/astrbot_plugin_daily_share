"""在真正的平台提交边界通知当前机会；状态随 asyncio 上下文隔离。"""

from contextvars import ContextVar

current_submission = ContextVar("daily_share_submission", default=None)


async def mark_submission(phase="submitting"):
    attempt = current_submission.get()
    if (
        attempt is None
        or not attempt.get("active", True)
        or attempt.get("phase") == phase
    ):
        return
    # 一个机会可能分阶段发送文字、图片；首次提交后不能退回准备状态。
    if phase == "submitting" and attempt.get("phase") in {"completed", "deferred"}:
        return
    await attempt["checkpoint"](phase)
    attempt["phase"] = phase

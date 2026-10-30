"""在真正的平台提交边界通知当前机会；状态随 asyncio 上下文隔离。"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar

from .integrations.mediajob import current_share_job

current_submission = ContextVar("daily_share_submission", default=None)
current_request_submission = ContextVar("daily_share_request_submission", default=None)


@asynccontextmanager
async def request_submission(checkpoint: Callable[[], Awaitable[None]]) -> AsyncIterator[dict]:
    """仅当前动作的实际写请求能领取提交标记；子任务退出后不能补写。"""
    state = {"checkpoint": checkpoint, "submitted": False, "active": True}
    token = current_request_submission.set(state)
    try:
        yield state
    finally:
        state["active"] = False
        current_request_submission.reset(token)


async def mark_request_submission() -> None:
    state = current_request_submission.get()
    if state and state["active"] and not state["submitted"]:
        await state["checkpoint"]()
        state["submitted"] = True


async def mark_submission(phase: str = "submitting") -> None:
    job = current_share_job.get()
    if phase == "submitting" and job is not None:
        service = job.get("service")
        if service is not None and job.get("id") in service.active:
            await service.mark_submitting()
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

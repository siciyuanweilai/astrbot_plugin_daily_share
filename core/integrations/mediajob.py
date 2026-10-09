from __future__ import annotations

from contextvars import ContextVar


class ShareMediaPending(Exception):
    """An accepted generation belongs to an unfinished sharing workflow."""


current_share_job: ContextVar[dict | None] = ContextVar("daily_share_job", default=None)


async def save_share_job(job: dict) -> None:
    service = job["service"]
    await service.save(job)

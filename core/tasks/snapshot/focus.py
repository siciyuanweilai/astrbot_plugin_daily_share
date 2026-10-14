from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..cache import TaskNewsCacheService


class TaskNewsCacheFocusService:
    def __init__(self, owner: TaskNewsCacheService) -> None:
        self.owner = owner

    def _news_snapshot_focus_key(self, target_uid: str) -> str:
        return f"{self.owner._news_snapshot_key(target_uid)}:focus"

    async def _remember_news_focus(
        self, target_uid: str, snapshot: dict, index: int
    ) -> None:
        focus = {
            "target_id": str(target_uid or "").strip(),
            "source_key": snapshot.get("source_key") or "",
            "index": index,
        }
        await self.owner.db.set_cache_state(
            self.owner._news_snapshot_focus_key(target_uid), focus
        )

    async def _focused_news_index(
        self, target_uid: str, snapshot: dict, source_key: str | None
    ) -> int | None:
        focus = await self.owner.db.get_cache_state(
            self.owner._news_snapshot_focus_key(target_uid), {}
        )
        focus_source = str((focus or {}).get("source_key") or "")
        focus_index = self.owner._coerce_news_tool_index((focus or {}).get("index"))
        snapshot_source = str(snapshot.get("source_key") or "")
        if focus_index and snapshot_source and focus_source == snapshot_source:
            return focus_index
        return None

from __future__ import annotations

from .store import TaskNewsCacheStoreService


class TaskNewsCacheFocusService(TaskNewsCacheStoreService):
    def _news_snapshot_focus_key(self, target_uid: str) -> str:
        return f"{self._news_snapshot_key(target_uid)}:focus"

    async def _remember_news_focus(
        self, target_uid: str, snapshot: dict, index: int
    ) -> None:
        focus = {
            "target_id": str(target_uid or "").strip(),
            "source_key": snapshot.get("source_key") or "",
            "index": index,
        }
        await self.db.set_cache_state(self._news_snapshot_focus_key(target_uid), focus)

    async def _focused_news_index(
        self, target_uid: str, snapshot: dict, source_key: str | None
    ) -> int | None:
        focus = await self.db.get_cache_state(
            self._news_snapshot_focus_key(target_uid), {}
        )
        focus_source = str((focus or {}).get("source_key") or "")
        focus_index = self._coerce_news_tool_index((focus or {}).get("index"))
        snapshot_source = str(snapshot.get("source_key") or "")
        if focus_index and snapshot_source and focus_source == snapshot_source:
            return focus_index
        return None

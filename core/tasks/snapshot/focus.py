from __future__ import annotations

from datetime import datetime


class TaskNewsCacheFocusMixin:
    def _news_snapshot_focus_key(self, target_uid: str) -> str:
        return f"{self._news_snapshot_key(target_uid)}:focus"

    async def _remember_news_focus(self, target_uid: str, snapshot_key: str, snapshot: dict, index: int) -> None:
        focus = {
            "source_key": snapshot.get("source_key") or "",
            "index": index,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        focused_snapshot = dict(snapshot)
        focused_snapshot["last_focus_index"] = index
        focused_snapshot["last_focus_at"] = focus["updated_at"]
        await self.db.set_state(snapshot_key, focused_snapshot)
        await self.db.set_state(self._news_snapshot_focus_key(target_uid), focus)

        source_key = focused_snapshot.get("source_key")
        if source_key:
            source_state_key = self._news_snapshot_source_key(target_uid, source_key)
            if source_state_key != snapshot_key:
                source_snapshot = await self.db.get_state(source_state_key, {})
                if self._is_news_snapshot(source_snapshot):
                    source_snapshot = dict(source_snapshot)
                    source_snapshot["last_focus_index"] = index
                    source_snapshot["last_focus_at"] = focus["updated_at"]
                    await self.db.set_state(source_state_key, source_snapshot)

    async def _focused_news_index(self, target_uid: str, snapshot: dict, source_key: str | None) -> int | None:
        focus = await self.db.get_state(self._news_snapshot_focus_key(target_uid), {})
        focus_source = str((focus or {}).get("source_key") or "")
        focus_index = self._coerce_news_tool_index((focus or {}).get("index"))
        if focus_index and (not source_key or focus_source == (snapshot.get("source_key") or "")):
            return focus_index
        return None

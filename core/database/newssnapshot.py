import json
from typing import Any

from .repository import DatabaseRepository


class DatabaseNewsSnapshotService(DatabaseRepository):
    """保存成功发送的新闻长图所对应的只追加快照。"""

    def _sync_get_latest_news_snapshot(
        self,
        target_id: str,
        source_key: str | None = None,
    ) -> dict[str, Any] | None:
        sql = """
            SELECT id, target_id, source_key, source_name, image_url, items, created_at
            FROM news_snapshot_history
            WHERE target_id = ?
        """
        params: list[Any] = [target_id]
        if source_key:
            sql += " AND source_key = ?"
            params.append(source_key)
        sql += " ORDER BY id DESC LIMIT 1"
        row = self._fetch_one(sql, params)
        return self._news_snapshot_row(row) if row else None

    def _sync_get_latest_news_snapshot_with_focus(
        self,
        target_id: str,
        focus_key: str,
    ) -> tuple[dict[str, Any] | None, Any]:
        with self._connection(
            timeout=self.manager.CONTEXT_READ_TIMEOUT_SECONDS
        ) as conn:
            snapshot_row = conn.execute(
                """
                SELECT id, target_id, source_key, source_name, image_url, items, created_at
                FROM news_snapshot_history
                WHERE target_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (target_id,),
            ).fetchone()
            focus_row = conn.execute(
                "SELECT value FROM plugin_state WHERE domain = 'cache' AND key = ?",
                (focus_key,),
            ).fetchone()

        focus: Any = {}
        if focus_row:
            try:
                focus = json.loads(focus_row[0])
            except (TypeError, json.JSONDecodeError):
                focus = focus_row[0]
        snapshot = self._news_snapshot_row(snapshot_row) if snapshot_row else None
        return snapshot, focus

    @staticmethod
    def _news_snapshot_row(row) -> dict[str, Any]:
        if not row:
            return {}
        try:
            items = json.loads(row[5])
        except (TypeError, json.JSONDecodeError):
            items = []
        return {
            "snapshot_id": row[0],
            "target_id": row[1],
            "source_key": row[2],
            "source_name": row[3],
            "image_url": row[4],
            "items": items if isinstance(items, list) else [],
            "created_at": str(row[6] or ""),
        }

    async def get_latest_news_snapshot(
        self,
        target_id: str,
        source_key: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._execute(
            self._sync_get_latest_news_snapshot, target_id, source_key
        )

    async def get_latest_news_snapshot_with_focus(
        self,
        target_id: str,
        focus_key: str,
    ) -> tuple[dict[str, Any] | None, Any]:
        return await self._execute_context(
            self._sync_get_latest_news_snapshot_with_focus,
            target_id,
            focus_key,
        )

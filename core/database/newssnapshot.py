import json
from datetime import datetime
from typing import Any

from .repository import DatabaseRepository


class DatabaseNewsSnapshotService(DatabaseRepository):
    """保存成功发送的新闻长图所对应的只追加快照。"""

    def _sync_add_news_snapshot(
        self,
        target_id: str,
        source_key: str,
        source_name: str,
        image_url: str,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        items_json = json.dumps(items, ensure_ascii=False)
        with self._connection(write=True) as conn:
            cursor = conn.execute(
                """
                INSERT INTO news_snapshot_history (
                    target_id, source_key, source_name, image_url, items, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    target_id,
                    source_key,
                    source_name,
                    image_url,
                    items_json,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            snapshot_id = cursor.lastrowid

            # 每个目标保留最近 100 次发送，并额外保留各新闻源的最新一次。
            conn.execute(
                """
                DELETE FROM news_snapshot_history
                WHERE target_id = ? AND id NOT IN (
                    SELECT id FROM news_snapshot_history
                    WHERE target_id = ?
                    ORDER BY id DESC
                    LIMIT 100
                )
                AND id NOT IN (
                    SELECT MAX(id) FROM news_snapshot_history
                    WHERE target_id = ?
                    GROUP BY source_key
                )
                """,
                (target_id, target_id, target_id),
            )
            row = conn.execute(
                """
                SELECT id, target_id, source_key, source_name, image_url, items, created_at
                FROM news_snapshot_history
                WHERE id = ?
                """,
                (snapshot_id,),
            ).fetchone()
        return self._news_snapshot_row(row)

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
        with self._connection() as conn:
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

    async def add_news_snapshot(
        self,
        target_id: str,
        source_key: str,
        source_name: str,
        image_url: str,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return await self._execute(
            self._sync_add_news_snapshot,
            target_id,
            source_key,
            source_name,
            image_url,
            items,
        )

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
        return await self._execute(
            self._sync_get_latest_news_snapshot_with_focus,
            target_id,
            focus_key,
        )

from datetime import datetime

from .dbschema import _HISTORY_SELECT_COLUMNS
from .repository import DatabaseRepository


class DatabaseHistoryService(DatabaseRepository):
    """分享历史和失败记录。"""

    def _sync_add_history(
        self,
        target_id,
        share_type,
        content,
        success,
        error_reason="",
        media_type="",
        media_url="",
        media_path="",
        source_type="",
        degraded=False,
        degradation_reason="",
    ):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._execute_write(
            """
            INSERT INTO sent_history (
                target_id, share_type, content, success, created_at,
                error_reason, media_type, media_url, media_path, source_type,
                degraded, degradation_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                str(target_id),
                str(share_type),
                str(content),
                1 if success else 0,
                now_str,
                str(error_reason or ""),
                str(media_type or ""),
                str(media_url or ""),
                str(media_path or ""),
                str(source_type or ""),
                1 if degraded else 0,
                str(degradation_reason or ""),
            ),
        )

    async def add_sent_history(
        self,
        target_id: str,
        share_type: str,
        content: str,
        success: bool = True,
        *,
        error_reason: str = "",
        media_type: str = "",
        media_url: str = "",
        media_path: str = "",
        source_type: str = "",
        degraded: bool = False,
        degradation_reason: str = "",
    ):
        await self._execute(
            self._sync_add_history,
            target_id,
            share_type,
            content,
            success,
            error_reason,
            media_type,
            media_url,
            media_path,
            source_type,
            degraded,
            degradation_reason,
        )

    def _history_item_from_row(self, row) -> dict:
        return {
            "id": row[0],
            "timestamp": row[1],
            "target_id": row[2],
            "type": row[3],
            "content": row[4],
            "success": bool(row[5]),
            "error_reason": row[6] or "",
            "media_type": row[7] or "",
            "media_url": row[8] or "",
            "media_path": row[9] or "",
            "source_type": row[10] or "",
            "degraded": bool(row[11]),
            "degradation_reason": row[12] or "",
        }

    def _sync_get_recent_history(self, limit: int) -> list[dict]:
        rows = self._fetch_all(
            f"""
            SELECT {_HISTORY_SELECT_COLUMNS}
            FROM sent_history
            ORDER BY id DESC LIMIT ?
        """,
            (limit,),
        )
        return [self._history_item_from_row(r) for r in rows]

    async def get_recent_history(self, limit: int = 5):
        return await self._execute(self._sync_get_recent_history, limit)

    def _sync_get_recent_history_by_target(
        self, target_id: str, limit: int
    ) -> list[dict]:
        rows = self._fetch_all(
            f"""
            SELECT {_HISTORY_SELECT_COLUMNS}
            FROM sent_history
            WHERE target_id = ? AND success = 1
            ORDER BY id DESC LIMIT ?
        """,
            (str(target_id), limit),
        )
        return [self._history_item_from_row(r) for r in rows]

    async def get_recent_history_by_target(self, target_id: str, limit: int = 3):
        return await self._execute(
            self._sync_get_recent_history_by_target, target_id, limit
        )

    def _sync_get_history_by_id(self, history_id: int) -> dict | None:
        row = self._fetch_one(
            f"""
            SELECT {_HISTORY_SELECT_COLUMNS}
            FROM sent_history
            WHERE id = ?
        """,
            (int(history_id),),
        )
        return self._history_item_from_row(row) if row else None

    async def get_history_by_id(self, history_id: int):
        return await self._execute(self._sync_get_history_by_id, history_id)

    def _sync_get_history_by_ids(self, history_ids: list[int]) -> list[dict]:
        ids = [int(item) for item in history_ids if int(item) > 0]
        if not ids:
            return []

        placeholders = ",".join("?" for _ in ids)
        rows = self._fetch_all(
            f"""
            SELECT {_HISTORY_SELECT_COLUMNS}
            FROM sent_history
            WHERE id IN ({placeholders})
        """,
            tuple(ids),
        )
        return [self._history_item_from_row(r) for r in rows]

    async def get_history_by_ids(self, history_ids: list[int]):
        return await self._execute(self._sync_get_history_by_ids, history_ids)

    def _sync_count_history_media_path_refs(self, media_path: str) -> int:
        media_path = str(media_path or "").strip()
        if not media_path:
            return 0

        row = self._fetch_one(
            "SELECT COUNT(*) FROM sent_history WHERE media_path = ?",
            (media_path,),
        )
        return int(row[0] or 0)

    async def count_history_media_path_refs(self, media_path: str) -> int:
        return await self._execute(self._sync_count_history_media_path_refs, media_path)

    def _sync_count_history_media_refs(self, media_refs: list[str]) -> int:
        refs = sorted(
            {str(item or "").strip() for item in media_refs if str(item or "").strip()}
        )
        if not refs:
            return 0

        placeholders = ",".join("?" for _ in refs)
        row = self._fetch_one(
            f"""
            SELECT COUNT(*)
            FROM sent_history
            WHERE media_path IN ({placeholders})
            """,
            tuple(refs),
        )
        return int(row[0] or 0)

    async def count_history_media_refs(self, media_refs: list[str]) -> int:
        return await self._execute(self._sync_count_history_media_refs, media_refs)

    def _sync_delete_history_by_ids(self, history_ids: list[int]) -> int:
        ids = [int(item) for item in history_ids if int(item) > 0]
        if not ids:
            return 0

        placeholders = ",".join("?" for _ in ids)
        return self._execute_write(
            f"DELETE FROM sent_history WHERE id IN ({placeholders})",
            tuple(ids),
        )

    async def delete_history_by_ids(self, history_ids: list[int]) -> int:
        return await self._execute(self._sync_delete_history_by_ids, history_ids)

    def _sync_get_recent_failures(self, limit: int) -> list[dict]:
        rows = self._fetch_all(
            f"""
            SELECT {_HISTORY_SELECT_COLUMNS}
            FROM sent_history
            WHERE success = 0
            ORDER BY id DESC LIMIT ?
        """,
            (limit,),
        )
        return [self._history_item_from_row(r) for r in rows]

    async def get_recent_failures(self, limit: int = 10):
        return await self._execute(self._sync_get_recent_failures, limit)

    def _sync_clear_failures(self) -> int:
        return self._execute_write("DELETE FROM sent_history WHERE success = 0")

    async def clear_failures(self) -> int:
        return await self._execute(self._sync_clear_failures)

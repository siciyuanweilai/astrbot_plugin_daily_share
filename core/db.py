import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .database.history import DatabaseHistoryService
from .database.maintenance import DatabaseMaintenanceService
from .database.metrics import DatabaseDashboardService
from .database.schema import (
    SchemaInitializationResult,
    initialize_schema,
)
from .database.newssnapshot import DatabaseNewsSnapshotService
from .database.state import DatabaseStateService
from .database.topics import DatabaseTopicService


class DatabaseManager:
    """聚合数据库连接、建表和各类数据访问能力。"""

    def __init__(self, data_dir: Path, *, initialize: bool = True):
        self.db_path = Path(data_dir) / "daily_share.db"
        self._initialized = False
        self._closed = False
        self._initialize_lock = asyncio.Lock()
        self._close_lock = asyncio.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="daily-share-db",
        )
        self.history = DatabaseHistoryService(self)
        self.snapshots = DatabaseNewsSnapshotService(self)
        self.state = DatabaseStateService(self)
        self.topics = DatabaseTopicService(self)
        self.metrics = DatabaseDashboardService(self)
        self.maintenance = DatabaseMaintenanceService(self)
        if initialize:
            self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    @contextmanager
    def _connection(self, *, write: bool = False):
        """提供自动提交、回滚和关闭的数据库连接。"""
        conn = self._get_conn()
        try:
            yield conn
            if write:
                conn.commit()
        except Exception:
            if write:
                conn.rollback()
            raise
        finally:
            conn.close()

    def _fetch_one(self, sql: str, params=()):
        with self._connection() as conn:
            return conn.execute(sql, params).fetchone()

    def _fetch_all(self, sql: str, params=()):
        with self._connection() as conn:
            return conn.execute(sql, params).fetchall()

    def _execute_write(self, sql: str, params=()) -> int:
        with self._connection(write=True) as conn:
            cursor = conn.execute(sql, params)
            return int(cursor.rowcount or 0)

    def _init_db(self) -> SchemaInitializationResult:
        # 数据库自身负责创建目录，首次安装和独立测试无需依赖外部生命周期顺序。
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            result = initialize_schema(conn)

        self._initialized = True
        return result

    async def clean_expired_data(self, days_limit: int):
        return await self.maintenance.clean_expired_data(days_limit)

    async def record_topic(self, target_id: str, category: str, content_key: str):
        return await self.topics.record_topic(target_id, category, content_key)

    async def get_used_topics(
        self, target_id: str, category: str, days_limit: int = 60
    ):
        return await self.topics.get_used_topics(target_id, category, days_limit)

    async def get_recent_media(self, limit: int = 12, days: int = 0):
        return await self.metrics.get_recent_media(limit, days)

    async def get_recent_dynamics(
        self,
        limit: int = 12,
        days: int = 0,
        media_kind: str = "",
        share_type: str = "",
        today_only: bool = False,
    ):
        return await self.metrics.get_recent_dynamics(
            limit, days, media_kind, share_type, today_only
        )

    async def get_dashboard_dynamic_summary(self, days: int = 0):
        return await self.metrics.get_dashboard_dynamic_summary(days)

    async def get_history_summary(self):
        return await self.metrics.get_history_summary()

    async def get_target_stats(self, days: int = 30, briefing=None):
        return await self.metrics.get_target_stats(days, briefing)

    async def add_news_snapshot(
        self,
        target_id: str,
        source_key: str,
        source_name: str,
        image_url: str,
        items: list,
    ):
        return await self.snapshots.add_news_snapshot(
            target_id, source_key, source_name, image_url, items
        )

    async def get_latest_news_snapshot(
        self, target_id: str, source_key: str | None = None
    ):
        return await self.snapshots.get_latest_news_snapshot(target_id, source_key)

    async def get_latest_news_snapshot_with_focus(
        self,
        target_id: str,
        focus_key: str,
    ):
        return await self.snapshots.get_latest_news_snapshot_with_focus(
            target_id,
            focus_key,
        )

    async def add_sent_history(
        self,
        target_id: str,
        share_type: str,
        content: str,
        success: bool,
        error_reason: str = "",
        media_type: str = "",
        media_url: str = "",
        media_path: str = "",
        source_type: str = "",
        degraded: bool = False,
        degradation_reason: str = "",
    ):
        return await self.history.add_sent_history(
            target_id,
            share_type,
            content,
            success,
            error_reason=error_reason,
            media_type=media_type,
            media_url=media_url,
            media_path=media_path,
            source_type=source_type,
            degraded=degraded,
            degradation_reason=degradation_reason,
        )

    async def get_recent_history(self, limit: int = 5):
        return await self.history.get_recent_history(limit)

    async def get_recent_history_by_target(self, target_id: str, limit: int = 3):
        return await self.history.get_recent_history_by_target(target_id, limit)

    async def get_history_by_id(self, history_id: int):
        return await self.history.get_history_by_id(history_id)

    async def get_history_by_ids(self, history_ids: list[int]):
        return await self.history.get_history_by_ids(history_ids)

    async def count_history_media_path_refs(self, media_path: str):
        return await self.history.count_history_media_path_refs(media_path)

    async def count_history_media_refs(self, media_refs: list[str]):
        return await self.history.count_history_media_refs(media_refs)

    async def delete_history_by_ids(self, history_ids: list[int]):
        return await self.history.delete_history_by_ids(history_ids)

    async def get_recent_failures(self, limit: int = 10):
        return await self.history.get_recent_failures(limit)

    async def clear_failures(self):
        return await self.history.clear_failures()

    async def get_share_state(self, key: str, default=None):
        return await self.state.get_share_state(key, default)

    async def set_share_state(self, key: str, value):
        return await self.state.set_share_state(key, value)

    async def update_share_state(self, key: str, updates: dict):
        return await self.state.update_share_state(key, updates)

    async def get_qzone_state(self, key: str, default=None):
        return await self.state.get_qzone_state(key, default)

    async def set_qzone_state(self, key: str, value):
        return await self.state.set_qzone_state(key, value)

    async def update_qzone_state(self, key: str, updates: dict):
        return await self.state.update_qzone_state(key, updates)

    async def get_context_state(self, key: str, default=None):
        return await self.state.get_context_state(key, default)

    async def set_context_state(self, key: str, value):
        return await self.state.set_context_state(key, value)

    async def update_context_state(self, key: str, updates: dict):
        return await self.state.update_context_state(key, updates)

    async def get_cache_state(self, key: str, default=None):
        return await self.state.get_cache_state(key, default)

    async def set_cache_state(self, key: str, value):
        return await self.state.set_cache_state(key, value)

    async def update_cache_state(self, key: str, updates: dict):
        return await self.state.update_cache_state(key, updates)

    async def initialize(self) -> None:
        async with self._initialize_lock:
            if self._initialized:
                return
            await self._execute(self._init_db)

    async def close(self) -> None:
        async with self._close_lock:
            if self._closed:
                return
            self._closed = True
            await asyncio.to_thread(
                self._executor.shutdown,
                wait=True,
                cancel_futures=False,
            )

    def _sync_add_sent_history_with_news_snapshots(
        self,
        history: dict,
        snapshots: list[dict],
    ) -> tuple[int, list[int]]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._connection(write=True) as conn:
            history_cursor = conn.execute(
                """
                INSERT INTO sent_history (
                    target_id, share_type, content, success, created_at,
                    error_reason, media_type, media_url, media_path, source_type,
                    degraded, degradation_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(history.get("target_id") or ""),
                    str(history.get("share_type") or ""),
                    str(history.get("content") or ""),
                    1,
                    now,
                    "",
                    str(history.get("media_type") or ""),
                    str(history.get("media_url") or ""),
                    str(history.get("media_path") or ""),
                    str(history.get("source_type") or ""),
                    1 if history.get("degraded") else 0,
                    str(history.get("degradation_reason") or ""),
                ),
            )
            snapshot_ids = []
            snapshot_targets = set()
            for snapshot in snapshots:
                target_id = str(snapshot.get("target_id") or "").strip()
                if not target_id:
                    continue
                snapshot_cursor = conn.execute(
                    """
                    INSERT INTO news_snapshot_history (
                        target_id, source_key, source_name, image_url, items, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        target_id,
                        str(snapshot.get("source_key") or ""),
                        str(snapshot.get("source_name") or ""),
                        str(snapshot.get("image_url") or ""),
                        json.dumps(snapshot.get("items") or [], ensure_ascii=False),
                        now,
                    ),
                )
                snapshot_ids.append(int(snapshot_cursor.lastrowid))
                snapshot_targets.add(target_id)

            for target_id in snapshot_targets:
                conn.execute(
                    """
                    DELETE FROM news_snapshot_history
                    WHERE target_id = ? AND id NOT IN (
                        SELECT id FROM news_snapshot_history
                        WHERE target_id = ? ORDER BY id DESC LIMIT 100
                    ) AND id NOT IN (
                        SELECT MAX(id) FROM news_snapshot_history
                        WHERE target_id = ? GROUP BY source_key
                    )
                    """,
                    (target_id, target_id, target_id),
                )
        return int(history_cursor.lastrowid), snapshot_ids

    async def add_sent_history_with_news_snapshots(
        self,
        history: dict,
        snapshots: list[dict],
    ) -> tuple[int, list[int]]:
        return await self._execute(
            self._sync_add_sent_history_with_news_snapshots,
            history,
            snapshots,
        )

    async def add_sent_history_with_news_snapshot(
        self,
        history: dict,
        snapshot: dict,
    ) -> tuple[int, int]:
        snapshot_record = {
            **snapshot,
            "target_id": str(
                snapshot.get("target_id") or history.get("target_id") or ""
            ),
        }
        history_id, snapshot_ids = await self.add_sent_history_with_news_snapshots(
            history,
            [snapshot_record],
        )
        return history_id, snapshot_ids[0]

    async def _execute(self, func, *args, **kwargs):
        if self._closed:
            raise RuntimeError("每日分享数据库已经关闭")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, func, *args, **kwargs)

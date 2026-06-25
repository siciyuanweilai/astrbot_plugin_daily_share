import asyncio
import sqlite3
from pathlib import Path

from .database.metrics import DatabaseDashboardMixin
from .database.records import DatabaseHistoryMixin
from .database.state import DatabaseStateMixin
from .database.topics import DatabaseTopicMixin


_DB_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_sent_history_target_success_id ON sent_history(target_id, success, id)",
    "CREATE INDEX IF NOT EXISTS idx_sent_history_success_id ON sent_history(success, id)",
    "CREATE INDEX IF NOT EXISTS idx_sent_history_success_created_at ON sent_history(success, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_sent_history_type_created_at ON sent_history(share_type, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_sent_history_target_created_at ON sent_history(target_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_sent_history_media_path ON sent_history(media_path)",
    "CREATE INDEX IF NOT EXISTS idx_topic_history_target_category_created_at ON topic_history(target_id, category, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_topic_history_created_at ON topic_history(created_at)",
)


class DatabaseManager(
    DatabaseStateMixin,
    DatabaseHistoryMixin,
    DatabaseDashboardMixin,
    DatabaseTopicMixin,
):
    """聚合数据库连接、建表和各类数据访问能力。"""

    def __init__(self, data_dir: Path):
        self.db_path = data_dir / "daily_share.db"
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sent_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT,
                share_type TEXT,
                content TEXT,
                success INTEGER,
                error_reason TEXT,
                media_type TEXT,
                media_url TEXT,
                media_path TEXT,
                source_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS topic_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT,
                category TEXT,
                content_key TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS plugin_state (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        for sql in _DB_INDEXES:
            cursor.execute(sql)

        conn.commit()
        conn.close()

    async def _execute(self, func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, func, *args, **kwargs)

from __future__ import annotations

from .keys import HISTORY_SHARE_BRIEFING

CURRENT_SCHEMA_VERSION = 2

TABLE_STATEMENTS = (
    """
    CREATE TABLE sent_history (
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        degraded INTEGER NOT NULL DEFAULT 0,
        degradation_reason TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE topic_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_id TEXT,
        category TEXT,
        content_key TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE plugin_state (
        domain TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (domain, key)
    )
    """,
    """
    CREATE TABLE news_snapshot_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_id TEXT NOT NULL,
        source_key TEXT NOT NULL,
        source_name TEXT,
        image_url TEXT,
        items TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
)

INDEX_STATEMENTS = (
    "CREATE INDEX idx_sent_history_target_success_id ON sent_history(target_id, success, id)",
    "CREATE INDEX idx_sent_history_success_id ON sent_history(success, id)",
    "CREATE INDEX idx_sent_history_success_created_at ON sent_history(success, created_at)",
    "CREATE INDEX idx_sent_history_type_created_at ON sent_history(share_type, created_at)",
    "CREATE INDEX idx_sent_history_target_created_at ON sent_history(target_id, created_at)",
    "CREATE INDEX idx_sent_history_media_path ON sent_history(media_path)",
    "CREATE INDEX idx_topic_history_target_category_created_at ON topic_history(target_id, category, created_at)",
    "CREATE INDEX idx_topic_history_created_at ON topic_history(created_at)",
    "CREATE INDEX idx_news_snapshot_target_id ON news_snapshot_history(target_id, id)",
    "CREATE INDEX idx_news_snapshot_target_source_id ON news_snapshot_history(target_id, source_key, id)",
    "CREATE INDEX idx_plugin_state_updated_at ON plugin_state(updated_at)",
)

CURRENT_TABLE_COLUMNS = {
    "sent_history": (
        "id",
        "target_id",
        "share_type",
        "content",
        "success",
        "error_reason",
        "media_type",
        "media_url",
        "media_path",
        "source_type",
        "created_at",
        "degraded",
        "degradation_reason",
    ),
    "topic_history": (
        "id",
        "target_id",
        "category",
        "content_key",
        "created_at",
    ),
    "plugin_state": ("domain", "key", "value", "updated_at"),
    "news_snapshot_history": (
        "id",
        "target_id",
        "source_key",
        "source_name",
        "image_url",
        "items",
        "created_at",
    ),
}
CURRENT_INDEX_NAMES = tuple(
    statement.split(" ", 3)[2] for statement in INDEX_STATEMENTS
)

_DYNAMIC_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif")
_DYNAMIC_VIDEO_EXTS = (".mp4", ".webm", ".mov", ".m4v", ".avi", ".mkv")
_HISTORY_SELECT_COLUMNS = """
    id, created_at, target_id, share_type, content, success,
    error_reason, media_type, media_url, media_path, source_type,
    degraded, degradation_reason
"""
_MEDIA_REF_SQL = "LOWER(COALESCE(media_path, '') || ' ' || COALESCE(media_url, ''))"
_HAS_MEDIA_SQL = "(COALESCE(media_path, '') <> '' OR COALESCE(media_url, '') <> '')"
_BRIEFING_HISTORY_SQL = f"COALESCE(share_type, '') = '{HISTORY_SHARE_BRIEFING}'"

STATE_DOMAINS = ("share", "qzone", "context", "cache")

__all__ = [name for name in globals() if not name.startswith("__")]

import importlib.util
import asyncio
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "core" / "db.py"
PACKAGE_NAME = "dashboard_db_testpkg"
CORE_PACKAGE_NAME = f"{PACKAGE_NAME}.core"
DB_MODULE_NAME = f"{CORE_PACKAGE_NAME}.db"


class _Logger:
    def debug(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None


def _install_stub_module(name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _load_db_module():
    for name in list(sys.modules):
        if name.startswith(PACKAGE_NAME) or name in {"astrbot", "astrbot.api"}:
            sys.modules.pop(name, None)
    _install_stub_module("astrbot")
    _install_stub_module("astrbot.api", logger=_Logger())

    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(ROOT)]
    sys.modules[PACKAGE_NAME] = package

    core_package = types.ModuleType(CORE_PACKAGE_NAME)
    core_package.__path__ = [str(ROOT / "core")]
    sys.modules[CORE_PACKAGE_NAME] = core_package

    spec = importlib.util.spec_from_file_location(DB_MODULE_NAME, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class DashboardDbMetricsTests(unittest.IsolatedAsyncioTestCase):
    async def test_deferred_database_initialization_creates_schema_asynchronously(self):
        mod = _load_db_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "nested" / "plugin-data"
            db = mod.DatabaseManager(data_dir, initialize=False)
            self.assertFalse(db.db_path.exists())

            await db.initialize()

            self.assertTrue(db.db_path.exists())
            self.assertTrue(db._initialized)

    async def test_concurrent_state_updates_are_atomic(self):
        mod = _load_db_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = mod.DatabaseManager(Path(tmp))
            await asyncio.gather(
                *(
                    db.update_share_state("shared", {f"field_{index}": index})
                    for index in range(24)
                )
            )

            state = await db.get_share_state("shared", {})
            self.assertEqual(state, {f"field_{index}": index for index in range(24)})

    async def test_database_close_is_concurrent_safe_and_rejects_new_work(self):
        mod = _load_db_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = mod.DatabaseManager(Path(tmp))

            await asyncio.gather(db.close(), db.close())

            self.assertTrue(db._closed)
            with self.assertRaisesRegex(RuntimeError, "数据库已经关闭"):
                await db.get_share_state("global")

    async def test_database_uses_only_the_default_file_name(self):
        mod = _load_db_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = mod.DatabaseManager(Path(tmp))

            self.assertEqual(db.db_path.name, "daily_share.db")
            self.assertEqual(
                await asyncio.to_thread(
                    lambda: sorted(path.name for path in Path(tmp).glob("*.db"))
                ),
                ["daily_share.db"],
            )
            conn = sqlite3.connect(db.db_path)
            try:
                self.assertEqual(
                    conn.execute("PRAGMA user_version").fetchone()[0],
                    1,
                )
            finally:
                conn.close()

    async def test_unversioned_current_database_is_adopted_without_data_loss(self):
        mod = _load_db_module()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            first = mod.DatabaseManager(data_dir)
            await first.set_share_state("global", {"kept": True})
            await first.close()
            conn = sqlite3.connect(first.db_path)
            try:
                conn.execute("PRAGMA user_version = 0")
                conn.commit()
            finally:
                conn.close()

            reopened = mod.DatabaseManager(data_dir)
            try:
                self.assertEqual(
                    await reopened.get_share_state("global"), {"kept": True}
                )
                conn = sqlite3.connect(reopened.db_path)
                try:
                    self.assertEqual(
                        conn.execute("PRAGMA user_version").fetchone()[0], 1
                    )
                finally:
                    conn.close()
                self.assertFalse(reopened.backup_path.exists())
            finally:
                await reopened.close()

    async def test_database_rejects_newer_schema_version(self):
        mod = _load_db_module()
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "daily_share.db"
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("PRAGMA user_version = 99")
                conn.commit()
            finally:
                conn.close()

            db = mod.DatabaseManager(Path(tmp), initialize=False)
            try:
                with self.assertRaisesRegex(RuntimeError, "高于插件支持的版本"):
                    await db.initialize()
            finally:
                await db.close()

    async def test_versioned_migration_backs_up_and_preserves_data(self):
        mod = _load_db_module()
        migration_module = sys.modules[f"{CORE_PACKAGE_NAME}.database.migrations"]
        schema_module = sys.modules[f"{CORE_PACKAGE_NAME}.database.dbschema"]
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            first = mod.DatabaseManager(data_dir)
            await first.set_share_state("global", {"kept": True})
            await first.close()

            columns = dict(schema_module.CURRENT_TABLE_COLUMNS)
            columns["plugin_state"] = (*columns["plugin_state"], "marker")
            migration = migration_module.SchemaMigration(
                version=2,
                statements=("ALTER TABLE plugin_state ADD COLUMN marker TEXT",),
            )
            with (
                mock.patch.object(schema_module, "CURRENT_SCHEMA_VERSION", 2),
                mock.patch.object(schema_module, "CURRENT_TABLE_COLUMNS", columns),
                mock.patch.object(migration_module, "SCHEMA_MIGRATIONS", (migration,)),
            ):
                upgraded = mod.DatabaseManager(data_dir)
                try:
                    self.assertEqual(
                        await upgraded.get_share_state("global"), {"kept": True}
                    )
                    conn = sqlite3.connect(upgraded.db_path)
                    try:
                        self.assertEqual(
                            conn.execute("PRAGMA user_version").fetchone()[0], 2
                        )
                        column_names = {
                            row[1]
                            for row in conn.execute(
                                "PRAGMA table_info(plugin_state)"
                            ).fetchall()
                        }
                    finally:
                        conn.close()
                    self.assertIn("marker", column_names)
                    self.assertTrue(upgraded.backup_path.exists())
                    backup = sqlite3.connect(upgraded.backup_path)
                    try:
                        self.assertEqual(
                            backup.execute("PRAGMA user_version").fetchone()[0], 1
                        )
                    finally:
                        backup.close()
                finally:
                    await upgraded.close()

    async def test_failed_migration_rolls_back_and_keeps_backup(self):
        mod = _load_db_module()
        migration_module = sys.modules[f"{CORE_PACKAGE_NAME}.database.migrations"]
        schema_module = sys.modules[f"{CORE_PACKAGE_NAME}.database.dbschema"]
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            first = mod.DatabaseManager(data_dir)
            await first.set_share_state("global", {"kept": True})
            await first.close()

            columns = dict(schema_module.CURRENT_TABLE_COLUMNS)
            columns["plugin_state"] = (*columns["plugin_state"], "transient")
            migration = migration_module.SchemaMigration(
                version=2,
                statements=(
                    "ALTER TABLE plugin_state ADD COLUMN transient TEXT",
                    "INSERT INTO missing_table(value) VALUES (1)",
                ),
            )
            with (
                mock.patch.object(schema_module, "CURRENT_SCHEMA_VERSION", 2),
                mock.patch.object(schema_module, "CURRENT_TABLE_COLUMNS", columns),
                mock.patch.object(migration_module, "SCHEMA_MIGRATIONS", (migration,)),
            ):
                failed = mod.DatabaseManager(data_dir, initialize=False)
                try:
                    with self.assertRaisesRegex(RuntimeError, "数据库迁移失败"):
                        await failed.initialize()
                finally:
                    await failed.close()

            conn = sqlite3.connect(data_dir / "daily_share.db")
            try:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 1)
                column_names = {
                    row[1]
                    for row in conn.execute(
                        "PRAGMA table_info(plugin_state)"
                    ).fetchall()
                }
                value = conn.execute(
                    "SELECT value FROM plugin_state WHERE domain = 'share' AND key = 'global'"
                ).fetchone()[0]
            finally:
                conn.close()
            self.assertNotIn("transient", column_names)
            self.assertIn('"kept": true', value)
            self.assertTrue((data_dir / "daily_share.backup.db").exists())

    async def test_database_indexes_are_created(self):
        mod = _load_db_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = mod.DatabaseManager(Path(tmp))
            conn = sqlite3.connect(db.db_path)
            try:
                indexes = set()
                for table in (
                    "sent_history",
                    "topic_history",
                    "news_snapshot_history",
                    "plugin_state",
                ):
                    rows = conn.execute(f"PRAGMA index_list({table})").fetchall()
                    indexes.update(str(row[1]) for row in rows)
            finally:
                conn.close()

            self.assertTrue(
                {
                    "idx_sent_history_target_success_id",
                    "idx_sent_history_success_id",
                    "idx_sent_history_success_created_at",
                    "idx_sent_history_type_created_at",
                    "idx_sent_history_target_created_at",
                    "idx_sent_history_media_path",
                    "idx_topic_history_target_category_created_at",
                    "idx_topic_history_created_at",
                    "idx_news_snapshot_target_id",
                    "idx_news_snapshot_target_source_id",
                    "idx_plugin_state_updated_at",
                }.issubset(indexes)
            )

    async def test_state_is_partitioned_by_domain(self):
        mod = _load_db_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = mod.DatabaseManager(Path(tmp))
            await db.set_share_state("global", {"kind": "scheduler"})
            await db.set_qzone_state("qzone_auto_comment", {"kind": "qzone"})
            await db.set_context_state("qzone_context:session", {"kind": "context"})
            await db.set_cache_state("news_short_url_cache", {"kind": "cache"})

            conn = sqlite3.connect(db.db_path)
            try:
                rows = conn.execute(
                    "SELECT domain, key FROM plugin_state ORDER BY domain, key"
                ).fetchall()
            finally:
                conn.close()

            self.assertEqual(
                rows,
                [
                    ("cache", "news_short_url_cache"),
                    ("context", "qzone_context:session"),
                    ("qzone", "qzone_auto_comment"),
                    ("share", "global"),
                ],
            )

    async def test_fresh_schema_has_no_compatibility_tables_or_state_api(self):
        mod = _load_db_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = mod.DatabaseManager(Path(tmp))
            conn = sqlite3.connect(db.db_path)
            try:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                    if row[0] != "sqlite_sequence"
                }
            finally:
                conn.close()

            self.assertEqual(
                tables,
                {
                    "sent_history",
                    "topic_history",
                    "news_snapshot_history",
                    "plugin_state",
                },
            )
            for method_name in ("get_state", "set_state", "update_state_dict"):
                self.assertFalse(hasattr(db, method_name), method_name)

    async def test_news_snapshot_history_returns_latest_any_and_latest_source(self):
        mod = _load_db_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = mod.DatabaseManager(Path(tmp))
            await db.add_news_snapshot(
                "group-1", "weibo", "微博热搜", "weibo-09.png", [{"title": "微博09"}]
            )
            await db.add_news_snapshot(
                "group-1", "douyin", "抖音热榜", "douyin-10.png", [{"title": "抖音10"}]
            )
            await db.add_news_snapshot(
                "group-1", "weibo", "微博热搜", "weibo-11.png", [{"title": "微博11"}]
            )

            latest = await db.get_latest_news_snapshot("group-1")
            douyin = await db.get_latest_news_snapshot("group-1", "douyin")
            weibo = await db.get_latest_news_snapshot("group-1", "weibo")

            self.assertEqual(latest["items"][0]["title"], "微博11")
            self.assertEqual(douyin["items"][0]["title"], "抖音10")
            self.assertEqual(weibo["items"][0]["title"], "微博11")

    async def test_sent_history_and_news_snapshot_share_one_transaction(self):
        mod = _load_db_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = mod.DatabaseManager(Path(tmp))
            history = {
                "target_id": "group-1",
                "share_type": "news",
                "content": "微博热搜长图",
                "source_type": "scheduled",
                "media_type": "image",
                "media_url": "https://example.invalid/weibo.png",
            }
            snapshot = {
                "source_key": "weibo",
                "source_name": "微博热搜",
                "image_url": "https://example.invalid/weibo.png",
                "items": [{"title": "测试新闻", "url": "https://example.invalid/1"}],
            }

            history_id, snapshot_id = await db.add_sent_history_with_news_snapshot(
                history, snapshot
            )

            self.assertGreater(history_id, 0)
            self.assertGreater(snapshot_id, 0)
            conn = sqlite3.connect(db.db_path)
            try:
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM sent_history").fetchone()[0], 1
                )
                self.assertEqual(
                    conn.execute(
                        "SELECT COUNT(*) FROM news_snapshot_history"
                    ).fetchone()[0],
                    1,
                )
            finally:
                conn.close()

    async def test_sent_history_and_multiple_news_snapshots_share_one_transaction(self):
        mod = _load_db_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = mod.DatabaseManager(Path(tmp))
            history = {
                "target_id": "qzone",
                "share_type": "news",
                "content": "新闻长图",
                "source_type": "manual",
            }
            snapshots = [
                {
                    "target_id": target,
                    "source_key": "weibo",
                    "source_name": "微博热搜",
                    "image_url": "https://example.invalid/weibo.png",
                    "items": [
                        {"title": "测试新闻", "url": "https://example.invalid/1"}
                    ],
                }
                for target in ("qzone", "session-1")
            ]

            history_id, snapshot_ids = await db.add_sent_history_with_news_snapshots(
                history, snapshots
            )

            self.assertGreater(history_id, 0)
            self.assertEqual(len(snapshot_ids), 2)
            self.assertIsNotNone(await db.get_latest_news_snapshot("qzone", "weibo"))
            self.assertIsNotNone(
                await db.get_latest_news_snapshot("session-1", "weibo")
            )

    async def test_multiple_news_snapshot_failure_rolls_back_history(self):
        mod = _load_db_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = mod.DatabaseManager(Path(tmp))
            history = {
                "target_id": "qzone",
                "share_type": "news",
                "content": "新闻长图",
                "source_type": "manual",
            }
            snapshots = [
                {
                    "target_id": "qzone",
                    "source_key": "weibo",
                    "items": [{"title": "测试新闻"}],
                },
                {
                    "target_id": "session-1",
                    "source_key": "weibo",
                    "items": [object()],
                },
            ]

            with self.assertRaises(TypeError):
                await db.add_sent_history_with_news_snapshots(history, snapshots)

            conn = sqlite3.connect(db.db_path)
            try:
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM sent_history").fetchone()[0], 0
                )
                self.assertEqual(
                    conn.execute(
                        "SELECT COUNT(*) FROM news_snapshot_history"
                    ).fetchone()[0],
                    0,
                )
            finally:
                conn.close()

    async def test_news_snapshot_cleanup_keeps_latest_record_for_each_source(self):
        mod = _load_db_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = mod.DatabaseManager(Path(tmp))
            await db.add_news_snapshot(
                "group-1",
                "douyin",
                "抖音热榜",
                "douyin.png",
                [{"title": "抖音保底快照"}],
            )
            for index in range(100):
                await db.add_news_snapshot(
                    "group-1",
                    "weibo",
                    "微博热搜",
                    f"weibo-{index}.png",
                    [{"title": f"微博{index}"}],
                )

            douyin = await db.get_latest_news_snapshot("group-1", "douyin")
            weibo = await db.get_latest_news_snapshot("group-1", "weibo")

            self.assertEqual(douyin["items"][0]["title"], "抖音保底快照")
            self.assertEqual(weibo["items"][0]["title"], "微博99")

    async def test_retention_cleans_transient_state_and_preserves_domain_state(self):
        mod = _load_db_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = mod.DatabaseManager(Path(tmp))
            await db.set_share_state("global", {"enabled": True})
            await db.set_qzone_state("qzone", {"enabled": True})
            await db.set_context_state("session", {"items": [1]})
            await db.set_cache_state("focus", {"index": 1})
            await db.add_news_snapshot(
                "group-1", "weibo", "微博热搜", "old-1.png", [{"title": "旧快照"}]
            )
            await db.add_news_snapshot(
                "group-1", "weibo", "微博热搜", "old-2.png", [{"title": "最新快照"}]
            )

            old_time = (datetime.now() - timedelta(days=10)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            conn = sqlite3.connect(db.db_path)
            try:
                conn.execute(
                    "UPDATE plugin_state SET updated_at = ?",
                    (old_time,),
                )
                conn.execute(
                    "UPDATE news_snapshot_history SET created_at = ?", (old_time,)
                )
                conn.commit()
            finally:
                conn.close()

            deleted = await db.clean_expired_data(days_limit=1)

            self.assertEqual(await db.get_share_state("global"), {"enabled": True})
            self.assertEqual(await db.get_qzone_state("qzone"), {"enabled": True})
            self.assertIsNone(await db.get_context_state("session"))
            self.assertIsNone(await db.get_cache_state("focus"))
            latest = await db.get_latest_news_snapshot("group-1", "weibo")
            self.assertEqual(latest["items"][0]["title"], "最新快照")
            self.assertEqual(deleted["news_snapshot_history"], 1)
            self.assertEqual(deleted["plugin_state"], 2)

    async def test_history_metadata_failures_media_and_stats(self):
        mod = _load_db_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = mod.DatabaseManager(Path(tmp))

            await db.add_sent_history(
                "group-1",
                "news",
                "sent with image",
                True,
                media_type="image",
                media_path="D:/tmp/news.png",
            )
            await db.add_sent_history(
                "group-1",
                "mood",
                "text only dynamic",
                True,
            )
            await db.add_sent_history(
                "group-1",
                "news",
                "failed",
                False,
                error_reason="upload failed",
            )

            recent = await db.get_recent_history(limit=5)
            failures = await db.get_recent_failures(limit=5)
            media = await db.get_recent_media(limit=5)
            dynamics = await db.get_recent_dynamics(limit=5)
            stats = await db.get_target_stats(days=30)
            summary = await db.get_history_summary()

            self.assertEqual(recent[0]["error_reason"], "upload failed")
            self.assertEqual(failures[0]["target_id"], "group-1")
            self.assertEqual(failures[0]["error_reason"], "upload failed")
            self.assertEqual(media[0]["media_type"], "image")
            self.assertEqual(media[0]["media_path"], "D:/tmp/news.png")
            self.assertEqual(
                [item["content"] for item in dynamics],
                ["text only dynamic", "sent with image"],
            )
            self.assertEqual(stats[0]["target_id"], "group-1")
            self.assertEqual(stats[0]["total"], 3)
            self.assertEqual(stats[0]["success"], 2)
            self.assertEqual(stats[0]["failed"], 1)
            self.assertEqual(summary["total"], 3)
            self.assertEqual(summary["success"], 2)
            self.assertEqual(summary["failed"], 1)
            self.assertEqual(summary["today"], 2)
            self.assertEqual(summary["dynamic"], 2)
            self.assertEqual(summary["media"], 1)

            deleted = await db.clear_failures()
            recent_after_clear = await db.get_recent_history(limit=5)
            failures_after_clear = await db.get_recent_failures(limit=5)
            summary_after_clear = await db.get_history_summary()

            self.assertEqual(deleted, 1)
            self.assertEqual(failures_after_clear, [])
            self.assertEqual(len(recent_after_clear), 2)
            self.assertTrue(recent_after_clear[0]["success"])
            self.assertEqual(summary_after_clear["total"], 2)
            self.assertEqual(summary_after_clear["failed"], 0)
            self.assertEqual(summary_after_clear["today"], 2)

    async def test_retention_cleans_history_while_dashboard_days_filter_display(self):
        mod = _load_db_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = mod.DatabaseManager(Path(tmp))

            await db.add_sent_history(
                "group-1",
                "mood",
                "new dynamic",
                True,
            )
            await db.add_sent_history(
                "group-1",
                "news",
                "old dynamic with image",
                True,
                media_type="image",
                media_path="D:/tmp/old-news.png",
            )
            await db.record_topic("group-1", "news", "old-topic")

            old_time = (datetime.now() - timedelta(days=10)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            conn = sqlite3.connect(db.db_path)
            conn.execute(
                "UPDATE sent_history SET created_at = ? WHERE content = ?",
                (old_time, "old dynamic with image"),
            )
            conn.execute(
                "UPDATE topic_history SET created_at = ? WHERE content_key = ?",
                (old_time, "old-topic"),
            )
            conn.commit()
            conn.close()

            visible_dynamics = await db.get_recent_dynamics(limit=5, days=1)
            all_dynamics = await db.get_recent_dynamics(limit=5, days=0)
            visible_summary = await db.get_dashboard_dynamic_summary(days=1)

            self.assertEqual(
                [item["content"] for item in visible_dynamics], ["new dynamic"]
            )
            self.assertEqual(
                {item["content"] for item in all_dynamics},
                {"new dynamic", "old dynamic with image"},
            )
            self.assertEqual(visible_summary["dynamic"], 1)
            self.assertEqual(visible_summary["text"], 1)
            self.assertEqual(visible_summary["media"], 0)
            self.assertEqual(visible_summary["image"], 0)
            self.assertEqual(visible_summary["video"], 0)

            await db.clean_expired_data(days_limit=1)
            history_after_cleanup = await db.get_recent_history(limit=5)
            used_topics_after_cleanup = await db.get_used_topics(
                "group-1", "news", days_limit=60
            )

            self.assertEqual(
                {item["content"] for item in history_after_cleanup},
                {"new dynamic"},
            )
            self.assertEqual(used_topics_after_cleanup, [])

    async def test_recent_dynamics_can_filter_today_from_midnight(self):
        mod = _load_db_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = mod.DatabaseManager(Path(tmp))

            await db.add_sent_history("group-1", "mood", "today text", True)
            await db.add_sent_history(
                "group-1",
                "news",
                "yesterday image",
                True,
                media_type="image",
                media_path="D:/tmp/yesterday.png",
            )

            yesterday = (datetime.now() - timedelta(days=1)).replace(
                hour=23, minute=0, second=0, microsecond=0
            )
            conn = sqlite3.connect(db.db_path)
            conn.execute(
                "UPDATE sent_history SET created_at = ? WHERE content = ?",
                (yesterday.strftime("%Y-%m-%d %H:%M:%S"), "yesterday image"),
            )
            conn.commit()
            conn.close()

            today_items = await db.get_recent_dynamics(limit=10, today_only=True)

            self.assertEqual([item["content"] for item in today_items], ["today text"])

    async def test_recent_dynamics_can_filter_media_kind_and_share_type(self):
        mod = _load_db_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = mod.DatabaseManager(Path(tmp))

            await db.add_sent_history(
                "group-1",
                "mood",
                "text mood",
                True,
            )
            await db.add_sent_history(
                "group-1",
                "news",
                "typed image news",
                True,
                media_type="image",
                media_path="D:/tmp/news.png",
            )
            await db.add_sent_history(
                "group-1",
                "greeting",
                "typed video greeting",
                True,
                media_type="video",
                media_url="https://example.com/hello.mp4",
            )
            await db.add_sent_history(
                "group-1",
                "recommendation",
                "typed extension image",
                True,
                media_type="image",
                media_path="D:/tmp/poster.WEBP",
            )
            await db.add_sent_history(
                "group-1",
                "news",
                "failed image",
                False,
                media_type="image",
                media_path="D:/tmp/failed.png",
            )

            text_items = await db.get_recent_dynamics(limit=10, media_kind="text")
            image_items = await db.get_recent_dynamics(limit=10, media_kind="image")
            video_items = await db.get_recent_dynamics(limit=10, media_kind="video")
            news_images = await db.get_recent_dynamics(
                limit=10,
                media_kind="image",
                share_type="news",
            )

            self.assertEqual([item["content"] for item in text_items], ["text mood"])
            self.assertEqual(
                [item["content"] for item in image_items],
                ["typed extension image", "typed image news"],
            )
            self.assertEqual(
                [item["content"] for item in video_items], ["typed video greeting"]
            )
            self.assertEqual(
                [item["content"] for item in news_images], ["typed image news"]
            )

            summary = await db.get_dashboard_dynamic_summary(days=0)
            self.assertEqual(summary["text"], 1)
            self.assertEqual(summary["image"], 2)
            self.assertEqual(summary["video"], 1)

    async def test_target_stats_use_share_type_to_separate_briefing(self):
        mod = _load_db_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = mod.DatabaseManager(Path(tmp))

            await db.add_sent_history("group-1", "news", "normal news", True)
            await db.add_sent_history("group-1", "mood", "normal mood", True)
            await db.add_sent_history(
                "group-1",
                "news",
                "normal news failed",
                False,
                error_reason="send failed",
            )
            await db.add_sent_history(
                "group-1", "briefing", "【每天60秒读懂世界】早报", True
            )
            await db.add_sent_history("group-1", "news", "manual news", True)
            await db.add_sent_history(
                "group-1",
                "briefing",
                "AI 资讯早报发送失败",
                False,
                error_reason="briefing failed",
            )

            regular_stats = await db.get_target_stats(days=30, briefing=False)
            briefing_stats = await db.get_target_stats(days=30, briefing=True)
            merged_stats = await db.get_target_stats(days=30)
            news_dynamics = await db.get_recent_dynamics(limit=10, share_type="news")
            briefing_dynamics = await db.get_recent_dynamics(
                limit=10, share_type="briefing"
            )

            regular = next(
                item for item in regular_stats if item["target_id"] == "group-1"
            )
            briefing = next(
                item for item in briefing_stats if item["target_id"] == "group-1"
            )
            merged = next(
                item for item in merged_stats if item["target_id"] == "group-1"
            )

            self.assertEqual(regular["total"], 4)
            self.assertEqual(regular["success"], 3)
            self.assertEqual(regular["failed"], 1)
            self.assertEqual(regular["types"], {"mood": 1, "news": 2})

            self.assertEqual(briefing["total"], 2)
            self.assertEqual(briefing["success"], 1)
            self.assertEqual(briefing["failed"], 1)
            self.assertEqual(briefing["types"], {"briefing": 1})

            self.assertEqual(merged["total"], 6)
            self.assertEqual(merged["success"], 4)
            self.assertEqual(merged["failed"], 2)

            self.assertEqual(
                [item["content"] for item in news_dynamics],
                ["manual news", "normal news"],
            )
            self.assertEqual(
                [item["content"] for item in briefing_dynamics],
                ["【每天60秒读懂世界】早报"],
            )


if __name__ == "__main__":
    unittest.main()

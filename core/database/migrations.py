from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from . import dbschema as schema


class DatabaseMigrationError(RuntimeError):
    """数据库结构无法安全升级。"""


@dataclass(frozen=True, slots=True)
class SchemaMigration:
    """将数据库从前一版本升级到指定版本。"""

    version: int
    statements: tuple[str, ...] = ()
    transform: Callable[[sqlite3.Connection], None] | None = None

    def apply(self, conn: sqlite3.Connection) -> None:
        for statement in self.statements:
            conn.execute(statement)
        if self.transform is not None:
            self.transform(conn)


SCHEMA_MIGRATIONS: tuple[SchemaMigration, ...] = (
    SchemaMigration(
        version=2,
        statements=(
            "ALTER TABLE sent_history ADD COLUMN degraded INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE sent_history ADD COLUMN degradation_reason TEXT NOT NULL DEFAULT ''",
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class SchemaInitializationResult:
    previous_version: int
    current_version: int
    created: bool = False
    adopted_baseline: bool = False
    migrated: bool = False


def read_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0] or 0) if row else 0


def _user_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()
    return {str(row[0]) for row in rows}


def _table_columns(conn: sqlite3.Connection, table_name: str) -> tuple[str, ...]:
    escaped = table_name.replace('"', '""')
    rows = conn.execute(f'PRAGMA table_info("{escaped}")').fetchall()
    return tuple(str(row[1]) for row in rows)


def _index_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type = 'index' AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()
    return {str(row[0]) for row in rows}


def _validate_tables(
    conn: sqlite3.Connection,
    expected_columns: Mapping[str, Sequence[str]],
) -> None:
    expected_tables = set(expected_columns)
    actual_tables = _user_tables(conn)
    missing_tables = sorted(expected_tables - actual_tables)
    unexpected_tables = sorted(actual_tables - expected_tables)
    if missing_tables or unexpected_tables:
        details = []
        if missing_tables:
            details.append(f"缺少表: {', '.join(missing_tables)}")
        if unexpected_tables:
            details.append(f"存在未知表: {', '.join(unexpected_tables)}")
        raise DatabaseMigrationError("数据库结构不属于当前版本；" + "；".join(details))

    for table_name, expected in expected_columns.items():
        actual = _table_columns(conn, table_name)
        expected_names = tuple(str(column) for column in expected)
        if set(actual) != set(expected_names) or len(actual) != len(expected_names):
            raise DatabaseMigrationError(
                f"数据表 {table_name} 字段不匹配；"
                f"期望 {', '.join(sorted(expected_names))}；"
                f"实际 {', '.join(sorted(actual)) or '空'}"
            )


def validate_current_schema(conn: sqlite3.Connection) -> None:
    _validate_tables(conn, schema.CURRENT_TABLE_COLUMNS)
    missing_indexes = sorted(set(schema.CURRENT_INDEX_NAMES) - _index_names(conn))
    if missing_indexes:
        raise DatabaseMigrationError(f"数据库缺少索引: {', '.join(missing_indexes)}")


def schema_requires_backup(conn: sqlite3.Connection) -> bool:
    version = read_schema_version(conn)
    if version > schema.CURRENT_SCHEMA_VERSION:
        return False
    if 0 < version < schema.CURRENT_SCHEMA_VERSION:
        return True
    if not (
        version == 0
        and _user_tables(conn)
        and schema.CURRENT_SCHEMA_VERSION > schema.BASELINE_SCHEMA_VERSION
    ):
        return False
    try:
        _validate_tables(conn, schema.CURRENT_TABLE_COLUMNS)
        return False
    except DatabaseMigrationError:
        return True


def _create_current_schema(conn: sqlite3.Connection) -> None:
    for statement in schema.TABLE_STATEMENTS:
        conn.execute(statement)
    for statement in schema.INDEX_STATEMENTS:
        conn.execute(statement)


def _migration_map() -> dict[int, SchemaMigration]:
    result: dict[int, SchemaMigration] = {}
    for migration in SCHEMA_MIGRATIONS:
        version = int(migration.version)
        if version in result:
            raise DatabaseMigrationError(f"数据库迁移版本重复: {version}")
        result[version] = migration
    return result


def initialize_schema(conn: sqlite3.Connection) -> SchemaInitializationResult:
    previous_version = read_schema_version(conn)
    target_version = schema.CURRENT_SCHEMA_VERSION
    if previous_version > target_version:
        raise DatabaseMigrationError(
            f"数据库版本 {previous_version} 高于插件支持的版本 {target_version}，"
            "请升级插件后再启动"
        )

    tables = _user_tables(conn)
    created = previous_version == 0 and not tables
    adopted_baseline = previous_version == 0 and bool(tables)
    migrated = False

    conn.execute("BEGIN IMMEDIATE")
    try:
        current_version = previous_version
        if created:
            _create_current_schema(conn)
            current_version = target_version
            conn.execute(f"PRAGMA user_version = {target_version}")
        elif adopted_baseline:
            try:
                _validate_tables(conn, schema.CURRENT_TABLE_COLUMNS)
                current_version = target_version
            except DatabaseMigrationError:
                _validate_tables(conn, schema.BASELINE_TABLE_COLUMNS)
                current_version = schema.BASELINE_SCHEMA_VERSION
            conn.execute(f"PRAGMA user_version = {current_version}")

        migrations = _migration_map()
        while current_version < target_version:
            next_version = current_version + 1
            migration = migrations.get(next_version)
            if migration is None:
                raise DatabaseMigrationError(
                    f"缺少数据库迁移步骤: {current_version} -> {next_version}"
                )
            migration.apply(conn)
            current_version = next_version
            conn.execute(f"PRAGMA user_version = {current_version}")
            migrated = True

        if not created:
            for statement in schema.INDEX_STATEMENTS:
                conn.execute(
                    statement.replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ", 1)
                )
        validate_current_schema(conn)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        if isinstance(exc, DatabaseMigrationError):
            raise
        raise DatabaseMigrationError(f"数据库迁移失败: {exc}") from exc

    return SchemaInitializationResult(
        previous_version=previous_version,
        current_version=target_version,
        created=created,
        adopted_baseline=adopted_baseline,
        migrated=migrated,
    )


__all__ = [
    "DatabaseMigrationError",
    "SCHEMA_MIGRATIONS",
    "SchemaInitializationResult",
    "SchemaMigration",
    "initialize_schema",
    "read_schema_version",
    "schema_requires_backup",
    "validate_current_schema",
]

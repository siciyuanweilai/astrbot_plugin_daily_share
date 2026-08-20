from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from . import dbschema as schema


class DatabaseSchemaError(RuntimeError):
    """数据库结构不是当前插件支持的版本。"""


@dataclass(frozen=True, slots=True)
class SchemaInitializationResult:
    previous_version: int
    current_version: int
    created: bool = False


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
        raise DatabaseSchemaError("数据库结构不属于当前版本；" + "；".join(details))

    for table_name, expected in expected_columns.items():
        actual = _table_columns(conn, table_name)
        expected_names = tuple(str(column) for column in expected)
        if set(actual) != set(expected_names) or len(actual) != len(expected_names):
            raise DatabaseSchemaError(
                f"数据表 {table_name} 字段不匹配；"
                f"期望 {', '.join(sorted(expected_names))}；"
                f"实际 {', '.join(sorted(actual)) or '空'}"
            )


def validate_current_schema(conn: sqlite3.Connection) -> None:
    _validate_tables(conn, schema.CURRENT_TABLE_COLUMNS)
    missing_indexes = sorted(set(schema.CURRENT_INDEX_NAMES) - _index_names(conn))
    if missing_indexes:
        raise DatabaseSchemaError(f"数据库缺少索引: {', '.join(missing_indexes)}")


def _create_current_schema(conn: sqlite3.Connection) -> None:
    for statement in schema.TABLE_STATEMENTS:
        conn.execute(statement)
    for statement in schema.INDEX_STATEMENTS:
        conn.execute(statement)


def initialize_schema(conn: sqlite3.Connection) -> SchemaInitializationResult:
    previous_version = read_schema_version(conn)
    target_version = schema.CURRENT_SCHEMA_VERSION
    tables = _user_tables(conn)
    created = previous_version == 0 and not tables

    if previous_version not in (0, target_version):
        raise DatabaseSchemaError(
            f"数据库结构版本 {previous_version} 不受当前插件支持；"
            f"当前仅支持全新数据库或结构版本 {target_version}，"
            "不会自动迁移旧数据"
        )
    if previous_version == 0 and tables:
        raise DatabaseSchemaError(
            f"数据库缺少结构版本标记且包含旧表；当前仅支持结构版本 {target_version}，"
            "不会自动迁移旧数据"
        )

    conn.execute("BEGIN IMMEDIATE")
    try:
        if created:
            _create_current_schema(conn)
            conn.execute(f"PRAGMA user_version = {target_version}")
        validate_current_schema(conn)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        if isinstance(exc, DatabaseSchemaError):
            raise
        raise DatabaseSchemaError(f"数据库结构初始化失败: {exc}") from exc

    return SchemaInitializationResult(
        previous_version=previous_version,
        current_version=target_version,
        created=created,
    )


__all__ = [
    "DatabaseSchemaError",
    "SchemaInitializationResult",
    "initialize_schema",
    "read_schema_version",
    "validate_current_schema",
]

from datetime import datetime, timedelta

from astrbot.api import logger

from .repository import DatabaseRepository


class DatabaseMaintenanceService(DatabaseRepository):
    """按数据用途清理过期记录，同时保留必要的最新状态。"""

    def _sync_clean_expired_data(self, days_limit: int) -> dict[str, int]:
        safe_days = max(1, int(days_limit))
        cutoff = (datetime.now() - timedelta(days=safe_days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        deleted: dict[str, int] = {}

        with self._connection(write=True) as conn:
            for table_name, time_column in (
                ("sent_history", "created_at"),
                ("topic_history", "created_at"),
            ):
                cursor = conn.execute(
                    f"DELETE FROM {table_name} WHERE {time_column} < ?",
                    (cutoff,),
                )
                deleted[table_name] = int(cursor.rowcount or 0)

            cursor = conn.execute(
                """
                DELETE FROM plugin_state
                WHERE domain IN ('context', 'cache') AND updated_at < ?
                """,
                (cutoff,),
            )
            deleted["plugin_state"] = int(cursor.rowcount or 0)

            cursor = conn.execute(
                """
                DELETE FROM news_snapshot_history
                WHERE created_at < ?
                  AND id NOT IN (
                      SELECT MAX(id)
                      FROM news_snapshot_history
                      GROUP BY target_id, source_key
                  )
                """,
                (cutoff,),
            )
            deleted["news_snapshot_history"] = int(cursor.rowcount or 0)

        total = sum(deleted.values())
        if total:
            logger.debug(
                f"[日常分享] 数据库过期清理完成：删除 {total} 条记录，保留天数 {safe_days} 天"
            )
        return deleted

    async def clean_expired_data(self, days_limit: int) -> dict[str, int]:
        return await self._execute(self._sync_clean_expired_data, days_limit)

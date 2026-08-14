from datetime import datetime, timedelta

from .repository import DatabaseRepository


class DatabaseTopicService(DatabaseRepository):
    """话题去重和过期清理。"""

    def _sync_record_topic(self, target_id, category, content_key):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._execute_write(
            """
            INSERT INTO topic_history (target_id, category, content_key, created_at)
            VALUES (?, ?, ?, ?)
        """,
            (str(target_id), str(category), str(content_key), now_str),
        )

    async def record_topic(self, target_id: str, category: str, content_key: str):
        await self._execute(self._sync_record_topic, target_id, category, content_key)

    def _sync_get_used_topics(self, target_id, category, days_limit=60) -> list[str]:
        date_limit = (datetime.now() - timedelta(days=days_limit)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        rows = self._fetch_all(
            """
            SELECT content_key FROM topic_history
            WHERE target_id = ? AND category = ? AND created_at > ?
        """,
            (str(target_id), str(category), date_limit),
        )
        return [r[0] for r in rows]

    async def get_used_topics(
        self, target_id: str, category: str, days_limit: int = 60
    ) -> list[str]:
        return await self._execute(
            self._sync_get_used_topics, target_id, category, days_limit
        )

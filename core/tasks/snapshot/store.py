from __future__ import annotations

from astrbot.api import logger

from ...config import NEWS_SOURCE_MAP
from .cleanse import TaskNewsCacheNormalizeService


class TaskNewsCacheStoreService(TaskNewsCacheNormalizeService):
    @staticmethod
    def news_snapshot_payload(items, source: str | None):
        return {
            "items": items if isinstance(items, list) else [],
            "source": source,
        }

    def prepare_news_snapshot_record(
        self,
        snapshot_data,
        image_url: str | None = None,
    ) -> dict | None:
        if not isinstance(snapshot_data, dict):
            return None
        source_key = str(
            snapshot_data.get("source") or snapshot_data.get("source_key") or ""
        ).strip()
        items = self._normalize_news_snapshot_items(snapshot_data.get("items"))
        if not source_key or not items:
            return None
        return {
            "source_key": source_key,
            "source_name": NEWS_SOURCE_MAP.get(source_key, {}).get("name")
            or "新闻热搜",
            "image_url": str(image_url or ""),
            "items": items,
        }

    async def commit_sent_news_snapshot(
        self,
        target_uid: str,
        snapshot_data=None,
        image_url: str | None = None,
    ) -> bool:
        """追加保存与成功发送新闻长图配对的结构化快照。"""
        try:
            target = str(target_uid or "").strip()
            if not target or not isinstance(snapshot_data, dict):
                return False

            record = self.prepare_news_snapshot_record(snapshot_data, image_url)
            if not record:
                return False

            snapshot = await self.db.add_news_snapshot(
                target,
                record["source_key"],
                record["source_name"],
                record["image_url"],
                record["items"],
            )
            logger.info(
                f"[日常分享] 已提交 {target} 的已发送新闻快照: "
                f"{record['source_name']} {len(record['items'])} 条 "
                f"(#{snapshot.get('snapshot_id')})"
            )
            return True
        except Exception as e:
            logger.warning(f"[日常分享] 提交已发送新闻快照失败: {e}")
            return False

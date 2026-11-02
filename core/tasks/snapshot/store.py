from __future__ import annotations

from typing import TYPE_CHECKING

from ...config import NEWS_SOURCE_MAP

if TYPE_CHECKING:
    from ..cache import TaskNewsCacheService


class TaskNewsCacheStoreService:
    def __init__(self, owner: TaskNewsCacheService) -> None:
        self.owner = owner

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
        items = self.owner._normalize_news_snapshot_items(snapshot_data.get("items"))
        if not source_key or not items:
            return None
        return {
            "source_key": source_key,
            "source_name": NEWS_SOURCE_MAP.get(source_key, {}).get("name")
            or "新闻热搜",
            "image_url": str(image_url or ""),
            "items": items,
        }

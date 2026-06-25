from __future__ import annotations

from datetime import datetime

from astrbot.api import logger

from ...config import NEWS_SOURCE_MAP


class TaskNewsCacheStoreMixin:
    async def cache_news_snapshot(self, target_uid: str, news_data=None, source_key: str = None, image_url: str = None) -> bool:
        """
        缓存一次新闻热搜 JSON 快照，用来把长图里的序号反查到原文链接。
        发送长图时传 source_key 会重新取同源 JSON；失败时不切到备用源，避免图文错位。
        """
        try:
            target = str(target_uid or "").strip()
            if not target:
                return False

            items, actual_source = self._extract_news_snapshot_source(news_data, source_key)
            items, actual_source = await self._complete_news_snapshot_items(items, actual_source)
            snapshot_items = self._normalize_news_snapshot_items(items)
            if not snapshot_items:
                return False

            source_name = NEWS_SOURCE_MAP.get(actual_source or "", {}).get("name") or "新闻热搜"
            snapshot = {
                "source_key": actual_source,
                "source_name": source_name,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "image_url": image_url or "",
                "items": snapshot_items,
            }

            await self.db.set_state(self._news_snapshot_key(target), snapshot)
            if actual_source:
                await self.db.set_state(self._news_snapshot_source_key(target, actual_source), snapshot)
            logger.info(f"[每日分享] 已缓存 {target} 的新闻快照: {source_name} {len(snapshot_items)} 条")
            return True
        except Exception as e:
            logger.warning(f"[每日分享] 缓存新闻快照失败: {e}")
            return False

    @staticmethod
    def _extract_news_snapshot_source(news_data, source_key: str = None) -> tuple[list | None, str | None]:
        items = None
        actual_source = source_key
        if news_data:
            if isinstance(news_data, tuple) and len(news_data) >= 2:
                items = news_data[0]
                actual_source = news_data[1] or actual_source
            elif isinstance(news_data, list):
                items = news_data
        return items, actual_source

    async def _complete_news_snapshot_items(self, items, actual_source: str | None) -> tuple[list | None, str | None]:
        snapshot_limit = self.get_news_snapshot_limit()
        item_count = len(items) if isinstance(items, list) else 0
        if actual_source and item_count < snapshot_limit:
            fetched = await self.news_service.get_hot_news(
                actual_source,
                limit=snapshot_limit,
                allow_fallback=False,
            )
            if fetched:
                fetched_items, fetched_source = fetched
                if isinstance(fetched_items, list) and len(fetched_items) > item_count:
                    items = fetched_items
                    actual_source = fetched_source or actual_source
        return items, actual_source

from __future__ import annotations

from datetime import datetime

from astrbot.api import logger

from ...config import NEWS_SOURCE_MAP


class TaskNewsCacheStoreMixin:
    @staticmethod
    def _news_snapshot_payload(items, source: str | None):
        return {
            "items": items if isinstance(items, list) else [],
            "source": source,
        }

    async def cache_news_snapshot(self, target_uid: str, snapshot_data=None, image_url: str = None) -> bool:
        """
        缓存一次新闻热搜 JSON 快照，用来把长图里的序号反查到原文链接。
        """
        try:
            target = str(target_uid or "").strip()
            if not target:
                return False

            if not isinstance(snapshot_data, dict):
                return False
            items = snapshot_data.get("items") if isinstance(snapshot_data.get("items"), list) else []
            actual_source = snapshot_data.get("source") or snapshot_data.get("source_key")
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

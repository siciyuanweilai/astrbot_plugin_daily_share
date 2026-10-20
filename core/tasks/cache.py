from __future__ import annotations

from .snapshot.cleanse import TaskNewsCacheNormalizeService
from .snapshot.focus import TaskNewsCacheFocusService
from .snapshot.formatter import TaskNewsCacheFormatService
from .snapshot.lookup import TaskNewsCacheLookupService
from .snapshot.store import TaskNewsCacheStoreService
from .taskbase import TaskServiceBase


class TaskNewsCacheService(TaskServiceBase):
    """新闻快照缓存和缓存链接查询辅助方法。"""

    NEWS_SNAPSHOT_TTL_SECONDS = TaskNewsCacheNormalizeService.NEWS_SNAPSHOT_TTL_SECONDS

    def get_news_snapshot_limit(self):
        """缓存新闻长图对应结构化数据时尽量保留完整列表。"""
        return self.normalize.get_news_snapshot_limit()

    def _news_snapshot_key(self, target_uid):
        return self.normalize._news_snapshot_key(target_uid)

    def _is_news_snapshot(self, snapshot):
        return self.normalize._is_news_snapshot(snapshot)

    def _is_news_snapshot_fresh(self, snapshot):
        """仅允许最近发送的新闻快照参与上下文和链接反查。"""
        return self.normalize._is_news_snapshot_fresh(snapshot)

    def _clean_snapshot_text(self, value, max_len=300):
        return self.normalize._clean_snapshot_text(value, max_len)

    def _normalize_news_snapshot_items(self, items):
        return self.normalize._normalize_news_snapshot_items(items)

    def _normalize_news_link_action(self, action):
        return self.normalize._normalize_news_link_action(action)

    def _coerce_news_tool_index(self, index):
        return self.normalize._coerce_news_tool_index(index)

    @staticmethod
    def news_snapshot_payload(items, source):
        return TaskNewsCacheStoreService.news_snapshot_payload(items, source)

    def prepare_news_snapshot_record(self, snapshot_data, image_url=None):
        return self.store.prepare_news_snapshot_record(snapshot_data, image_url)

    def invalidate_news_context_prompt(self, target_uid) -> None:
        """让新闻快照写入和焦点更新立即刷新工具动态上下文。"""
        support = getattr(self.plugin, "support_service", None)
        operations = getattr(support, "operations", None)
        tool_context = getattr(operations, "tool_context", None)
        invalidate = getattr(tool_context, "invalidate_context_prompt", None)
        if callable(invalidate):
            invalidate("news", target_uid)

    async def commit_sent_news_snapshot(
        self, target_uid, snapshot_data=None, image_url=None
    ):
        """追加保存与成功发送新闻长图配对的结构化快照。"""
        return await self.store.commit_sent_news_snapshot(
            target_uid, snapshot_data, image_url
        )

    def _news_snapshot_focus_key(self, target_uid):
        return self.focus._news_snapshot_focus_key(target_uid)

    async def _remember_news_focus(self, target_uid, snapshot, index):
        return await self.focus._remember_news_focus(target_uid, snapshot, index)

    async def _focused_news_index(self, target_uid, snapshot, source_key):
        return await self.focus._focused_news_index(target_uid, snapshot, source_key)

    async def _news_short_url_cache(self):
        return await self.formatter._news_short_url_cache()

    async def _save_news_short_url_cache(self, cache):
        return await self.formatter._save_news_short_url_cache(cache)

    async def _shorten_news_url(self, url):
        return await self.formatter._shorten_news_url(url)

    async def _shorten_news_url_once(self, original_url):
        return await self.formatter._shorten_news_url_once(original_url)

    async def _format_news_link_item(self, snapshot, item, index, action="link"):
        return await self.formatter._format_news_link_item(
            snapshot, item, index, action
        )

    def _format_news_link_preview(self, snapshot, items, limit=10):
        return self.formatter._format_news_link_preview(snapshot, items, limit)

    async def get_cached_news_link(
        self, target_uid, query="", action="link", index="", source_key=None
    ):
        """从最近一次新闻快照中按大语言模型结构化参数取链接、摘要或来源。"""
        return await self.lookup.get_cached_news_link(
            target_uid, query, action, index, source_key
        )

    async def _load_news_snapshot(self, target, *, source_key=None):
        return await self.lookup._load_news_snapshot(target, source_key=source_key)

    async def _resolve_news_item_index(
        self, target, snapshot, *, source_key, index, fallback_to_query=False
    ):
        return await self.lookup._resolve_news_item_index(
            target,
            snapshot,
            source_key=source_key,
            index=index,
            fallback_to_query=fallback_to_query,
        )

    async def _format_indexed_news_link(
        self, target, snapshot, items, item_index, action_key
    ):
        return await self.lookup._format_indexed_news_link(
            target, snapshot, items, item_index, action_key
        )

    def __init__(self, runtime, config, state) -> None:
        super().__init__(runtime, config, state)
        self.normalize = TaskNewsCacheNormalizeService(self)
        self.store = TaskNewsCacheStoreService(self)
        self.focus = TaskNewsCacheFocusService(self)
        self.formatter = TaskNewsCacheFormatService(self)
        self.lookup = TaskNewsCacheLookupService(self)


__all__ = ["TaskNewsCacheService"]

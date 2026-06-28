from __future__ import annotations

from ...config import NEWS_SOURCE_MAP


class TaskNewsCacheLookupMixin:
    async def get_cached_news_link(
        self,
        target_uid: str,
        query: str = "",
        action: str = "link",
        index: str = "",
        source_key: str = None,
        refresh_source: bool = True,
    ) -> str:
        """从最近一次新闻快照中按大语言模型结构化参数取链接、摘要或来源。"""
        target = str(target_uid or "").strip()
        if not target:
            return "工具内部提示：没有当前会话信息。请自然说明暂时查不到刚才那条新闻链接，不要提及工具状态。"

        if source_key and refresh_source:
            news_data = await self.news_service.get_hot_news(
                source_key,
                limit=self.get_news_snapshot_limit(),
                allow_fallback=False,
            )
            ok = bool(
                news_data
                and await self.cache_news_snapshot(
                    target,
                    snapshot_data=self._news_snapshot_payload(news_data[0], news_data[1]),
                )
            )
            if not ok:
                source_name = NEWS_SOURCE_MAP.get(source_key, {}).get("name", source_key)
                return f"工具内部提示：获取【{source_name}】新闻列表失败。请自然说明暂时拿不到原文链接，不要提及工具状态。"

        snapshot_key, snapshot = await self._load_news_snapshot(target, source_key=source_key)
        if not self._is_news_snapshot(snapshot):
            return "工具内部提示：还没有可用于反查的新闻列表。请自然提醒用户先分享一次新闻，再问“第3条链接”，不要提及工具状态。"

        if source_key and not refresh_source and snapshot.get("source_key") != source_key:
            wanted_name = NEWS_SOURCE_MAP.get(source_key, {}).get("name", source_key)
            current_name = snapshot.get("source_name") or "新闻热搜"
            return f"工具内部提示：当前可用新闻源是【{current_name}】，不是用户指定的【{wanted_name}】。请自然提醒用户先分享对应新闻源，或直接问刚才新闻的第几条链接；不要提及工具状态。"

        action_key = self._normalize_news_link_action(action)
        items = snapshot.get("items") or []
        if action_key == "list":
            return self._format_news_link_preview(snapshot, items)

        item_index = await self._resolve_news_item_index(
            target,
            snapshot,
            source_key=source_key,
            index=index,
        )
        if isinstance(item_index, str):
            return item_index
        if item_index is not None:
            return await self._format_indexed_news_link(target, snapshot_key, snapshot, items, item_index, action_key)

        text = str(query or "").strip()
        if not text:
            return self._format_news_link_preview(snapshot, items)

        keyword = text.lower()
        for idx, item in enumerate(items, start=1):
            haystack = f"{item.get('title', '')} {item.get('description', '')}".lower()
            if keyword in haystack:
                await self._remember_news_focus(target, snapshot_key, snapshot, idx)
                return await self._format_news_link_item(snapshot, item, idx, action_key)

        return f"工具内部提示：新闻列表里没找到“{text}”。请自然提醒用户换个关键词；如果用户表达的是第几条，请你把序号转成阿拉伯数字填入 index 后再次调用本工具。不要提及工具状态。"

    async def _load_news_snapshot(self, target: str, *, source_key: str | None = None) -> tuple[str, dict]:
        snapshot_key = self._news_snapshot_key(target)
        snapshot = await self.db.get_state(snapshot_key, {})
        if source_key:
            source_snapshot_key = self._news_snapshot_source_key(target, source_key)
            source_snapshot = await self.db.get_state(source_snapshot_key, {})
            if self._is_news_snapshot(source_snapshot):
                return source_snapshot_key, source_snapshot
        return snapshot_key, snapshot

    async def _resolve_news_item_index(
        self,
        target: str,
        snapshot: dict,
        *,
        source_key: str | None,
        index: str,
    ) -> int | str | None:
        index_text = str(index or "").strip()
        item_index = self._coerce_news_tool_index(index_text)
        if index_text and item_index is None:
            return (
                "工具内部提示：index 参数不是纯数字。请你自己理解用户要第几条，"
                "把阿拉伯数字字符串填入 index 后再次调用本工具；不要向用户提及工具状态。"
            )

        if item_index is None:
            item_index = await self._focused_news_index(target, snapshot, source_key)
        return item_index

    async def _format_indexed_news_link(
        self,
        target: str,
        snapshot_key: str,
        snapshot: dict,
        items: list,
        item_index: int,
        action_key: str,
    ) -> str:
        if item_index < 1 or item_index > len(items):
            return f"工具内部提示：当前新闻列表共有 {len(items)} 条，用户请求的序号超出范围。请自然提醒换个 1-{len(items)} 范围内的序号，不要提及工具状态。"
        await self._remember_news_focus(target, snapshot_key, snapshot, item_index)
        return await self._format_news_link_item(snapshot, items[item_index - 1], item_index, action_key)

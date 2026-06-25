from __future__ import annotations

import re
from typing import Optional


class TaskNewsCacheNormalizeMixin:
    def get_news_snapshot_limit(self) -> int:
        """缓存新闻长图对应 JSON 时尽量保留完整列表。"""
        return 50

    def _news_snapshot_key(self, target_uid: str) -> str:
        target = str(target_uid or "").strip() or "global"
        return f"news_snapshot:{target}"

    def _news_snapshot_source_key(self, target_uid: str, source_key: str) -> str:
        source = str(source_key or "").strip() or "unknown"
        return f"{self._news_snapshot_key(target_uid)}:source:{source}"

    def _is_news_snapshot(self, snapshot) -> bool:
        return isinstance(snapshot, dict) and bool(snapshot.get("items"))

    def _clean_snapshot_text(self, value, max_len: int = 300) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if max_len > 0 and len(text) > max_len:
            return text[:max_len].rstrip() + "..."
        return text

    def _normalize_news_snapshot_items(self, items) -> list:
        normalized = []
        for item in list(items or [])[: self.get_news_snapshot_limit()]:
            if not isinstance(item, dict):
                continue

            title = self._clean_snapshot_text(item.get("title") or item.get("name"), 180)
            if not title:
                continue

            entry = {
                "title": title,
                "url": self._clean_snapshot_text(
                    item.get("url")
                    or item.get("link")
                    or item.get("mobile_link")
                    or item.get("mobile_url")
                    or item.get("mobileUrl"),
                    500,
                ),
                "hot": self._clean_snapshot_text(
                    item.get("hot")
                    or item.get("hotValue")
                    or item.get("hot_value")
                    or item.get("hot_value_desc")
                    or item.get("score_desc")
                    or item.get("score"),
                    80,
                ),
                "description": self._clean_snapshot_text(
                    item.get("description")
                    or item.get("summary")
                    or item.get("desc")
                    or item.get("content")
                    or item.get("detail"),
                    300,
                ),
            }

            for extra_key in ("author", "cover", "created", "created_at"):
                if item.get(extra_key):
                    entry[extra_key] = item.get(extra_key)

            normalized.append(entry)
        return normalized

    def _normalize_news_link_action(self, action: str) -> str:
        text = str(action or "").strip().lower()
        if text in {"summary", "detail", "details", "摘要", "详情", "详细", "详细说明", "详细说说", "介绍"}:
            return "summary"
        if text in {"source", "origin", "from", "出处", "来源", "新闻源"}:
            return "source"
        if text in {"list", "preview", "items", "列表", "清单", "目录", "可查列表"}:
            return "list"
        return "link"

    def _coerce_news_tool_index(self, index) -> Optional[int]:
        text = "".join(
            str(index or "")
            .strip()
            .translate(str.maketrans("０１２３４５６７８９", "0123456789"))
            .split()
        )
        return int(text) if text.isdigit() else None

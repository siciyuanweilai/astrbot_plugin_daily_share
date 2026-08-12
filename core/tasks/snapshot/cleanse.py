from __future__ import annotations

import re

from ..taskbase import TaskServiceBase


class TaskNewsCacheNormalizeService(TaskServiceBase):
    def get_news_snapshot_limit(self) -> int:
        """缓存新闻长图对应结构化数据时尽量保留完整列表。"""
        return 50

    def _news_snapshot_key(self, target_uid: str) -> str:
        target = str(target_uid or "").strip() or "global"
        return f"news_snapshot:{target}"

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

            title = self._clean_snapshot_text(
                item.get("title") or item.get("name"), 180
            )
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
                    entry[extra_key] = str(item.get(extra_key) or "")

            normalized.append(entry)
        return normalized

    def _normalize_news_link_action(self, action: str) -> str:
        text = str(action or "").strip().lower()
        if text in {
            "summary",
            "detail",
            "details",
            "摘要",
            "详情",
            "详细",
            "详细说明",
            "详细说说",
            "介绍",
        }:
            return "summary"
        if text in {"source", "origin", "from", "出处", "来源", "新闻源"}:
            return "source"
        if text in {"list", "preview", "items", "列表", "清单", "目录", "可查列表"}:
            return "list"
        return "link"

    def _coerce_news_tool_index(self, index) -> int | None:
        text = "".join(
            str(index or "")
            .strip()
            .translate(str.maketrans("０１２３４５６７８９", "0123456789"))
            .split()
        )
        text = text.strip("，,。.!！?？:：;；\"'“”‘’")
        if not text:
            return None
        if text.isdigit():
            return int(text)

        number_chars = set("0123456789零〇一二两三四五六七八九十百")
        if all(char in number_chars for char in text):
            number = text
        else:
            if text.count("第") != 1:
                return None
            number_start = text.index("第") + 1
            number_end = number_start
            while number_end < len(text) and text[number_end] in number_chars:
                number_end += 1
            if number_end == number_start:
                return None
            outside = text[: number_start - 1] + text[number_end:]
            if any(char in number_chars for char in outside):
                return None
            number = text[number_start:number_end]

        if number.isdigit():
            return int(number)
        if any(char.isdigit() for char in number):
            return None
        digit_map = {
            "零": 0,
            "〇": 0,
            "一": 1,
            "二": 2,
            "两": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
        }
        if "百" in number:
            left, right = number.split("百", 1)
            hundreds = digit_map.get(left or "一")
            if hundreds is None:
                return None
            remainder = 0
            if right:
                if right.startswith(("零", "〇")):
                    right = right[1:]
                if "十" in right:
                    tens, ones = right.split("十", 1)
                    tens_value = digit_map.get(tens or "一")
                    ones_value = digit_map.get(ones, 0)
                    if tens_value is None or ones_value is None:
                        return None
                    remainder = tens_value * 10 + ones_value
                else:
                    remainder = digit_map.get(right, -1)
                    if remainder < 0:
                        return None
            return hundreds * 100 + remainder
        if "十" in number:
            tens, ones = number.split("十", 1)
            tens_value = digit_map.get(tens or "一")
            ones_value = digit_map.get(ones, 0)
            if tens_value is None or ones_value is None:
                return None
            return tens_value * 10 + ones_value
        if all(char in digit_map for char in number):
            return int("".join(str(digit_map[char]) for char in number))
        return None

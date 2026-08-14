import html
import json
import re
from typing import Any

from .client import NewsApiService


class NewsParserService(NewsApiService):
    """新闻接口响应解析。"""

    conf: dict

    ITEM_CONTAINER_KEYS = ("data", "list", "items", "result")
    NESTED_ITEM_CONTAINER_KEYS = ("list", "items")
    TITLE_KEYS = ("title", "name", "query", "word", "keyword")
    HOT_KEYS = (
        "hot",
        "hotValue",
        "hot_value",
        "hot_value_desc",
        "heat",
        "hotScore",
        "like_count",
        "score_desc",
        "score",
    )
    URL_KEYS = ("url", "link", "mobileUrl", "mobile_url", "mobile_link")
    DESCRIPTION_KEYS = (
        "description",
        "desc",
        "summary",
        "abstract",
        "digest",
        "brief",
        "intro",
        "detail",
        "content",
    )

    def _loads_json_payload(self, text: str) -> Any:  # noqa: C901
        """从被状态文本或调试输出包裹的响应中提取新闻结构化数据。"""
        if not text:
            raise json.JSONDecodeError("响应为空", "", 0)

        # 限制异常上游响应的体积，避免解析任务无限占用处理器。
        if len(text) > 8 * 1024 * 1024:
            raise json.JSONDecodeError("JSON 响应过大", text, 0)

        decoder = json.JSONDecoder()
        clean = text.lstrip("\ufeff \t\r\n")
        candidates = []
        direct_error = json.JSONDecodeError("未找到 JSON 载荷", clean, 0)

        try:
            data, end = decoder.raw_decode(clean)
            candidates.append((0, end, data))
        except json.JSONDecodeError:
            pass

        candidate_count = 0
        for start, char in enumerate(clean):
            if char not in "[{":
                continue
            if start == 0 and candidates:
                continue
            candidate_count += 1
            if candidate_count > 64:
                break
            try:
                # 直接传入偏移量，避免为每个候选位置重复复制剩余文本。
                data, end = decoder.raw_decode(clean, start)
                candidates.append((start, end, data))
            except json.JSONDecodeError:
                continue

        if not candidates:
            raise direct_error

        for _, _, data in candidates:
            if self._has_parseable_news_items(data):
                return data

        return candidates[0][2]

    def _parse_news_payload(
        self, text: str, limit: int | None = None
    ) -> tuple[Any, list[dict] | None]:
        """在线程中解析并规范化一次新闻响应。"""
        data = self._loads_json_payload(text)
        return data, self._parse_response(data, limit=limit)

    @staticmethod
    def _is_tencent_style_dict(value: dict) -> bool:
        return any(str(k).startswith("Top_") for k in value.keys())

    def _has_parseable_news_items(self, data: Any) -> bool:
        return any(
            isinstance(item, dict) and self._first_non_empty(item, self.TITLE_KEYS)
            for item in self._extract_news_items(data)
        )

    def _extract_news_items(self, data: Any) -> list[dict]:
        if isinstance(data, list):
            return data
        if not isinstance(data, dict):
            return []

        if self._is_tencent_style_dict(data):
            return list(data.values())

        for key in self.ITEM_CONTAINER_KEYS:
            value = data.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                if self._is_tencent_style_dict(value):
                    return list(value.values())
                for nested_key in self.NESTED_ITEM_CONTAINER_KEYS:
                    nested_value = value.get(nested_key)
                    if isinstance(nested_value, list):
                        return nested_value

        return []

    @staticmethod
    def _first_non_empty(item: dict, keys) -> Any:
        for key in keys:
            value = item.get(key)
            if value:
                return value
        return ""

    def _parse_response(
        self, data: Any, limit: int | None = None
    ) -> list[dict] | None:
        """
        解析响应数据
        支持多层级结构化数据和多种上游字段名。
        支持腾讯新闻这种字典结构的列表 {"Top_1": {...}, "Top_2": {...}}
        """
        items = self._extract_news_items(data)

        if not items:
            return None

        limit = self._news_item_limit(limit)
        res: list[dict] = []
        for item in items:
            if len(res) >= limit:
                break
            parsed_item = self._parse_news_item(item)
            if parsed_item:
                res.append(parsed_item)

        return res if res else None

    def _news_item_limit(self, limit: int | None) -> int:
        raw_limit = self.conf.get("news_items_count", 5) if limit is None else limit
        try:
            return max(1, int(raw_limit))
        except (TypeError, ValueError):
            return 5

    @staticmethod
    def _clean_news_text(value: Any, max_len: int = 800) -> str:
        if value is None:
            return ""
        text = html.unescape(str(value))
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if max_len > 0 and len(text) > max_len:
            return text[:max_len].rstrip() + "..."
        return text

    def _parse_news_item(self, item: Any) -> dict | None:
        if not isinstance(item, dict):
            return None
        title = self._first_non_empty(item, self.TITLE_KEYS)
        if not title:
            return None
        hot = self._first_non_empty(item, self.HOT_KEYS)
        url_link = self._first_non_empty(item, self.URL_KEYS)
        parsed_item = {
            "title": str(title).strip(),
            "hot": str(hot).strip() if hot else "",
            "url": str(url_link).strip() if url_link else "",
        }
        description = self._first_non_empty(item, self.DESCRIPTION_KEYS)
        clean_description = self._clean_news_text(description)
        if clean_description and clean_description != parsed_item["title"]:
            parsed_item["description"] = clean_description
        for key in ("author", "cover", "created", "created_at", "source"):
            if item.get(key):
                parsed_item[key] = item[key]
        return parsed_item

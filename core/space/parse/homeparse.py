from __future__ import annotations

import re
from typing import Any

from ..models import QzonePost
from .decoder import _balanced_object_candidate, _object_literal_mapping


def _extract_home_module_payload(markup: str) -> dict[str, Any]:
    source = str(markup or "")
    match = re.search(r"var\s+_feedsdata\s*=\s*{", source)
    if not match:
        return {}
    start = source.find("{", match.start())
    candidate = _balanced_object_candidate(source, start)
    return _object_literal_mapping(candidate) if candidate else {}


def _extract_home_feed_blocks(markup: str) -> list[str]:
    source = str(markup or "")
    blocks: list[str] = []
    pattern = re.compile(
        r"<li\b[^>]*class=(['\"])[^'\"]*\bf-single\b[^'\"]*\1[^>]*>", re.I
    )
    matches = list(pattern.finditer(source))
    for index, match in enumerate(matches):
        start = match.start()
        if index + 1 < len(matches):
            end = matches[index + 1].start()
        else:
            list_end = source.find("</ul>", match.end())
            end = len(source) if list_end < 0 else list_end
        if end > start:
            blocks.append(source[start:end])
    return blocks


def _home_feed_id_part(feed: dict[str, Any]) -> str:
    return "_".join(
        str(feed.get(key) or "")
        for key in ("uin", "appid", "typeid", "abstime", "feedno")
    )


def _home_feeds_with_html(
    feeds: list[dict[str, Any]], markup: str
) -> list[dict[str, Any]]:
    blocks = _extract_home_feed_blocks(markup)
    if not blocks:
        return feeds
    used: set[int] = set()
    result: list[dict[str, Any]] = []
    for index, feed in enumerate(feeds):
        key = str(feed.get("key") or "")
        id_part = _home_feed_id_part(feed)
        block_index = -1
        for block_idx, block in enumerate(blocks):
            if block_idx in used:
                continue
            if (key and f'data-key="{key}"' in block) or (id_part and id_part in block):
                block_index = block_idx
                break
        if block_index < 0 and index < len(blocks) and index not in used:
            block_index = index
        if block_index >= 0:
            used.add(block_index)
            result.append({**feed, "html": feed.get("html") or blocks[block_index]})
        else:
            result.append(feed)
    return result


def parse_home_feed_list(markup_or_payload: Any) -> list[QzonePost]:
    from .mood import parse_recent_feed_list

    payload = (
        _extract_home_module_payload(markup_or_payload)
        if isinstance(markup_or_payload, str)
        else markup_or_payload
    )
    data = payload.get("data") if isinstance(payload, dict) else {}
    feeds: list[dict[str, Any]] = []
    if isinstance(data, dict):
        for key in ("host_data", "firstpage_data", "friend_data", "about_data", "data"):
            feeds.extend(item for item in data.get(key) or [] if isinstance(item, dict))
    if isinstance(feeds, list) and isinstance(markup_or_payload, str):
        feeds = _home_feeds_with_html(feeds, markup_or_payload)
    return parse_recent_feed_list({"data": {"data": feeds}})

"""生活观察使用共享新闻快照，只提供与当前兴趣相关的真实文字材料。"""

from __future__ import annotations

from ...context.relevance import terms
from ..opportunity import compact, digest

_CACHE = "living_news_snapshot"


async def news_materials(living, data: dict, now) -> list[dict]:
    if (data.get("current_facts") or {}).get("valid") is not True:
        return []
    interests = (data.get("continuity") or {}).get("interests") or []
    labels = [
        compact(row.get("label"), 100)
        for row in interests
        if isinstance(row, dict) and row.get("state") == "active"
    ]
    query = terms(" ".join(labels))
    conf = living.plugin.config.get("news_conf") or {}
    if (
        not query
        or not conf.get("enable_news_api", True)
        or not conf.get("nycnm_api_key")
    ):
        return []
    signature = digest(conf)
    cache = await living.db.get_share_state(_CACHE, {})
    if cache.get("signature") != signature or now.timestamp() >= cache.get(
        "expires_at", 0
    ):
        # 请求前落失败退避，异常与重载也不会让每个目标重新请求。
        cache = {
            "signature": signature,
            "expires_at": now.timestamp() + 300,
            "items": [],
            "source": "",
            "fetched_at": "",
        }
        await living.db.update_share_state(_CACHE, cache)
        result = await living.schedule.news_service.get_hot_news(limit=20)
        if result:
            items, source = result
            cache.update(
                items=items[:20],
                source=source,
                fetched_at=now.isoformat(),
                expires_at=now.timestamp() + 1800,
            )
            await living.db.update_share_state(_CACHE, cache)
    rows = []
    for item in cache.get("items") or []:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        text = str(item.get("title", "")) + " " + str(item.get("description", ""))
        overlap = query & terms(text)
        if (
            len(overlap) < 2
            and not any(len(word) >= 5 and word.isascii() for word in overlap)
            and not any(
                len(label) >= 2 and label.lower() in text.lower() for label in labels
            )
        ):
            continue
        article = {
            key: compact(item.get(key), 800 if key == "description" else 400)
            for key in ("title", "description", "url")
        }
        rows.append(
            {
                "id": digest(["news", cache.get("source"), article]),
                "kind": "news",
                "title": article["title"],
                "detail": article["description"],
                "source": cache.get("source"),
                "fetched_at": cache.get("fetched_at"),
                "news_item": article,
            }
        )
    return rows[:4]

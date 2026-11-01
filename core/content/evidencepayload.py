"""保留检索的结构化依据与缺口，不按正文措辞推断检索是否成功。"""

import json


def search_reference(payload, *, content=None):
    if (
        not isinstance(payload, dict)
        or payload.get("status") != "ok"
        or not isinstance(payload.get("content"), str)
        or not isinstance(payload.get("quality"), str)
        or not all(
            isinstance(payload.get(key), list)
            for key in ("sources", "missing_aspects", "providers")
        )
    ):
        return ""
    text = str((payload.get("content") if content is None else content) or "").strip()[:2000]
    if not text:
        return ""
    result = {"content": text}
    for key in ("quality", "source_scope", "provider_mode"):
        if isinstance(payload.get(key), str):
            result[key] = payload[key][:80]
    for key in ("missing_aspects", "providers"):
        if isinstance(payload.get(key), list):
            result[key] = [item[:180] for item in payload[key][:5] if isinstance(item, str)]
    sources = payload.get("sources")
    result["sources"] = [
        {key: row[key][:400] for key in ("title", "url", "provider") if isinstance(row.get(key), str)}
        for row in (sources[:5] if isinstance(sources, list) else []) if isinstance(row, dict)
    ]
    return json.dumps(result, ensure_ascii=False)

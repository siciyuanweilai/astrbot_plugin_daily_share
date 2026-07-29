from __future__ import annotations

import json


def _extract_json_object(text: str) -> str:
    text = str(text or "").replace("```json", "").replace("```", "").strip()
    start = text.find("{")
    if start < 0:
        return text

    try:
        _, end = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return text[start:]
    return text[start : start + end]

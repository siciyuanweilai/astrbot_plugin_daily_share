from __future__ import annotations

import html
import json
import re
from typing import Any

from astrbot.api import logger

try:
    import json5
except Exception:
    json5 = None


def _json_object_candidates(raw: str) -> list[str]:
    text = str(raw or "")
    candidates: list[str] = []
    start = text.find("{")
    end = text.rfind("}")
    if 0 <= start < end:
        candidates.append(text[start : end + 1])

    for start_match in re.finditer(r"{", text):
        start = start_match.start()
        depth = 0
        quote = ""
        escape = False
        for index in range(start, len(text)):
            ch = text[index]
            if quote:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == quote:
                    quote = ""
                continue
            if ch in {"'", '"'}:
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start : index + 1])
                    break
        if len(candidates) >= 80:
            break
    return list(dict.fromkeys(item.strip() for item in candidates if item.strip()))

def _parse_json_object(body: str) -> dict[str, Any]:
    normalized = str(body or "").replace("undefined", "null")
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError as exc:
        if json5 is not None:
            try:
                parsed = json5.loads(normalized)
            except Exception as json5_exc:
                raise ValueError(f"{exc}；json5 解析失败: {json5_exc}") from json5_exc
        else:
            raise ValueError(str(exc)) from exc
    if not isinstance(parsed, dict):
        raise ValueError("响应格式异常")
    return parsed

def _parse_js_object_literal(body: str) -> dict[str, Any]:
    normalized = str(body or "").replace("undefined", "null")
    quoted = re.sub(
        r"(?<=[{,\s])([A-Za-z_$][\w$]*)\s*:",
        r'"\1":',
        normalized,
    )
    quoted = re.sub(r"'([^'\\]*(?:\\.[^'\\]*)*)'", r'"\1"', quoted)
    parsed = json.loads(quoted)
    if not isinstance(parsed, dict):
        raise ValueError("响应格式异常")
    return parsed

def parse_qzone_response(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {"code": -1, "message": "QQ 空间返回为空"}

    candidates = _json_object_candidates(raw)
    if not candidates:
        return {"code": -1, "message": "QQ 空间返回内容不是结构化数据"}

    parser_errors: list[str] = []
    for body in candidates:
        try:
            return _parse_json_object(body)
        except ValueError as exc:
            parser_errors.append(f"json: {exc}")
            try:
                return _parse_js_object_literal(body)
            except (TypeError, ValueError, json.JSONDecodeError) as js_exc:
                parser_errors.append(f"js-literal: {js_exc}")
            continue
    logger.debug(f"[每日分享] QQ 空间响应解析失败: {'; '.join(parser_errors[-6:])}")
    return {"code": -1, "message": "QQ 空间响应解析失败"}

def parse_upload_result(payload: dict[str, Any]) -> tuple[str, str]:
    data = payload.get("data") if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        raise RuntimeError("QQ 空间图片上传返回格式异常")
    url = str(data.get("url") or "")
    if "&bo=" not in url:
        raise RuntimeError("QQ 空间图片上传缺少 bo 参数")
    picbo = url.split("&bo=", 1)[1]
    richval = ",{},{},{},{},{},{},,{},{}".format(
        data.get("albumid", ""),
        data.get("lloc", ""),
        data.get("sloc", ""),
        data.get("type", ""),
        data.get("height", ""),
        data.get("width", ""),
        data.get("height", ""),
        data.get("width", ""),
    )
    return picbo, richval

def clean_qzone_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(?:div|p|li|section|article)>", "\n", text)
    text = re.sub(r"\[em\].*?\[/em\]", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t\f\v\r]+", " ", text)
    lines = [re.sub(r" {2,}", " ", line).strip() for line in text.split("\n")]
    cleaned = "\n".join(line for line in lines if line)
    cleaned = re.sub(r"\n?\s*展开全文\s*$", "", cleaned)
    return cleaned.strip()

def has_qzone_expand_marker(value: Any) -> bool:
    return bool(re.search(r"\b展开全文\b|展开全文", html.unescape(str(value or ""))))

def _clean_media_url(value: Any) -> str:
    url = html.unescape(str(value or "").strip())
    if url.startswith("//"):
        url = f"https:{url}"
    return url

def _tag_attrs(tag: str) -> dict[str, str]:
    return {
        key.lower(): value
        for key, _, value in re.findall(r'([:\w-]+)\s*=\s*(["\'])(.*?)\2', tag or "", re.S)
    }

def _decode_js_escaped_text(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""

    def replace_hex(match: re.Match) -> str:
        try:
            return chr(int(match.group(1), 16))
        except Exception:
            return match.group(0)

    def replace_unicode(match: re.Match) -> str:
        try:
            return chr(int(match.group(1), 16))
        except Exception:
            return match.group(0)

    text = re.sub(r"\\x([0-9A-Fa-f]{2})", replace_hex, text)
    text = re.sub(r"\\u([0-9A-Fa-f]{4})", replace_unicode, text)
    return html.unescape(text.replace("\\/", "/").replace('\\"', '"').replace("\\'", "'"))

def _json_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    text = html.unescape(value).strip()
    if not text or not text.startswith("{") or len(text) > 200_000:
        return {}
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}

def _object_literal_mapping(value: str) -> dict[str, Any]:
    text = html.unescape(str(value or "")).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text.replace("undefined", "null"))
    except (TypeError, ValueError):
        if json5 is None:
            parsed = None
        else:
            try:
                parsed = json5.loads(text)
            except Exception:
                parsed = None
    if parsed is None:
        quoted = re.sub(r"(?<=[{,\s])([A-Za-z_$][\w$]*)\s*:", r'"\1":', text.replace("undefined", "null"))
        try:
            parsed = json.loads(quoted)
        except (TypeError, ValueError):
            return {}
    return parsed if isinstance(parsed, dict) else {}

def _dig(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current

def _mapping_first(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None

def _mapping_first_from_paths(mapping: dict[str, Any], paths: tuple[tuple[str, ...], ...]) -> Any:
    for path in paths:
        value = _dig(mapping, *path)
        if value not in (None, ""):
            return value
    return None

def _html_first_attr(markup: Any, names: tuple[str, ...]) -> str:
    for name in names:
        value = _html_attr(markup, name)
        if value:
            return value
    return ""

def _first_json_mapping(mapping: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    for key in keys:
        value = _json_mapping(mapping.get(key))
        if value:
            return value
    return {}

def _html_attr(markup: Any, name: str) -> str:
    text = str(markup or "")
    if not text:
        return ""
    match = re.search(
        rf'\b{re.escape(name)}\s*=\s*(["\'])(.*?)\1',
        text,
        re.I | re.S,
    )
    return html.unescape(match.group(2)).strip() if match else ""

def _safe_int(value: Any) -> int:
    text = str(value or "").strip()
    if text.lower().startswith("o"):
        text = text[1:]
    return int(text) if text.isdigit() else 0

def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""

def _walk_mappings(value: Any):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk_mappings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk_mappings(item)


__all__ = [
    "clean_qzone_text",
    "has_qzone_expand_marker",
    "parse_qzone_response",
    "parse_upload_result",
]

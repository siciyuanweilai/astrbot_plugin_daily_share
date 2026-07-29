from __future__ import annotations


_URL_PREFIXES = ("https://", "http://")
_URL_TRAILING_PUNCTUATION = ".,;:!?，。；：！？"


def _url_end(text: str, start: int) -> int:
    end = start
    while end < len(text) and not text[end].isspace() and text[end] not in "，。；！？":
        end += 1
    while end > start and text[end - 1] in _URL_TRAILING_PUNCTUATION:
        end -= 1
    return end


def _markdown_link_end(text: str, destination_start: int) -> int | None:
    if not text.startswith(_URL_PREFIXES, destination_start):
        return None
    closing = text.find(")", destination_start)
    return closing if closing >= 0 else None


def strip_news_reference_links(text: str) -> str:
    """移除仅用于核实的检索链接，保留可读的事实文本。"""
    value = str(text or "")
    result: list[str] = []
    index = 0

    while index < len(value):
        if value.startswith("[[", index):
            marker_end = value.find("]]", index + 2)
            if marker_end >= 0 and value.startswith("(", marker_end + 2):
                closing = _markdown_link_end(value, marker_end + 3)
                marker = value[index + 2 : marker_end].strip()
                if closing is not None and marker.isdigit():
                    index = closing + 1
                    continue

        if value[index] == "[":
            label_end = value.find("]", index + 1)
            if label_end >= 0 and value.startswith("(", label_end + 1):
                closing = _markdown_link_end(value, label_end + 2)
                if closing is not None:
                    label = value[index + 1 : label_end].strip()
                    if label and not label.isdigit():
                        result.append(label)
                    index = closing + 1
                    continue

        if value.startswith(_URL_PREFIXES, index):
            index = _url_end(value, index)
            continue

        result.append(value[index])
        index += 1

    cleaned = "".join(result)
    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n\n", "\n\n")
    while "  " in cleaned:
        cleaned = cleaned.replace("  ", " ")
    for punctuation in "，。；：！？":
        cleaned = cleaned.replace(f" {punctuation}", punctuation)
    return cleaned.strip()


__all__ = ["strip_news_reference_links"]

from __future__ import annotations

from html.parser import HTMLParser

from .decoder import clean_qzone_text

_BODY_CLASSES = (
    "f-info",
    "txt-box-title",
    "txt-box",
    "content-box",
    "qz_summary",
    "f-reprint",
)
_NON_BODY_CLASSES = frozenset(
    {
        "f-single-head",
        "f-single-foot",
        "f-op-detail",
        "f-detail",
        "op-list",
        "user-info",
        "user-pto",
        "user-op",
        "img-box",
        "video-img",
        "fui-txtimg",
        "single-reply",
    }
)
_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)


class _FeedTextParser(HTMLParser):
    """Read balanced body nodes while keeping interaction subtrees out of captions."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stack: list[tuple[str, bool, int | None]] = []
        self.candidates: list[tuple[int, list[str]]] = []

    def _append(self, fragment: str) -> None:
        for _, _, index in self.stack:
            if index is not None:
                self.candidates[index][1].append(fragment)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        classes = str(values.get("class") or "").lower().split()
        blocked = (
            bool(self.stack and self.stack[-1][1])
            or tag in {"script", "style", "form", "textarea"}
            or values.get("data-type") in {"commentroot", "replyroot"}
            or any(
                name in _NON_BODY_CLASSES
                or name.startswith(
                    ("comments-", "mod-comments", "mod-commnets", "f-like")
                )
                for name in classes
            )
        )
        index = None
        if not blocked and tag not in _VOID_TAGS:
            ranks = [rank for rank, name in enumerate(_BODY_CLASSES) if name in classes]
            if ranks:
                index = len(self.candidates)
                self.candidates.append((min(ranks), []))
        if tag not in _VOID_TAGS:
            self.stack.append((tag, blocked, index))
        if not blocked:
            self._append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                if not self.stack[-1][1]:
                    self._append(f"</{tag}>")
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.stack and not self.stack[-1][1]:
            self._append(data)

    def handle_entityref(self, name):
        self.handle_data(f"&{name};")

    def handle_charref(self, name):
        self.handle_data(f"&#{name};")


def feed_body_text(raw_html: str) -> str:
    parser = _FeedTextParser()
    parser.feed(str(raw_html or ""))
    parser.close()
    for _, parts in sorted(parser.candidates, key=lambda candidate: candidate[0]):
        text = clean_qzone_text("".join(parts))
        if text:
            return text
    return ""

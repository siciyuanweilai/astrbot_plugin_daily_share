from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from ..models import QzonePhoto
from .decoder import _safe_int


def parse_photo_batch_topic(
    topic_id: str, *, album_id: str
) -> tuple[str, str, int] | None:
    """解析已观察到的上传标识尾缀，仍须通过照片查看器核验各字段。"""
    prefix = f"{album_id}_"
    topic = unquote(str(topic_id or "").strip())
    if not album_id or not topic.startswith(prefix):
        return None
    parts = topic[len(prefix) :].rsplit("_", 2)
    if len(parts) != 3:
        return None
    pic, batch, platform = parts
    if (
        not pic
        or not batch.isascii()
        or not batch.isdigit()
        or len(batch) > 20
        or int(batch) <= 0
        or platform != "4"
    ):
        return None
    return pic, batch, 4


def parse_feed_photo_targets(
    item: dict[str, Any], *, appid: int, owner_uin: int, raw_html: str = ""
) -> list[QzonePhoto]:
    """只保留明确配对的照片标识，不从动态 fid 或图片 CDN 地址猜测。"""
    if appid != 4:
        return []
    targets: dict[tuple[int, str, str], QzonePhoto] = {}
    declared_count = 0

    def add(values: dict, album: str = "", owner: int = owner_uin):
        normalized = {
            str(k).lower().replace("-", "").replace("_", ""): v
            for k, v in values.items()
        }
        album = str(normalized.get("albumid") or album or "").strip()
        pic = str(normalized.get("pickey") or normalized.get("lloc") or "").strip()
        topic = str(normalized.get("topicid") or "").strip()
        if normalized.get("name") == "feed_data":
            album = album or str(normalized.get("tid") or "").strip()
            if not pic:
                # 上传批次的 subid 不一定是照片 picKey。
                batch_topic = parse_photo_batch_topic(topic, album_id=album)
                prefix = f"{album}_"
                if batch_topic:
                    pic = batch_topic[0]
                elif album and topic.startswith(prefix) and topic.endswith("_0_0"):
                    pic = topic[len(prefix) : -4]
                else:
                    pic = str(
                        normalized.get("origtid") or normalized.get("subid") or ""
                    ).strip()
        owner = (
            _safe_int(normalized.get("owneruin") or normalized.get("hostuin")) or owner
        )
        feed_topic = ""
        if topic and pic:
            # picKey 本身可能包含下划线，仅移除精确匹配的已知尾缀。
            suffix = f"_{pic}_0_0"
            if not album:
                batch_parts = topic.rsplit("_", 2)
                if topic.endswith(suffix):
                    album = topic.removesuffix(suffix)
                elif topic.endswith(f"_{pic}"):
                    album = topic.removesuffix(f"_{pic}")
                elif len(batch_parts) == 3 and batch_parts[0].endswith(f"_{pic}"):
                    # 未知尾缀保留为存在冲突的 topicId，不将其解释为新相册。
                    album = batch_parts[0].removesuffix(f"_{pic}")
                else:
                    album = topic
            if topic not in {album, f"{album}_{pic}"}:
                feed_topic = topic
        if album and pic:
            batch_topic = parse_photo_batch_topic(topic, album_id=album)
            batch_id = str(
                normalized.get("batchid") or (batch_topic[1] if batch_topic else "")
            ).strip()
            platform_sub_id = (
                _safe_int(normalized["platformsubid"])
                if "platformsubid" in normalized
                else batch_topic[2]
                if batch_topic
                else None
            )
            key = (owner, album, pic)
            existing = targets.get(key)
            if existing is None:
                targets[key] = QzonePhoto(
                    owner_uin=owner,
                    album_id=album,
                    pic_key=pic,
                    feed_topic_id=feed_topic,
                    batch_id=batch_id,
                    platform_sub_id=platform_sub_id,
                )
            else:
                if not existing.batch_id or (
                    batch_topic and batch_id != batch_topic[1]
                ):
                    existing.batch_id = batch_id
                if existing.platform_sub_id is None or (
                    batch_topic and platform_sub_id != batch_topic[2]
                ):
                    existing.platform_sub_id = platform_sub_id
                if feed_topic and (
                    not existing.feed_topic_id or feed_topic != f"{album}_{pic}_0_0"
                ):
                    existing.feed_topic_id = feed_topic
        return album, owner

    def walk(value, album="", owner=owner_uin, depth=0):
        nonlocal declared_count
        if depth > 6 or not isinstance(value, dict):
            return
        if value.get("is_video"):
            return
        album, owner = add(value, album, owner)
        for key in (
            "photo",
            "photos",
            "pic",
            "pic_list",
            "picList",
            "photoList",
            "photo_list",
        ):
            child = value.get(key)
            if isinstance(child, dict):
                walk(child, album, owner, depth + 1)
            elif isinstance(child, list):
                declared_count = max(declared_count, len(child))
                for entry in child[:100]:
                    walk(entry, album, owner, depth + 1)

    class PhotoTags(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack: list[tuple[str, bool]] = []

        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            classes = str(values.get("class") or "").lower()
            blocked = any(skip for _, skip in self.stack) or any(
                word in classes for word in ("comment", "reply", "repost")
            )
            if tag not in {"img", "br", "input", "hr", "meta", "link", "source", "wbr"}:
                self.stack.append((tag, blocked))
            if blocked:
                return
            # 配对的标识属性必须属于同一个 HTML 元素。
            album, owner = add({k.removeprefix("data-"): v for k, v in values.items()})
            for name in ("href", "link"):
                url = values.get(name) or ""
                try:
                    parts = urlsplit(url)
                    if parts.scheme not in {"", "http", "https"}:
                        continue
                    if parts.hostname and not (
                        parts.hostname == "qzone.qq.com"
                        or parts.hostname.endswith(".qzone.qq.com")
                    ):
                        continue
                    query = parse_qs(parts.query)
                    add(
                        {k: v[0] for k, v in query.items() if len(v) == 1},
                        album=album,
                        owner=owner,
                    )
                except ValueError:
                    continue

        def handle_endtag(self, tag):
            for index in range(len(self.stack) - 1, -1, -1):
                if self.stack[index][0] == tag:
                    del self.stack[index:]
                    break

    walk(item)
    PhotoTags().feed(raw_html)
    result = list(targets.values())
    if declared_count > len(result):
        # 仅解析出部分照片的批次不能视为唯一的单照片目标。
        result.append(
            QzonePhoto(
                owner_uin=owner_uin,
                unresolved_count=declared_count - len(result),
            )
        )
    return result

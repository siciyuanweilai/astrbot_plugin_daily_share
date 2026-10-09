from __future__ import annotations

import re
from typing import Any

from ..models import QzoneComment, QzonePhoto, QzonePhotoComment
from .decoder import _safe_int, clean_qzone_text


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _photo_url(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("//"):
        return f"https:{text}"
    return text if text.startswith(("http://", "https://")) else ""


def _photo_comment(item: dict[str, Any]) -> QzonePhotoComment:
    poster = _mapping(item.get("poster"))
    extend = _mapping(poster.get("extendData"))
    uin = _safe_int(poster.get("id") or item.get("uin"))
    return QzonePhotoComment(
        comment_id=str(item.get("id") or "").strip(),
        uin=uin,
        nickname=clean_qzone_text(poster.get("name") or uin),
        content=clean_qzone_text(item.get("content")),
        create_time=_safe_int(item.get("postTime") or item.get("create_time")),
        topic_id=str(item.get("topicId") or "").strip(),
        private=0 if item.get("private") in (None, 0, "0") else 1,
        source=_safe_int(item.get("source")),
        avatar_url=_photo_url(extend.get("face")),
    )


def photo_reply_mention(content: str) -> tuple[int, str]:
    mentions = re.findall(r"@\{([^}]*)\}", content or "")
    if len(mentions) != 1:
        return 0, ""
    uin = re.search(r"(?:^|,)uin:(\d+)(?:,|$)", mentions[0])
    nickname = re.search(r"(?:^|,)nick:(.*?)(?:,auto:|$)", mentions[0])
    return (
        _safe_int(uin.group(1)) if uin else 0,
        nickname.group(1) if nickname else "",
    )


def photo_thread_comments(photo: QzonePhoto) -> list[QzoneComment]:
    """区分原一级评论的提交标识与查看器回复标识。"""
    comments: list[QzoneComment] = []
    seen: set[tuple[str, str, int]] = set()
    for root in photo.comments:
        parent = QzoneComment(
            uin=root.uin,
            nickname=root.nickname,
            content=root.content,
            create_time=root.create_time,
            tid=root.comment_id,
            submit_tid=root.comment_id,
            raw_tid=root.comment_id,
            raw_fields={"photo_topic_id": root.topic_id, "photo_private": root.private},
        )
        comments.append(parent)
        thread = [parent]
        # 查看器回复可能按任意顺序返回；时间缺失或相同时，无法可靠定位
        # 回复对象，继续排除这些自动回评候选。
        for reply in sorted(root.replies, key=lambda item: item.create_time):
            identity = (root.comment_id, reply.comment_id, reply.uin)
            if identity in seen:
                continue
            seen.add(identity)
            target_uin, target_name = photo_reply_mention(reply.content)
            previous = [
                item
                for item in thread
                if item.uin == target_uin and 0 < item.create_time < reply.create_time
            ]
            latest_time = max((item.create_time for item in previous), default=0)
            latest = [item for item in previous if item.create_time == latest_time]
            target = latest[0] if len(latest) == 1 else None
            comment = QzoneComment(
                uin=reply.uin,
                nickname=reply.nickname,
                content=reply.content,
                create_time=reply.create_time,
                tid=f"{root.comment_id}_r_{reply.comment_id}_{reply.uin}",
                submit_tid=reply.comment_id,
                raw_tid=reply.comment_id,
                parent_tid=root.comment_id,
                reply_to_tid=target.tid if target else "",
                raw_reply_to_tid=target.raw_tid if target else "",
                reply_to_uin=target_uin,
                reply_to_nickname=target_name,
                reply_to_tid_source="photo_mention" if target else "",
                raw_fields={
                    "photo_topic_id": reply.topic_id,
                    "photo_private": reply.private,
                    "photo_root_id": root.comment_id,
                    "photo_root_uin": root.uin,
                },
            )
            thread.append(comment)
            comments.append(comment)
    return comments


def parse_qzone_photo(
    payload: dict[str, Any], *, album_id: str = "", pic_key: str = ""
) -> QzonePhoto | None:
    data = _mapping(payload.get("data"))
    photos = data.get("photos")
    photos = photos if isinstance(photos, list) else []
    topic = _mapping(data.get("topic"))
    if album_id or pic_key:
        photo = next(
            (
                item
                for item in photos
                if isinstance(item, dict)
                and str(item.get("albumId") or topic.get("topicId") or "").strip()
                == album_id
                and str(item.get("picKey") or item.get("lloc") or "").strip() == pic_key
            ),
            {},
        )
        if not photo:
            return None
        if "picPosInPage" in data:
            try:
                active_index = int(data["picPosInPage"])
            except (TypeError, ValueError):
                return None
            if not 0 <= active_index < len(photos) or photos[active_index] is not photo:
                return None
    else:
        photo = photos[0] if photos else {}
    photo = _mapping(photo)
    if not photo and not topic:
        return None

    album_id = str(photo.get("albumId") or topic.get("topicId") or "").strip()
    pic_key = str(photo.get("picKey") or photo.get("lloc") or "").strip()
    if not album_id or not pic_key:
        return None
    single = _mapping(data.get("single"))
    raw_comments = single.get("comments")
    raw_comments = (
        [item for item in raw_comments if isinstance(item, dict)]
        if isinstance(raw_comments, list)
        else []
    )
    comments = [_photo_comment(item) for item in raw_comments]
    for root, raw in zip(comments, raw_comments):
        replies = raw.get("replies")
        for item in replies if isinstance(replies, list) else []:
            if not isinstance(item, dict):
                continue
            reply = _photo_comment(item)
            reply.topic_id = reply.topic_id or root.topic_id
            reply.private = root.private or reply.private
            root.replies.append(reply)
    owner_uin = _safe_int(
        photo.get("ownerUin") or topic.get("ownerUin") or topic.get("loginUin")
    )
    owner_name = clean_qzone_text(
        photo.get("ownerName") or topic.get("ownerName") or owner_uin
    )
    batch_id = str(photo.get("batchId") or "").strip()
    batch_targets = []
    if batch_id:
        for item in photos:
            if (
                not isinstance(item, dict)
                or item.get("is_video")
                or str(item.get("albumId") or "").strip() != album_id
                or str(item.get("batchId") or "").strip() != batch_id
                or _safe_int(item.get("ownerUin")) != owner_uin
            ):
                continue
            key = str(item.get("picKey") or item.get("lloc") or "").strip()
            if key:
                batch_targets.append(
                    QzonePhoto(
                        album_id=album_id,
                        pic_key=key,
                        owner_uin=owner_uin,
                        batch_id=batch_id,
                        platform_sub_id=_safe_int(item.get("platformSubId")),
                    )
                )
    return QzonePhoto(
        album_id=album_id,
        pic_key=pic_key,
        topic_id=str(photo.get("topicId") or topic.get("topicId") or album_id).strip(),
        owner_uin=owner_uin,
        owner_name=owner_name,
        album_name=clean_qzone_text(photo.get("topicName") or topic.get("topicName")),
        name=clean_qzone_text(photo.get("name")),
        image_url=_photo_url(photo.get("url")),
        preview_url=_photo_url(photo.get("pre")),
        width=_safe_int(photo.get("width")),
        height=_safe_int(photo.get("height")),
        shoot_time=_safe_int(photo.get("shootTime")),
        upload_time=str(photo.get("uploadTime") or "").strip(),
        comment_total=_safe_int(photo.get("cmtTotal") or len(comments)),
        like_total=_safe_int(photo.get("likeTotal") or single.get("likeTotal")),
        comments=comments,
        batch_id=batch_id,
        platform_sub_id=_safe_int(photo.get("platformSubId")),
        batch_targets=batch_targets,
    )


def parse_qzone_photo_comment(
    payload: dict[str, Any], *, content: str, uin: int
) -> QzonePhotoComment:
    data = _mapping(payload.get("data"))
    return QzonePhotoComment(
        comment_id=str(data.get("id") or "").strip(),
        uin=uin,
        content=clean_qzone_text(data.get("content") or content),
        create_time=_safe_int(data.get("postTime")),
        topic_id=str(data.get("topicId") or "").strip(),
    )


__all__ = ["parse_qzone_photo", "parse_qzone_photo_comment"]

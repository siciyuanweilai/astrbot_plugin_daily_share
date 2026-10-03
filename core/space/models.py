from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote


def normalize_photo_comment_topic(album_id: str, pic_key: str, topic_id: str = "") -> str:
    canonical = f"{album_id}_{pic_key}_0_0"
    raw = str(topic_id or "").strip()
    if unquote(raw) in {"", album_id, f"{album_id}_{pic_key}", canonical}:
        return canonical
    return raw


@dataclass(slots=True)
class QzoneContext:
    uin: int
    skey: str
    p_skey: str
    nickname: str = ""
    cookie_values: dict[str, str] = field(default_factory=dict)

    @property
    def gtk(self) -> str:
        return self.gtk2

    @property
    def gtk2(self) -> str:
        value = 5381
        for ch in self.p_skey:
            value += (value << 5) + ord(ch)
        return str(value & 0x7FFFFFFF)

    @property
    def cookies(self) -> dict[str, str]:
        cookies = dict(self.cookie_values or {})
        cookies.update(
            {
                "uin": f"o{self.uin}",
                "skey": self.skey,
                "p_skey": self.p_skey,
            }
        )
        return cookies


@dataclass(slots=True)
class QzoneComment:
    uin: int = 0
    nickname: str = ""
    content: str = ""
    create_time: int = 0
    tid: str = ""
    submit_tid: str = ""
    raw_tid: str = ""
    parent_tid: str = ""
    reply_to_tid: str = ""
    raw_reply_to_tid: str = ""
    reply_to_uin: int = 0
    raw_reply_to_uin: int = 0
    reply_to_nickname: str = ""
    reply_to_tid_source: str = ""
    images: list[str] = field(default_factory=list)
    raw_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class QzonePhotoComment:
    """Comment attached to one Qzone photo."""

    comment_id: str = ""
    uin: int = 0
    nickname: str = ""
    content: str = ""
    create_time: int = 0
    topic_id: str = ""
    private: int = 0
    source: int = 0
    avatar_url: str = ""
    replies: list[QzonePhotoComment] = field(default_factory=list)


@dataclass(slots=True)
class QzonePhoto:
    """A photo and the comments returned by the Qzone photo viewer."""

    album_id: str = ""
    pic_key: str = ""
    topic_id: str = ""
    owner_uin: int = 0
    owner_name: str = ""
    album_name: str = ""
    name: str = ""
    image_url: str = ""
    preview_url: str = ""
    width: int = 0
    height: int = 0
    shoot_time: int = 0
    upload_time: str = ""
    comment_total: int = 0
    like_total: int = 0
    comments: list[QzonePhotoComment] = field(default_factory=list)
    feed_topic_id: str = ""
    batch_id: str = ""
    platform_sub_id: int | None = None
    batch_targets: list[QzonePhoto] = field(default_factory=list)
    unresolved_count: int = 0

    @property
    def key(self) -> str:
        return f"{self.album_id}:{self.pic_key}"

    @property
    def comment_topic_id(self) -> str:
        return f"{self.album_id}_{self.pic_key}"

    @property
    def feed_comment_topic_id(self) -> str:
        return normalize_photo_comment_topic(self.album_id, self.pic_key, self.feed_topic_id)


@dataclass(slots=True)
class QzonePost:
    tid: str = ""
    uin: int = 0
    name: str = ""
    text: str = ""
    images: list[str] = field(default_factory=list)
    videos: list[str] = field(default_factory=list)
    comments: list[QzoneComment] = field(default_factory=list)
    create_time: int = 0
    avatar_url: str = ""
    rt_con: str = ""
    rt_uin: int = 0
    rt_uinname: str = ""
    rt_tid: str = ""
    rt_images: list[str] = field(default_factory=list)
    expandable: bool = False
    appid: int = 311
    feed_key: str = ""
    curkey: str = ""
    unikey: str = ""
    liked: bool = False
    busi_param: dict[str, Any] = field(default_factory=dict)
    photo_targets: list[QzonePhoto] = field(default_factory=list)
    photo_batch_key: str = ""
    photo_batch_complete: bool = True

    @property
    def comment_target_error(self) -> str:
        if int(self.appid or 311) == 311:
            return ""
        if int(self.appid) != 4:
            return f"暂不支持该类型动态的评论（appid={self.appid}）"
        if not self.photo_targets:
            return "相册动态缺少明确的 albumId/picKey，不能作为普通说说评论"
        if len(self.photo_targets) != 1:
            return "相册动态包含多个照片目标，需指定要评论的照片"
        photo = self.photo_targets[0]
        if not photo.album_id or not photo.pic_key:
            return "相册动态缺少明确的 albumId/picKey"
        if photo.owner_uin and photo.owner_uin != self.uin:
            return "相册照片主人与动态作者不一致，不能自动选择评论目标"
        if photo.feed_comment_topic_id != f"{photo.comment_topic_id}_0_0":
            return "相册动态 topicId 与 albumId/picKey 不一致，不能自动评论"
        return ""

    @property
    def key(self) -> str:
        return f"{self.uin}:{self.tid}"

    def to_payload(self, *, self_uin: int = 0, include_comments: bool = False) -> dict:
        payload: dict[str, Any] = {
            "id": self.key,
            "tid": self.tid,
            "author": {
                "uin": self.uin,
                "nickname": self.name or str(self.uin or ""),
                "avatar": self.avatar_url,
            },
            "content": self.text or self.rt_con or "",
            "created_at": int(self.create_time or 0),
            "stats": {
                "likes": 0,
                "comments": len(self.comments or []),
            },
            "liked": bool(self.liked),
            "images": list(dict.fromkeys(self.images or [])),
            "videos": list(dict.fromkeys(self.videos or [])),
            "can_delete": bool(self_uin and int(self.uin or 0) == int(self_uin)),
            "expandable": bool(self.expandable),
        }
        if self.rt_con:
            payload["repost"] = {
                "uin": int(self.rt_uin or 0),
                "nickname": self.rt_uinname or str(self.rt_uin or ""),
                "tid": self.rt_tid,
                "content": self.rt_con,
                "images": list(dict.fromkeys(self.rt_images or [])),
            }
        if include_comments:
            comments = list(self.comments or [])
            comments_by_tid = {
                comment.tid: comment for comment in comments if comment.tid
            }
            payload["comments"] = []
            for index, comment in enumerate(comments, start=1):
                reply_to_id = comment.reply_to_tid or comment.parent_tid
                reply_to = comments_by_tid.get(reply_to_id)
                item = {
                    "id": comment.tid or str(index),
                    "author": {
                        "uin": comment.uin,
                        "nickname": comment.nickname or str(comment.uin or ""),
                    },
                    "content": comment.content,
                    "created_at": int(comment.create_time or 0),
                    "can_reply": bool(comment.tid and comment.uin),
                    "images": list(dict.fromkeys(comment.images or [])),
                }
                if comment.parent_tid:
                    item["parent_id"] = comment.parent_tid
                if reply_to_id:
                    item["reply_to"] = {
                        "id": reply_to_id,
                        "uin": comment.reply_to_uin
                        or (reply_to.uin if reply_to else 0),
                        "nickname": (
                            comment.reply_to_nickname
                            or (
                                (reply_to.nickname or str(reply_to.uin or ""))
                                if reply_to
                                else ""
                            )
                        ),
                    }
                payload["comments"].append(item)
        return payload

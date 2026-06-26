from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class QzoneContext:
    uin: int
    skey: str
    p_skey: str
    nickname: str = ""
    cookie_values: dict[str, str] = field(default_factory=dict)

    @property
    def gtk(self) -> str:
        value = 5381
        for ch in self.p_skey:
            value += (value << 5) + ord(ch)
        return str(value & 0x7FFFFFFF)

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
    raw_fields: dict[str, Any] = field(default_factory=dict)


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
    expandable: bool = False
    appid: int = 311
    feed_key: str = ""
    curkey: str = ""
    unikey: str = ""
    liked: bool = False
    busi_param: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.uin}:{self.tid}"

    def to_payload(self, *, self_uin: int = 0, include_comments: bool = False) -> dict:
        payload = {
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
        if include_comments:
            comments = list(self.comments or [])
            comments_by_tid = {comment.tid: comment for comment in comments if comment.tid}
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
                }
                if comment.parent_tid:
                    item["parent_id"] = comment.parent_tid
                if reply_to_id:
                    item["reply_to"] = {
                        "id": reply_to_id,
                        "uin": comment.reply_to_uin or (reply_to.uin if reply_to else 0),
                        "nickname": (
                            comment.reply_to_nickname
                            or ((reply_to.nickname or str(reply_to.uin or "")) if reply_to else "")
                        ),
                    }
                payload["comments"].append(item)
        return payload

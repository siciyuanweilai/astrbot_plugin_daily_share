from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from .models import QzoneComment, QzonePost

if TYPE_CHECKING:
    from .qzone import QzoneService


class QzoneFeedMergeService:
    def __init__(self, owner: QzoneService) -> None:
        self.owner = owner

    @classmethod
    def _merge_post_detail(cls, base: QzonePost, detail: QzonePost | None) -> QzonePost:
        from .qzone import QzoneService

        if detail is None:
            return base
        detail.feed_key = detail.feed_key or base.feed_key
        detail.curkey = base.curkey or detail.curkey
        detail.unikey = base.unikey or detail.unikey
        detail.busi_param = detail.busi_param or base.busi_param
        # 通用详情解析器默认使用 appid=311，保留动态明确提供的类型和目标。
        if int(base.appid or 311) != 311:
            detail.appid = base.appid
        photos = {}
        for photo in base.photo_targets + detail.photo_targets:
            key = (photo.owner_uin, photo.album_id, photo.pic_key)
            previous = photos.get(key)
            if previous and not photo.feed_topic_id:
                photo.feed_topic_id = previous.feed_topic_id
            photos[key] = photo
        detail.photo_targets = list(photos.values())
        detail.comments = QzoneService._merge_comments(base.comments, detail.comments)
        detail.images = detail.images or base.images
        detail.videos = detail.videos or base.videos
        detail.text = detail.text or base.text
        detail.name = detail.name or base.name
        detail.avatar_url = detail.avatar_url or base.avatar_url
        detail.rt_con = detail.rt_con or base.rt_con
        detail.rt_uin = detail.rt_uin or base.rt_uin
        detail.rt_uinname = detail.rt_uinname or base.rt_uinname
        detail.rt_tid = detail.rt_tid or base.rt_tid
        detail.rt_images = detail.rt_images or base.rt_images
        detail.expandable = bool(detail.expandable or base.expandable)
        detail.liked = bool(detail.liked or base.liked)
        return detail

    @classmethod
    def _merge_comments(
        cls, base_comments: list[QzoneComment], detail_comments: list[QzoneComment]
    ) -> list[QzoneComment]:
        from .qzone import QzoneService

        base = list(base_comments or [])
        detail = list(detail_comments or [])
        if not base:
            return detail
        if not detail:
            return base

        detail_by_tid = {
            str(comment.tid or "").strip(): comment
            for comment in detail
            if str(comment.tid or "").strip()
        }
        detail_by_submit_tid = {
            str(comment.submit_tid or "").strip(): comment
            for comment in detail
            if str(comment.submit_tid or "").strip()
        }
        merged_by_id: dict[int, QzoneComment] = {}
        parent_aliases: dict[str, str] = {}
        seen: set[str] = set()
        used_detail: set[int] = set()
        # 先合并一级评论，建立详情接口真实编号到原楼层编号的映射。
        for comment in sorted(base, key=lambda item: bool(item.parent_tid)):
            tid = str(comment.tid or "").strip()
            matched = QzoneService._match_detail_comment(
                comment,
                detail,
                detail_by_tid=detail_by_tid,
                detail_by_submit_tid=detail_by_submit_tid,
                used_detail=used_detail,
                parent_aliases=parent_aliases,
            )
            if matched is not None:
                merged_by_id[id(comment)] = QzoneService._merge_comment(
                    comment, matched
                )
                if not comment.parent_tid:
                    for alias in (matched.tid, matched.submit_tid, matched.raw_tid):
                        if alias:
                            parent_aliases[str(alias)] = tid
            else:
                merged_by_id[id(comment)] = comment
            if tid:
                seen.add(tid)

        merged = [merged_by_id[id(comment)] for comment in base]
        for comment in detail:
            if id(comment) in used_detail:
                continue
            tid = str(comment.tid or "").strip()
            if not tid or tid not in seen:
                comment = replace(
                    comment,
                    parent_tid=parent_aliases.get(
                        comment.parent_tid, comment.parent_tid
                    ),
                    reply_to_tid=parent_aliases.get(
                        comment.reply_to_tid, comment.reply_to_tid
                    ),
                )
                merged.append(comment)
                if tid:
                    seen.add(tid)
        return merged

    @classmethod
    def _match_detail_comment(
        cls,
        base_comment: QzoneComment,
        detail_comments: list[QzoneComment],
        *,
        detail_by_tid: dict[str, QzoneComment],
        detail_by_submit_tid: dict[str, QzoneComment],
        used_detail: set[int],
        parent_aliases: dict[str, str] | None = None,
    ) -> QzoneComment | None:
        from .qzone import QzoneService

        direct_matches = (
            detail_by_tid.get(str(base_comment.tid or "").strip()),
            detail_by_submit_tid.get(str(base_comment.submit_tid or "").strip()),
        )
        for candidate in direct_matches:
            if candidate is None or id(candidate) in used_detail:
                continue
            if not cls._comment_identity_compatible(
                base_comment, candidate, parent_aliases
            ):
                continue
            if (
                str(base_comment.tid or "") != str(candidate.tid or "")
                and QzoneService._comment_submit_tid_rank(
                    str(base_comment.submit_tid or "")
                )
                < 2
                and not QzoneService._comments_equivalent(base_comment, candidate)
            ):
                continue
            used_detail.add(id(candidate))
            return candidate

        for candidate in detail_comments:
            if id(candidate) in used_detail:
                continue
            if cls._comment_identity_compatible(
                base_comment, candidate, parent_aliases
            ) and QzoneService._comments_equivalent(base_comment, candidate):
                used_detail.add(id(candidate))
                return candidate
        return None

    @staticmethod
    def _comment_identity_compatible(
        left: QzoneComment,
        right: QzoneComment,
        parent_aliases: dict[str, str] | None,
    ) -> bool:
        if left.uin and right.uin and int(left.uin) != int(right.uin):
            return False
        left_parent = str(left.parent_tid or "").strip()
        right_parent = str(right.parent_tid or "").strip()
        right_parent = (parent_aliases or {}).get(right_parent, right_parent)
        # 短 submit_tid 只在自己的评论楼内有效，不可跨作者、跨楼或跨层级合并。
        return left_parent == right_parent

    @staticmethod
    def _comments_equivalent(left: QzoneComment, right: QzoneComment) -> bool:
        if int(left.uin or 0) != int(right.uin or 0):
            return False
        if str(left.content or "").strip() != str(right.content or "").strip():
            return False
        if bool(str(left.parent_tid or "").strip()) != bool(
            str(right.parent_tid or "").strip()
        ):
            return False
        if int(left.reply_to_uin or 0) and int(right.reply_to_uin or 0):
            if int(left.reply_to_uin or 0) != int(right.reply_to_uin or 0):
                return False
        left_time = int(left.create_time or 0)
        right_time = int(right.create_time or 0)
        if left_time and right_time and abs(left_time - right_time) > 5:
            return False
        return True

    @staticmethod
    def _comment_submit_tid_rank(value: str) -> int:
        text = str(value or "").strip()
        if not text:
            return -1
        if "_r_" in text:
            return 0
        if text.isdigit() and len(text) <= 6:
            return 1
        return 2

    @classmethod
    def _prefer_submit_tid(cls, *values: str) -> str:
        from .qzone import QzoneService

        best = ""
        best_rank = -1
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            rank = QzoneService._comment_submit_tid_rank(text)
            if rank > best_rank:
                best = text
                best_rank = rank
        return best

    @classmethod
    def _merge_comment(
        cls, base_comment: QzoneComment, detail_comment: QzoneComment
    ) -> QzoneComment:
        from .qzone import QzoneService

        raw_fields = dict(getattr(base_comment, "raw_fields", {}) or {})
        raw_fields.update(dict(getattr(detail_comment, "raw_fields", {}) or {}))
        return QzoneComment(
            uin=int(detail_comment.uin or base_comment.uin or 0),
            nickname=str(detail_comment.nickname or base_comment.nickname or ""),
            content=str(detail_comment.content or base_comment.content or ""),
            create_time=int(
                detail_comment.create_time or base_comment.create_time or 0
            ),
            tid=str(base_comment.tid or detail_comment.tid or ""),
            submit_tid=QzoneService._prefer_submit_tid(
                str(detail_comment.submit_tid or ""),
                str(detail_comment.tid or ""),
                str(base_comment.submit_tid or ""),
                str(base_comment.tid or ""),
            ),
            raw_tid=str(detail_comment.raw_tid or base_comment.raw_tid or ""),
            parent_tid=str(base_comment.parent_tid or detail_comment.parent_tid or ""),
            reply_to_tid=str(
                base_comment.reply_to_tid or detail_comment.reply_to_tid or ""
            ),
            raw_reply_to_tid=str(
                detail_comment.raw_reply_to_tid or base_comment.raw_reply_to_tid or ""
            ),
            reply_to_uin=int(
                detail_comment.reply_to_uin or base_comment.reply_to_uin or 0
            ),
            raw_reply_to_uin=int(
                detail_comment.raw_reply_to_uin or base_comment.raw_reply_to_uin or 0
            ),
            reply_to_nickname=str(
                detail_comment.reply_to_nickname or base_comment.reply_to_nickname or ""
            ),
            reply_to_tid_source=str(
                detail_comment.reply_to_tid_source
                or base_comment.reply_to_tid_source
                or ""
            ),
            images=list(
                dict.fromkeys(
                    (detail_comment.images or []) + (base_comment.images or [])
                )
            ),
            raw_fields=raw_fields,
        )

from __future__ import annotations

from .models import QzoneComment, QzonePost


class QzoneFeedMergeMixin:
    @classmethod
    def _merge_post_detail(cls, base: QzonePost, detail: QzonePost | None) -> QzonePost:
        if detail is None:
            return base
        detail.feed_key = detail.feed_key or base.feed_key
        detail.curkey = detail.curkey or base.curkey
        detail.unikey = detail.unikey or base.unikey
        detail.busi_param = detail.busi_param or base.busi_param
        detail.comments = cls._merge_comments(base.comments, detail.comments)
        detail.images = detail.images or base.images
        detail.videos = detail.videos or base.videos
        detail.text = detail.text or base.text
        detail.name = detail.name or base.name
        detail.avatar_url = detail.avatar_url or base.avatar_url
        detail.rt_con = detail.rt_con or base.rt_con
        detail.expandable = bool(detail.expandable or base.expandable)
        detail.liked = bool(detail.liked or base.liked)
        return detail

    @classmethod
    def _merge_comments(cls, base_comments: list[QzoneComment], detail_comments: list[QzoneComment]) -> list[QzoneComment]:
        base = list(base_comments or [])
        detail = list(detail_comments or [])
        if not base:
            return detail
        if not detail:
            return base

        detail_by_tid = {str(comment.tid or "").strip(): comment for comment in detail if str(comment.tid or "").strip()}
        detail_by_submit_tid = {
            str(comment.submit_tid or "").strip(): comment for comment in detail if str(comment.submit_tid or "").strip()
        }
        merged: list[QzoneComment] = []
        seen: set[str] = set()
        used_detail: set[int] = set()
        for comment in base:
            tid = str(comment.tid or "").strip()
            matched = cls._match_detail_comment(
                comment,
                detail,
                detail_by_tid=detail_by_tid,
                detail_by_submit_tid=detail_by_submit_tid,
                used_detail=used_detail,
            )
            if matched is not None:
                merged.append(cls._merge_comment(comment, matched))
            else:
                merged.append(comment)
            if tid:
                seen.add(tid)

        for comment in detail:
            if id(comment) in used_detail:
                continue
            tid = str(comment.tid or "").strip()
            if not tid or tid not in seen:
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
    ) -> QzoneComment | None:
        direct_matches = (
            detail_by_tid.get(str(base_comment.tid or "").strip()),
            detail_by_submit_tid.get(str(base_comment.submit_tid or "").strip()),
        )
        for candidate in direct_matches:
            if candidate is not None and id(candidate) not in used_detail:
                used_detail.add(id(candidate))
                return candidate

        for candidate in detail_comments:
            if id(candidate) in used_detail:
                continue
            if cls._comments_equivalent(base_comment, candidate):
                used_detail.add(id(candidate))
                return candidate
        return None

    @staticmethod
    def _comments_equivalent(left: QzoneComment, right: QzoneComment) -> bool:
        if int(left.uin or 0) != int(right.uin or 0):
            return False
        if str(left.content or "").strip() != str(right.content or "").strip():
            return False
        if bool(str(left.parent_tid or "").strip()) != bool(str(right.parent_tid or "").strip()):
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
        best = ""
        best_rank = -1
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            rank = cls._comment_submit_tid_rank(text)
            if rank > best_rank:
                best = text
                best_rank = rank
        return best

    @classmethod
    def _merge_comment(cls, base_comment: QzoneComment, detail_comment: QzoneComment) -> QzoneComment:
        raw_fields = dict(getattr(base_comment, "raw_fields", {}) or {})
        raw_fields.update(dict(getattr(detail_comment, "raw_fields", {}) or {}))
        return QzoneComment(
            uin=int(detail_comment.uin or base_comment.uin or 0),
            nickname=str(detail_comment.nickname or base_comment.nickname or ""),
            content=str(detail_comment.content or base_comment.content or ""),
            create_time=int(detail_comment.create_time or base_comment.create_time or 0),
            tid=str(base_comment.tid or detail_comment.tid or ""),
            submit_tid=cls._prefer_submit_tid(
                str(detail_comment.submit_tid or ""),
                str(detail_comment.tid or ""),
                str(base_comment.submit_tid or ""),
                str(base_comment.tid or ""),
            ),
            raw_tid=str(detail_comment.raw_tid or base_comment.raw_tid or ""),
            parent_tid=str(base_comment.parent_tid or detail_comment.parent_tid or ""),
            reply_to_tid=str(base_comment.reply_to_tid or detail_comment.reply_to_tid or ""),
            raw_reply_to_tid=str(detail_comment.raw_reply_to_tid or base_comment.raw_reply_to_tid or ""),
            reply_to_uin=int(detail_comment.reply_to_uin or base_comment.reply_to_uin or 0),
            raw_reply_to_uin=int(detail_comment.raw_reply_to_uin or base_comment.raw_reply_to_uin or 0),
            reply_to_nickname=str(detail_comment.reply_to_nickname or base_comment.reply_to_nickname or ""),
            reply_to_tid_source=str(detail_comment.reply_to_tid_source or base_comment.reply_to_tid_source or ""),
            raw_fields=raw_fields,
        )

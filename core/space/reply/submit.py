from __future__ import annotations

import time
from typing import Any

from ..models import QzoneComment, QzoneContext, QzonePost


QZONE_BASE_URL = "https://user.qzone.qq.com"


class QzoneReplySubmitMixin:
    def _reply_submit_plans(
        self,
        ctx: QzoneContext,
        post: QzonePost,
        comment: QzoneComment,
        *,
        content: str,
        parent_comment: QzoneComment | None,
        reply_targets: list[dict[str, Any]],
        prefer_h5: bool,
    ) -> list[dict[str, Any]]:
        if parent_comment is not None:
            if int(getattr(post, "uin", 0) or 0) != int(ctx.uin or 0) and int(getattr(parent_comment, "uin", 0) or 0) == int(ctx.uin or 0):
                variants = self._thread_reply_re_feeds_payload_variants(post, comment, parent_comment, reply_targets)
                if variants:
                    return [
                        self._reply_submit_plan(
                            ctx,
                            post,
                            comment,
                            content=content,
                            transport="h5_re_feeds_parent",
                            variant=variant,
                        )
                        for variant in variants
                    ]
            variants = self._thread_reply_payload_variants(post, comment, parent_comment, reply_targets)
            return [
                self._reply_submit_plan(
                    ctx,
                    post,
                    comment,
                    content=content,
                    transport="addreply_ugc",
                    variant=variant,
                )
                for variant in variants
            ]

        transports = ("h5", "pc") if prefer_h5 else ("pc", "h5")
        plans: list[dict[str, Any]] = []
        for target in reply_targets:
            target_id = str((target or {}).get("comment_id") or "").strip()
            target_uin = int((target or {}).get("comment_uin") or getattr(comment, "uin", 0) or 0)
            for transport in transports:
                plans.append(
                    self._reply_submit_plan(
                        ctx,
                        post,
                        comment,
                        content=content,
                        transport=transport,
                        variant={
                            "name": "target",
                            "comment_id": target_id,
                            "comment_uin": target_uin,
                            "payload_comment_id": target_id,
                            "payload_t2_tid": target_id,
                        },
                    )
                )
        return plans

    @classmethod
    def _thread_reply_payload_variants(
        cls,
        post: QzonePost,
        comment: QzoneComment,
        parent_comment: QzoneComment,
        reply_targets: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        submit_tid = str(getattr(comment, "submit_tid", "") or "").strip()
        raw_tid = str(getattr(comment, "raw_tid", "") or "").strip()
        parent_tid = str(
            getattr(parent_comment, "submit_tid", "")
            or getattr(parent_comment, "tid", "")
            or getattr(comment, "parent_tid", "")
            or ""
        ).strip()
        post_tid = str(getattr(post, "tid", "") or "").strip()
        if not parent_tid or parent_tid == post_tid:
            return []

        target = next(
            (
                target
                for target in reply_targets or []
                if str((target or {}).get("comment_id") or "").strip()
            ),
            None,
        )
        target_id = str((target or {}).get("comment_id") or "").strip()
        target_uin = int((target or {}).get("comment_uin") or getattr(comment, "uin", 0) or 0)
        parent_ids = cls._comment_id_aliases(parent_comment)
        parent_ids.update(
            value
            for value in (
                parent_tid,
                str(getattr(comment, "parent_tid", "") or "").strip(),
            )
            if value
        )
        if not target_id or target_id == post_tid or target_id in parent_ids or not target_uin:
            return []

        child_seq = submit_tid or raw_tid
        unsafe_reason = cls._unsafe_thread_reply_target_reason(comment, parent_comment=parent_comment)
        if unsafe_reason and not cls._can_try_addreply_ugc_thread_variant(
            post,
            comment,
            parent_comment=parent_comment,
            child_seq=child_seq,
        ):
            return []

        return [
            {
                "name": "pc_addreply_ugc_parent",
                "comment_id": target_id,
                "comment_uin": target_uin,
                "payload_comment_id": parent_tid,
                "payload_t2_tid": target_id,
                "payload_t2_uin": target_uin,
                "reply_uin": target_uin,
                "topic_id": f"{post.uin}_{post.tid}",
                "thread": True,
            }
        ]

    @staticmethod
    def _thread_reply_re_feeds_payload_variants(
        post: QzonePost,
        comment: QzoneComment,
        parent_comment: QzoneComment,
        reply_targets: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        parent_tid = str(
            getattr(parent_comment, "submit_tid", "")
            or getattr(parent_comment, "tid", "")
            or getattr(comment, "parent_tid", "")
            or ""
        ).strip()
        parent_uin = int(getattr(parent_comment, "uin", 0) or 0)
        post_tid = str(getattr(post, "tid", "") or "").strip()
        if not parent_tid or parent_tid == post_tid or not parent_uin:
            return []

        target = next(
            (
                target
                for target in reply_targets or []
                if str((target or {}).get("comment_id") or "").strip()
            ),
            None,
        )
        target_id = str((target or {}).get("comment_id") or "").strip()
        target_uin = int((target or {}).get("comment_uin") or getattr(comment, "uin", 0) or 0)
        if not target_id or not target_uin:
            return []

        return [
            {
                "name": "h5_re_feeds_parent",
                "comment_id": target_id,
                "comment_uin": target_uin,
                "payload_comment_id": parent_tid,
                "payload_comment_uin": parent_uin,
                "topic_id": f"{post.uin}_{post.tid}__1",
                "qzreferrer": f"{QZONE_BASE_URL}/{post.uin}",
                "thread": True,
            }
        ]

    def _reply_submit_plan(
        self,
        ctx: QzoneContext,
        post: QzonePost,
        comment: QzoneComment,
        *,
        content: str,
        transport: str,
        variant: dict[str, Any],
    ) -> dict[str, Any]:
        comment_id = str((variant or {}).get("comment_id") or "").strip()
        comment_uin = int((variant or {}).get("comment_uin") or getattr(comment, "uin", 0) or 0)
        payload_comment_id = str((variant or {}).get("payload_comment_id") or comment_id).strip()
        payload_comment_uin = int((variant or {}).get("payload_comment_uin") or comment_uin or 0)
        payload_t2_tid = str((variant or {}).get("payload_t2_tid") or payload_comment_id).strip()
        payload_t2_uin = int((variant or {}).get("payload_t2_uin") or comment_uin or 0)
        reply_uin = int((variant or {}).get("reply_uin") or payload_t2_uin or comment_uin or 0)
        topic_id = str((variant or {}).get("topic_id") or "")
        if transport == "sns":
            data = self._sns_comment_data(
                ctx,
                post,
                content=content,
                comment_id=comment_id,
                comment_uin=comment_uin,
                comment=comment,
                payload_comment_id=payload_comment_id,
                payload_t2_tid=payload_t2_tid,
                payload_t2_uin=payload_t2_uin,
                reply_uin=reply_uin,
                topic_id=topic_id,
            )
            url = self.SNS_COMMENT_URL
            headers = self._comment_sns_headers(ctx, referer=f"{self.BASE_URL}/{post.uin}/mood/{post.tid}")
        elif transport == "h5_re_feeds_parent":
            data = self._h5_thread_parent_comment_data(
                ctx,
                post,
                content=content,
                comment_id=payload_comment_id,
                comment_uin=payload_comment_uin,
                topic_id=topic_id,
                qzreferrer=str((variant or {}).get("qzreferrer") or ""),
            )
            url = self.H5_COMMENT_URL
            headers = self._comment_h5_headers(ctx, referer=str(data.get("qzreferrer") or ""))
        elif transport == "addreply_ugc":
            data = self._addreply_ugc_comment_data(
                ctx,
                post,
                content=content,
                comment_id=comment_id,
                comment_uin=comment_uin,
                payload_comment_id=payload_comment_id,
                topic_id=topic_id,
            )
            url = self.ADD_REPLY_UGC_URL
            headers = self._pc_form_headers(ctx, referer=str(data.get("qzreferrer") or ""))
        elif transport == "h5":
            data = self._h5_comment_data(
                ctx,
                post,
                content=content,
                comment_id=comment_id,
                comment_uin=comment_uin,
                comment=comment,
                payload_comment_id=payload_comment_id,
                payload_t2_tid=payload_t2_tid,
                payload_t2_uin=payload_t2_uin,
                reply_uin=reply_uin,
                topic_id=topic_id,
            )
            url = self.H5_COMMENT_URL
            headers = self._comment_h5_headers(ctx, referer=f"{self.H5_ORIGIN}/{post.uin}/mood/{post.tid}")
        else:
            data = {
                "hostUin": post.uin,
                "topicId": topic_id or f"{post.uin}_{post.tid}",
                "content": content,
                "format": "json",
                "qzreferrer": f"{self.BASE_URL}/{ctx.uin}",
            }
            if comment_uin:
                data.update(
                    commentId=payload_comment_id,
                    commentUin=comment_uin,
                    replyUin=reply_uin,
                )
            if payload_t2_tid and comment_uin and bool((variant or {}).get("thread")):
                data.update(t1_uin=post.uin, t1_tid=post.tid, t2_tid=payload_t2_tid, t2_uin=payload_t2_uin)
            url = self.COMMENT_URL
            headers = None
        return {
            "transport": transport,
            "variant": str((variant or {}).get("name") or ""),
            "comment_id": comment_id,
            "comment_uin": comment_uin,
            "url": url,
            "headers": headers,
            "data": data,
        }

    @staticmethod
    def _prefer_h5_reply(comment: QzoneComment, *, parent_comment: QzoneComment | None = None) -> bool:
        return bool(
            str(getattr(comment, "submit_tid", "") or "").strip()
            or (
                parent_comment is not None
                and str(getattr(comment, "parent_tid", "") or "").strip()
            )
        )

    @classmethod
    def _can_try_addreply_ugc_thread_variant(
        cls,
        post: QzonePost,
        comment: QzoneComment,
        *,
        parent_comment: QzoneComment,
        child_seq: str,
    ) -> bool:
        child_seq = str(child_seq or "").strip()
        if not cls._is_short_numeric_comment_id(child_seq):
            return False
        try:
            if int(child_seq) <= 0:
                return False
        except ValueError:
            return False
        parent_ids = cls._comment_id_aliases(parent_comment)
        post_uin = int(getattr(post, "uin", 0) or 0)
        parent_uin = int(getattr(parent_comment, "uin", 0) or 0)
        reply_to_uin = int(getattr(comment, "reply_to_uin", 0) or getattr(comment, "raw_reply_to_uin", 0) or 0)
        known_self_uins = {uin for uin in (post_uin, parent_uin) if uin}
        if reply_to_uin and reply_to_uin not in known_self_uins:
            return False
        self_uin = reply_to_uin or post_uin
        if not self_uin:
            return False
        reply_to_tid = str(getattr(comment, "reply_to_tid", "") or "").strip()
        parent_tid = str(getattr(comment, "parent_tid", "") or "").strip()
        if not parent_tid:
            parent_tid = str(getattr(parent_comment, "submit_tid", "") or getattr(parent_comment, "tid", "") or "").strip()
        if parent_uin == self_uin and (not reply_to_tid or reply_to_tid in parent_ids):
            return True
        saw_self_reply_under_parent = False
        for item in getattr(post, "comments", []) or []:
            if int(getattr(item, "uin", 0) or 0) != self_uin:
                continue
            if parent_tid and str(getattr(item, "parent_tid", "") or "").strip() != parent_tid:
                continue
            saw_self_reply_under_parent = True
            if reply_to_tid in cls._comment_id_aliases(item):
                return True
        if reply_to_tid and reply_to_tid not in parent_ids:
            return False
        return saw_self_reply_under_parent and reply_to_uin == self_uin

    @staticmethod
    def _reply_submit_targets(
        post: QzonePost,
        comment: QzoneComment,
        *,
        parent_comment: QzoneComment | None = None,
    ) -> list[dict[str, Any]]:
        post_tid = str(getattr(post, "tid", "") or "").strip()
        comment_tid = str(getattr(comment, "tid", "") or "").strip()
        comment_submit_tid = str(getattr(comment, "submit_tid", "") or "").strip()
        comment_uin = int(getattr(comment, "uin", 0) or 0)
        parent_tid = str(
            getattr(parent_comment, "submit_tid", "")
            or getattr(parent_comment, "tid", "")
            or getattr(comment, "parent_tid", "")
            or ""
        ).strip()
        parent_uin = int(getattr(parent_comment, "uin", 0) or 0)
        if parent_tid == post_tid:
            parent_tid = ""

        targets: list[dict[str, Any]] = []

        def add(comment_id: str, comment_uin_value: int) -> None:
            comment_id = str(comment_id or "").strip()
            if not comment_id:
                return
            key = (comment_id, int(comment_uin_value or 0))
            if any((item["comment_id"], item["comment_uin"]) == key for item in targets):
                return
            targets.append({"comment_id": comment_id, "comment_uin": int(comment_uin_value or 0)})

        add(comment_tid, comment_uin)
        if comment_submit_tid and comment_tid and comment_tid != comment_submit_tid:
            add(comment_submit_tid, comment_uin)
        elif comment_submit_tid and not comment_tid:
            add(comment_submit_tid, comment_uin)
        if parent_comment is None and parent_tid:
            add(parent_tid, parent_uin or comment_uin)
        return targets

    @classmethod
    def _filter_thread_reply_targets(
        cls,
        post: QzonePost,
        comment: QzoneComment,
        *,
        parent_comment: QzoneComment | None,
        targets: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        comment_ids = {
            str(getattr(comment, "tid", "") or "").strip(),
            str(getattr(comment, "submit_tid", "") or "").strip(),
        }
        comment_ids.discard("")
        blocked_ids = {
            str(getattr(post, "tid", "") or "").strip(),
            str(getattr(parent_comment, "tid", "") or "").strip(),
            str(getattr(parent_comment, "submit_tid", "") or "").strip(),
            str(getattr(comment, "parent_tid", "") or "").strip(),
        }
        blocked_ids.discard("")

        filtered: list[dict[str, Any]] = []
        for target in targets or []:
            comment_id = str((target or {}).get("comment_id") or "").strip()
            if not comment_id or comment_id in blocked_ids:
                continue
            if parent_comment is not None and cls._is_short_numeric_comment_id(comment_id):
                continue
            if comment_ids and comment_id not in comment_ids:
                continue
            comment_uin = int((target or {}).get("comment_uin") or 0)
            key = (comment_id, comment_uin)
            if any((item["comment_id"], item["comment_uin"]) == key for item in filtered):
                continue
            filtered.append({"comment_id": comment_id, "comment_uin": comment_uin})
        return filtered

    @classmethod
    def unsafe_thread_reply_target_reason(
        cls,
        comment: QzoneComment,
        *,
        parent_comment: QzoneComment | None,
    ) -> str:
        return cls._unsafe_thread_reply_target_reason(comment, parent_comment=parent_comment)

    def has_thread_reply_submit_plan(
        self,
        post: QzonePost,
        comment: QzoneComment,
        *,
        parent_comment: QzoneComment | None,
    ) -> bool:
        if parent_comment is None:
            return False
        try:
            targets = self._reply_submit_targets(post, comment, parent_comment=parent_comment)
            targets = self._filter_thread_reply_targets(
                post,
                comment,
                parent_comment=parent_comment,
                targets=targets,
            )
            return bool(self._thread_reply_payload_variants(post, comment, parent_comment, targets))
        except Exception:
            return False

    @classmethod
    def _unsafe_thread_reply_target_reason(
        cls,
        comment: QzoneComment,
        *,
        parent_comment: QzoneComment | None,
    ) -> str:
        if parent_comment is None:
            return ""
        comment_tid = str(getattr(comment, "tid", "") or "").strip()
        parent_tid = str(getattr(comment, "parent_tid", "") or "").strip()
        submit_tid = str(getattr(comment, "submit_tid", "") or "").strip()
        raw_tid = str(getattr(comment, "raw_tid", "") or "").strip()
        parent_ids = cls._comment_id_aliases(parent_comment)
        parent_ids.update(text for text in (parent_tid,) if text)
        if not comment_tid or "_r_" not in comment_tid or not parent_ids:
            return ""
        if parent_tid and not any(comment_tid.startswith(f"{parent_id}_r_") for parent_id in parent_ids):
            return ""
        if not cls._is_short_numeric_comment_id(submit_tid or raw_tid):
            return ""
        if submit_tid and submit_tid != raw_tid and raw_tid and not cls._is_short_numeric_comment_id(raw_tid):
            return ""
        return "synthetic_thread_tid_without_real_submit_id"

    @classmethod
    def _h5_reply_target_id(cls, comment_id: str, comment: QzoneComment | None) -> str:
        comment_id = str(comment_id or "").strip()
        if comment is None:
            return comment_id
        submit_tid = str(getattr(comment, "submit_tid", "") or "").strip()
        comment_tid = str(getattr(comment, "tid", "") or "").strip()
        parent_tid = str(getattr(comment, "parent_tid", "") or "").strip()
        if submit_tid and comment_id == submit_tid:
            return submit_tid
        if submit_tid and parent_tid and comment_id == comment_tid:
            if cls._is_short_numeric_comment_id(submit_tid):
                return comment_id
            if submit_tid == parent_tid:
                return comment_id
            return submit_tid
        return comment_id

    @staticmethod
    def _is_short_numeric_comment_id(value: str) -> bool:
        text = str(value or "").strip()
        return bool(text and text.isdigit() and len(text) <= 6)

    def _mood_v6_referrer(self, post: QzonePost) -> str:
        return (
            f"{self.BASE_URL}/proxy/domain/qzonestyle.gtimg.cn/qzone/app/mood_v6/html/index.html"
            f"#mood&g_iframeUser=1&g_iframedescend=1&uin={post.uin}&pfid=2&qz_ver=8"
            f"&appcanvas=0&qz_style=1&params=&entertime={int(time.time() * 1000)}"
            "&canvastype=&cdn_use_https=1"
        )

    def _h5_comment_data(
        self,
        ctx: QzoneContext,
        post: QzonePost,
        *,
        content: str,
        comment_id: str = "",
        comment_uin: int = 0,
        comment: QzoneComment | None = None,
        payload_comment_id: str = "",
        payload_t2_tid: str = "",
        payload_t2_uin: int = 0,
        reply_uin: int = 0,
        topic_id: str = "",
    ) -> dict[str, Any]:
        target_comment_id = str(payload_comment_id or "").strip() or self._h5_reply_target_id(comment_id, comment)
        target_t2_tid = str(payload_t2_tid or "").strip() or target_comment_id
        target_t2_uin = int(payload_t2_uin or comment_uin or 0)
        is_reply = bool(target_comment_id and comment_uin)
        data: dict[str, Any] = {
            "topicId": topic_id or f"{post.uin}_{post.tid}__1",
            "uin": ctx.uin,
            "hostUin": post.uin,
            "feedsType": 100,
            "inCharset": "utf-8",
            "outCharset": "utf-8",
            "plat": "qzone",
            "source": "ic",
            "platformid": 50,
            "format": "fs",
            "ref": "feeds",
            "content": content,
            "private": 0,
            "paramstr": "2" if is_reply else "1",
            "isSignIn": "",
            "appid": post.appid or 311,
            "richval": "",
            "richtype": "",
            "qzreferrer": f"{self.BASE_URL}/{post.uin}/mood/{post.tid}",
        }
        if target_comment_id:
            data.update(
                commentId=target_comment_id,
            )
            if is_reply:
                data.update(t1_uin=post.uin, t1_tid=post.tid, t2_tid=target_t2_tid)
        if comment_uin:
            data.update(
                commentUin=comment_uin,
            )
            if is_reply:
                data.update(
                    t2_uin=target_t2_uin,
                )
        return data

    def _h5_thread_parent_comment_data(
        self,
        ctx: QzoneContext,
        post: QzonePost,
        *,
        content: str,
        comment_id: str,
        comment_uin: int,
        topic_id: str = "",
        qzreferrer: str = "",
    ) -> dict[str, Any]:
        return {
            "topicId": topic_id or f"{post.uin}_{post.tid}__1",
            "feedsType": 100,
            "inCharset": "utf-8",
            "outCharset": "utf-8",
            "plat": "qzone",
            "source": "ic",
            "hostUin": post.uin,
            "isSignIn": "",
            "platformid": 50,
            "uin": ctx.uin,
            "format": "fs",
            "ref": "feeds",
            "content": content,
            "commentId": str(comment_id or "").strip(),
            "commentUin": int(comment_uin or 0),
            "richval": "",
            "richtype": "",
            "private": 0,
            "paramstr": "2",
            "qzreferrer": qzreferrer or f"{self.BASE_URL}/{post.uin}",
        }

    def _addreply_ugc_comment_data(
        self,
        ctx: QzoneContext,
        post: QzonePost,
        *,
        content: str,
        comment_id: str,
        comment_uin: int,
        payload_comment_id: str = "",
        topic_id: str = "",
    ) -> dict[str, Any]:
        target_comment_id = str(payload_comment_id or comment_id or "").strip()
        return {
            "uin": ctx.uin,
            "hostUin": post.uin,
            "topicId": topic_id or f"{post.uin}_{post.tid}",
            "commentId": target_comment_id,
            "commentUin": int(comment_uin or 0),
            "content": content,
            "inCharset": "",
            "outCharset": "",
            "ref": "",
            "private": 0,
            "with_fwd": 0,
            "to_tweet": 0,
            "hostuin": post.uin,
            "code_version": 1,
            "format": "fs",
            "qzreferrer": self._mood_v6_referrer(post),
        }

    def _sns_comment_data(
        self,
        ctx: QzoneContext,
        post: QzonePost,
        *,
        content: str,
        comment_id: str,
        comment_uin: int,
        comment: QzoneComment | None = None,
        payload_comment_id: str = "",
        payload_t2_tid: str = "",
        payload_t2_uin: int = 0,
        reply_uin: int = 0,
        topic_id: str = "",
    ) -> dict[str, Any]:
        target_comment_id = str(comment_id or "").strip()
        target_submit_id = str(payload_t2_tid or "").strip() or self._h5_reply_target_id(target_comment_id, comment)
        submit_comment_id = str(payload_comment_id or "").strip() or target_submit_id or target_comment_id
        target_t2_uin = int(payload_t2_uin or comment_uin or 0)
        target_reply_uin = int(reply_uin or target_t2_uin or comment_uin or 0)
        data: dict[str, Any] = {
            "topicId": topic_id or f"{post.uin}_{post.tid}",
            "uin": ctx.uin,
            "hostUin": post.uin,
            "feedsType": 100,
            "inCharset": "utf-8",
            "outCharset": "utf-8",
            "plat": "qzone",
            "source": "ic",
            "platformid": 50,
            "format": "fs",
            "ref": "feeds",
            "content": content,
            "private": 0,
            "paramstr": "2",
            "isSignIn": "",
            "appid": post.appid or 311,
            "richval": "",
            "richtype": "",
            "qzreferrer": f"{self.BASE_URL}/{post.uin}/mood/{post.tid}",
            "commentId": submit_comment_id,
            "commentUin": int(comment_uin or 0),
        }
        if target_submit_id:
            data.update(t1_uin=post.uin, t1_tid=post.tid, t2_tid=target_submit_id)
        if comment_uin:
            data.update(t2_uin=target_t2_uin, replyUin=target_reply_uin)
        return data



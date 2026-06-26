from __future__ import annotations

from typing import Any

from ..models import QzoneComment, QzoneContext, QzonePost
from .payloads import QzoneReplyPayloadMixin


QZONE_BASE_URL = "https://user.qzone.qq.com"


class QzoneReplyPlanMixin(QzoneReplyPayloadMixin):
    """Prepare ordered Qzone reply submission attempts."""

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

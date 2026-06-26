from __future__ import annotations

import time
from typing import Any

from ..models import QzoneComment, QzoneContext, QzonePost
from .targets import QzoneReplyTargetMixin


class QzoneReplyPayloadMixin(QzoneReplyTargetMixin):
    """Build request payloads for each Qzone reply endpoint."""

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
            data.update(commentId=target_comment_id)
            if is_reply:
                data.update(t1_uin=post.uin, t1_tid=post.tid, t2_tid=target_t2_tid)
        if comment_uin:
            data.update(commentUin=comment_uin)
            if is_reply:
                data.update(t2_uin=target_t2_uin)
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

from __future__ import annotations

from ..models import QzoneContext, QzonePost


class QzoneCommentDeleteMixin:
    """删除 QQ 空间评论。"""

    async def delete_comment(
        self,
        post: QzonePost | str,
        comment_id: str,
        *,
        comment_uin: int = 0,
        ctx: QzoneContext | None = None,
    ) -> dict:
        qzone_post = self._require_post(post) if isinstance(post, str) else post
        comment_id = str(comment_id or "").strip()
        if not comment_id:
            raise RuntimeError("QQ 空间评论 ID 无效")
        ctx = ctx or await self.context()
        comment_uin = int(comment_uin or ctx.uin or 0)
        sns_payload = await self._delete_comment_via_sns(
            ctx,
            qzone_post,
            comment_id=comment_id,
            comment_uin=comment_uin,
        )
        if self._ok(sns_payload):
            return {
                "transport": "sns",
                "comment_id": comment_id,
                "payload": sns_payload,
            }
        pc_payload = await self._delete_comment_via_pc(
            ctx,
            qzone_post,
            comment_id=comment_id,
        )
        if self._ok(pc_payload) or self._write_response_without_json_ok(pc_payload):
            return {
                "transport": "pc",
                "comment_id": comment_id,
                "payload": pc_payload,
            }
        raise RuntimeError(self._payload_message(pc_payload) or self._payload_message(sns_payload) or "QQ 空间删除评论失败")

    async def _delete_comment_via_sns(
        self,
        ctx: QzoneContext,
        post: QzonePost,
        *,
        comment_id: str,
        comment_uin: int,
    ) -> dict:
        return await self._request(
            "POST",
            self.SNS_DELETE_COMMENT_URL,
            params={"g_tk": ctx.gtk},
            data={
                "inCharset": "utf-8",
                "outCharset": "utf-8",
                "plat": "qzone",
                "source": "ic",
                "hostUin": post.uin,
                "uin": post.uin,
                "topicId": f"{post.uin}_{post.tid}",
                "feedsType": 100,
                "commentId": comment_id,
                "commentUin": comment_uin,
                "format": "fs",
                "ref": "feeds",
                "paramstr": "2",
                "qzreferrer": f"{self.BASE_URL}/{post.uin}/mood/{post.tid}",
            },
            headers=self._comment_sns_headers(ctx, referer=f"{self.BASE_URL}/{post.uin}/mood/{post.tid}"),
            retry_parse_error=False,
        )

    async def _delete_comment_via_pc(
        self,
        ctx: QzoneContext,
        post: QzonePost,
        *,
        comment_id: str,
    ) -> dict:
        return await self._request(
            "POST",
            self.DELETE_COMMENT_URL,
            params={"g_tk": ctx.gtk},
            data={
                "hostuin": ctx.uin,
                "uin": post.uin,
                "tid": post.tid,
                "comment_id": comment_id,
                "format": "json",
                "qzreferrer": f"{self.BASE_URL}/{post.uin}/mood/{post.tid}",
            },
            retry_parse_error=False,
        )

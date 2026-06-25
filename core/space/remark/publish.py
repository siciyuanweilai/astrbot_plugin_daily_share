from __future__ import annotations


class QzoneCommentPostMixin:
    """提交 QQ 空间一级评论。"""

    async def comment(self, post_id: str, content: str) -> None:
        post = self._require_post(post_id)
        content = str(content or "").strip()
        if not content:
            raise RuntimeError("评论内容不能为空")
        ctx = await self.context()
        payload = await self._request(
            "POST",
            self.COMMENT_URL,
            params={"g_tk": ctx.gtk},
            data={
                "hostUin": post.uin,
                "topicId": f"{post.uin}_{post.tid}",
                "content": content,
                "format": "json",
                "qzreferrer": f"{self.BASE_URL}/{ctx.uin}",
            },
            retry_parse_error=False,
        )
        if self._comment_submit_ok(payload):
            return

        payload = await self._request(
            "POST",
            self.H5_COMMENT_URL,
            params={"g_tk": ctx.gtk},
            data=self._h5_comment_data(ctx, post, content=content),
            retry_parse_error=False,
        )
        if self._comment_submit_ok(payload):
            return
        raise RuntimeError(str(payload.get("message") or "QQ 空间评论失败"))

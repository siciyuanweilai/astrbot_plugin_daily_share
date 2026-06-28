from __future__ import annotations

import json


class QzoneCommentPostMixin:
    """提交 QQ 空间一级评论。"""

    async def comment(self, post_id: str, content: str) -> None:
        post = self._require_post(post_id)
        content = str(content or "").strip()
        if not content:
            raise RuntimeError("评论内容不能为空")
        ctx = await self.context()
        data = self._h5_comment_data(ctx, post, content=content)
        data.update(
            busi_param=json.dumps(getattr(post, "busi_param", {}) or {}, ensure_ascii=False),
            isSignIn="0",
        )
        payload = await self._request(
            "POST",
            self.COMMENT_URL,
            params={"g_tk": ctx.gtk},
            data=data,
            headers=self._headers(ctx, Referer=str(data.get("qzreferrer") or ""), Origin=self.BASE_URL),
            retry_parse_error=False,
        )
        if self._comment_submit_ok(payload):
            return
        raise RuntimeError(str(payload.get("message") or "QQ 空间评论失败"))

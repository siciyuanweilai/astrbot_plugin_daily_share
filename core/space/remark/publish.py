from __future__ import annotations

from ..methodset import QzoneMethodSet


class QzoneCommentPostService(QzoneMethodSet):
    """提交 QQ 空间一级评论。"""

    async def comment(self, post_id: str, content: str) -> None:
        post = self._require_post(post_id)
        content = str(content or "").strip()
        if not content:
            raise RuntimeError("评论内容不能为空")
        if post.comment_target_error:
            raise RuntimeError(post.comment_target_error)
        if int(post.appid or 311) == 4:
            photo = post.photo_targets[0]
            await self.comment_photo(
                owner_uin=post.uin,
                album_id=photo.album_id,
                pic_key=photo.pic_key,
                content=content,
                feed_topic_id=photo.feed_comment_topic_id,
            )
            self._invalidate_qzone_cache(post_id=post.key, target_id=str(post.uin))
            return
        ctx = await self.context()
        # 按 PC 说说页成功抓包构造一级评论，不能混用 H5 回评参数。
        # hostUin 指动态主人；hostuin 和 commentUin 均为当前登录账号。
        referer = self._mood_v6_referrer(post)
        data = {
            "uin": ctx.uin,
            "hostUin": post.uin,
            "topicId": f"{post.uin}_{post.tid}",
            "commentUin": ctx.uin,
            "content": content,
            "richval": "",
            "richtype": "",
            "inCharset": "",
            "outCharset": "",
            "ref": "",
            "private": 0,
            "with_fwd": 0,
            "to_tweet": 0,
            "hostuin": ctx.uin,
            "code_version": 1,
            "format": "fs",
            "qzreferrer": referer,
        }
        payload = await self._request(
            "POST",
            self.COMMENT_URL,
            params={"g_tk": ctx.gtk},
            data=data,
            headers=self._pc_form_headers(ctx, referer=referer),
            retry_parse_error=False,
        )
        if self._comment_submit_ok(payload):
            self._invalidate_qzone_cache(post_id=post.key, target_id=str(post.uin))
            return

        message = self._payload_message(payload) or "QQ 空间评论失败"
        code = payload.get("code") if isinstance(payload, dict) else None
        status = payload.get("_http_status") if isinstance(payload, dict) else None
        diagnostics = ["transport=pc_mood", f"appid={post.appid}"]
        if code not in (None, ""):
            diagnostics.append(f"code={code}")
        if status not in (None, ""):
            diagnostics.append(f"http={status}")
        suffix = f"（{', '.join(diagnostics)}）" if diagnostics else ""
        raise RuntimeError(f"{message}{suffix}")

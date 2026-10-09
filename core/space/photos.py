from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace
from typing import Any

from astrbot.api import logger

from .methodset import QzoneMethodSet
from .models import (
    QzoneComment,
    QzonePhoto,
    QzonePhotoComment,
    QzonePost,
    normalize_photo_comment_topic,
)
from .parse.decoder import clean_qzone_text
from .parse.photo import photo_reply_mention, photo_thread_comments
from .parse.phototarget import parse_photo_batch_topic


def _parse_photo(payload: dict[str, Any], *, album_id: str, pic_key: str):
    from .parse.photo import parse_qzone_photo

    return parse_qzone_photo(payload, album_id=album_id, pic_key=pic_key)


def _parse_photo_comment(payload: dict[str, Any], *, content: str, uin: int):
    from .parse.photo import parse_qzone_photo_comment

    return parse_qzone_photo_comment(payload, content=content, uin=uin)


def _positive_uin(value: Any, *, label: str) -> int:
    text = str(value or "").strip()
    if not text.isascii() or not text.isdigit() or len(text) > 20 or int(text) <= 0:
        raise RuntimeError(f"{label}无效")
    return int(text)


def _photo_identifier(value: Any, *, label: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 512 or any(ord(char) < 0x20 for char in text):
        raise RuntimeError(f"{label}无效")
    return text


def _photo_form_headers(
    service, ctx, *, owner: int, referer: str = ""
) -> dict[str, str]:
    return service._headers(
        ctx,
        Referer=referer or f"{service.BASE_URL}/{owner}",
        Origin=service.BASE_URL,
        Accept="*/*",
        **{
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        },
    )


def photo_reply_target_error(
    comment: QzoneComment, *, topic: str, parent_comment: QzoneComment | None = None
) -> str:
    root = parent_comment if parent_comment is not None else comment
    try:
        _positive_uin(root.tid, label="相册一级评论 ID")
        _positive_uin(root.uin, label="相册一级评论人 QQ")
        _positive_uin(comment.uin, label="相册评论人 QQ")
    except RuntimeError as exc:
        return str(exc)
    for item in (root, comment):
        fields = item.raw_fields or {}
        if fields.get("photo_private") not in (None, 0, "0"):
            return "私密相册评论不能自动公开回评"
        if fields.get("photo_topic_id") and fields["photo_topic_id"] != topic:
            return "相册评论 topicId 与照片目标不一致"
    if root.parent_tid or root.reply_to_tid:
        return "相册原一级评论楼无效，不能作为更深层续评的落点"
    if parent_comment is None:
        return "" if not comment.parent_tid else "相册续评缺少原一级评论楼"
    fields = comment.raw_fields or {}
    try:
        _positive_uin(comment.raw_tid, label="相册二级回复 ID")
    except RuntimeError as exc:
        return str(exc)
    if (
        comment.parent_tid != root.tid
        or fields.get("photo_root_id") != root.tid
        or fields.get("photo_root_uin") != root.uin
        or fields.get("photo_topic_id") != topic
        or (root.raw_fields or {}).get("photo_topic_id") != topic
        or comment.tid != f"{root.tid}_r_{comment.raw_tid}_{comment.uin}"
        or comment.reply_to_tid_source != "photo_mention"
        or not comment.reply_to_tid
        or photo_reply_mention(comment.content)[0] != comment.reply_to_uin
        or comment.reply_to_uin <= 0
    ):
        return "相册更深层续评缺少可靠的原楼或回复对象，不能猜测落点"
    return ""


async def _verify_photo_reply(
    service, *, owner, album, pic, root, target, reply, content
):
    """按返回的回复 ID 回查结果，不重发，也不调用说说评论删除接口。"""
    status = "not_found"
    for delay in (0, 0.8, 1.6):
        if delay:
            await asyncio.sleep(delay)
        try:
            photo = await service.query_photo(
                owner_uin=owner, album_id=album, pic_key=pic, comment_count=50
            )
        except Exception:
            status = "detail_failed"
            continue
        status = "not_found"
        misplaced = False
        for parent in photo.comments:
            for item in parent.replies:
                if item.comment_id != reply.comment_id or item.uin != reply.uin:
                    continue
                if parent.comment_id != root.tid or parent.uin != root.uin:
                    misplaced = True
                    continue
                if photo_reply_mention(item.content)[
                    0
                ] != target.uin or item.content != clean_qzone_text(content):
                    return {"verification_status": "wrong_target"}
                return {
                    "verification_status": "confirmed",
                    "verified_reply_tid": f"{root.tid}_r_{item.comment_id}_{item.uin}",
                    "verified_reply_to_tid": target.tid,
                    "verified_reply_to_uin": target.uin,
                }
        if misplaced:
            status = "wrong_target"
    return {"verification_status": status}


def _photo_submit_result(
    service, payload: dict, *, content: str, uin: int, transport: str
) -> QzonePhotoComment:
    try:
        success = (
            int(payload["code"]) == 0
            and int(payload.get("subcode") or 0) == 0
            and 200 <= int(payload.get("_http_status") or 200) < 300
        )
    except (KeyError, TypeError, ValueError):
        success = False
    if not success:
        message = service._payload_message(payload) or "QQ 空间相册评论提交失败"
        exc = RuntimeError(
            f"{message}（transport={transport}, appid=4, "
            f"code={payload.get('code')}, subcode={payload.get('subcode')}, "
            f"http={payload.get('_http_status')}）"
        )
        if payload.get("code") in (None, "", -1, "-1") or (
            payload.get("code") in (0, "0")
            and payload.get("subcode") in (None, "", 0, "0")
        ):
            setattr(exc, "submission_unknown", True)
        raise exc
    comment = _parse_photo_comment(payload, content=content, uin=uin)
    if (
        not comment.comment_id.isascii()
        or not comment.comment_id.isdigit()
        or len(comment.comment_id) > 20
        or int(comment.comment_id) <= 0
    ):
        exc = RuntimeError(
            "QQ 空间相册评论未返回有效评论 ID，提交状态未知，请先查看相册避免重复评论"
            f"（transport={transport}, appid=4）"
        )
        setattr(exc, "submission_unknown", True)
        raise exc
    return comment


class QzonePhotoService(QzoneMethodSet):
    """读取 QQ 空间相册中的单张照片并发表评论。"""

    async def query_photo_posts(self, post_id: str) -> list[QzonePost]:
        """读取动态中明确标识的照片，分别建立可安全提交的目标。"""
        post = self._require_post(post_id)
        if int(post.appid or 311) != 4:
            return [post]
        targets = {}
        missing_count = 0
        for target in post.photo_targets:
            if (
                not target.album_id
                and not target.pic_key
                and target.unresolved_count > 0
            ):
                missing_count += target.unresolved_count
                continue
            error = replace(
                post, photo_targets=[replace(target, feed_topic_id="")]
            ).comment_target_error
            if error:
                raise RuntimeError(error)
            targets[target.key] = target
        if not targets:
            raise RuntimeError(post.comment_target_error)

        topic_targets = {
            f"{target.comment_topic_id}_0_0": target for target in targets.values()
        }
        shared_topics = {}
        batch_topics = {}
        for target in targets.values():
            topic = target.feed_comment_topic_id
            if topic == f"{target.comment_topic_id}_0_0":
                continue
            batch_topic = parse_photo_batch_topic(
                target.feed_topic_id, album_id=target.album_id
            )
            if batch_topic:
                pic, batch, platform = batch_topic
                if target.batch_id != batch or target.platform_sub_id != platform:
                    raise RuntimeError("相册动态批次或 platformSubId 与 topicId 不一致")
                sibling = targets.get(f"{target.album_id}:{pic}")
                batch_topics[target.key] = (batch, platform)
            else:
                sibling = topic_targets.get(topic)
            if sibling is None or sibling.album_id != target.album_id:
                raise RuntimeError(
                    "相册动态 topicId 与 albumId/picKey 不一致，不能自动评论"
                    f"（photo={target.key!r}, topicId={target.feed_topic_id[:512]!r}, "
                    f"expected={target.comment_topic_id + '_0_0'!r}）"
                )
            shared_topics[target.key] = sibling.key
        if len(post.photo_targets) == 1 and not shared_topics:
            return [await self.detail(post.key)]

        seeds = {}
        if missing_count:
            for target in targets.values():
                seeds[target.key] = await self.query_photo(
                    owner_uin=post.uin,
                    album_id=target.album_id,
                    pic_key=target.pic_key,
                    comment_count=50,
                )
            batches = {(photo.album_id, photo.batch_id) for photo in seeds.values()}
            if len(batches) != 1 or not next(iter(batches))[1]:
                raise RuntimeError("相册动态有未定位照片，查看器未确认同一 batchId")
            expected_count = len(targets) + missing_count
            for photo in seeds.values():
                for target in photo.batch_targets:
                    targets.setdefault(target.key, target)
            if len(targets) != expected_count:
                raise RuntimeError(
                    "相册动态照片数量与查看器同批照片不一致，不能自动补全"
                )

        result = []
        viewer_batches = {}
        complete = True
        for target in sorted(targets.values(), key=lambda photo: photo.key):
            try:
                photo = seeds.get(target.key)
                if photo is None:
                    photo = await self.query_photo(
                        owner_uin=post.uin,
                        album_id=target.album_id,
                        pic_key=target.pic_key,
                        comment_count=50,
                    )
                if (
                    target.batch_id
                    and photo.batch_id
                    and target.batch_id != photo.batch_id
                ):
                    raise RuntimeError("相册照片 batchId 与动态目标不一致")
                photo.feed_topic_id = target.feed_topic_id
                viewer_batches[photo.key] = photo.batch_id
                photo.batch_id = photo.batch_id or target.batch_id
            except Exception as exc:
                complete = False
                logger.debug(
                    f"[日常分享] QQ 空间批量相册读取照片评论失败: {target.key}: {exc}"
                )
                continue
            # 不将上传批次中未绑定照片的 HTML 评论带入单张照片。
            result.append(
                replace(
                    post,
                    tid=f"photo:{photo.key}",
                    feed_key=post.feed_key or post.tid,
                    photo_targets=[photo],
                    comments=photo_thread_comments(photo),
                    images=[photo.image_url] if photo.image_url else [],
                )
            )
        if not result:
            raise RuntimeError("QQ 空间批量相册未能读取任何照片评论")
        if shared_topics:
            verified = {item.photo_targets[0].key: item for item in result}
            safe_result = []
            for item in result:
                photo = item.photo_targets[0]
                sibling_key = shared_topics.get(photo.key)
                if sibling_key:
                    sibling_post = verified.get(sibling_key)
                    sibling = sibling_post.photo_targets[0] if sibling_post else None
                    claimed_batch = batch_topics.get(photo.key)
                    if (
                        sibling is None
                        or not viewer_batches.get(photo.key)
                        or viewer_batches[photo.key] != viewer_batches.get(sibling_key)
                        or photo.album_id != sibling.album_id
                        or photo.owner_uin != sibling.owner_uin
                        or (
                            claimed_batch
                            and (
                                viewer_batches[photo.key] != claimed_batch[0]
                                or photo.platform_sub_id != claimed_batch[1]
                                or sibling.platform_sub_id != claimed_batch[1]
                            )
                        )
                    ):
                        complete = False
                        logger.debug(
                            "[日常分享] QQ 空间相册共享 topicId 未确认同批，跳过照片: "
                            f"{photo.key!r}，引用照片={sibling_key!r}"
                        )
                        continue
                    photo.feed_topic_id = f"{photo.comment_topic_id}_0_0"
                safe_result.append(item)
            result = safe_result
            if not result:
                raise RuntimeError("QQ 空间相册共享 topicId 未能核实任何照片目标")
        batches = {
            (item.photo_targets[0].album_id, item.photo_targets[0].batch_id)
            for item in result
        }
        if complete and len(batches) == 1 and next(iter(batches))[1]:
            album, batch = next(iter(batches))
            batch_key = f"{post.uin}:photo-batch:{album}:{batch}"
        else:
            identity = "\n".join(sorted(targets))
            digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
            batch_key = f"{post.uin}:photo-set:{digest}"
        for item in result:
            item.photo_batch_key = batch_key
            item.photo_batch_complete = complete
        self._remember_posts(result, detailed=True)
        return result

    async def query_photo(
        self,
        *,
        owner_uin: int | str,
        album_id: str,
        pic_key: str,
        photo_t: str = "",
        comment_count: int = 10,
    ) -> QzonePhoto:
        owner = _positive_uin(owner_uin, label="相册主人 QQ")
        album = _photo_identifier(album_id, label="相册 ID")
        pic = _photo_identifier(pic_key, label="照片 picKey")
        limit = max(1, min(int(comment_count or 10), 50))
        ctx = await self.context()
        params = {
            "t": str(photo_t or "").strip(),
            "topicId": album,
            "picKey": pic,
            "shootTime": "",
            "cmtOrder": 1,
            "fupdate": 1,
            "plat": "qzone",
            "source": "qzone",
            "cmtNum": limit,
            "likeNum": 5,
            "inCharset": "utf-8",
            "outCharset": "utf-8",
            "callbackFun": "viewer",
            "offset": 0,
            "number": 15,
            "uin": ctx.uin,
            "hostUin": owner,
            "appid": 4,
            "isFirst": 1,
            "sortOrder": 1,
            "showMode": 1,
            "need_private_comment": 1,
            "prevNum": 9,
            "postNum": 18,
            "g_tk": ctx.gtk,
        }
        payload = await self._request(
            "GET",
            self.PHOTO_VIEW_URL,
            params=params,
            headers=self._headers(ctx, Referer=f"{self.BASE_URL}/{owner}"),
            retry_parse_error=False,
        )
        if not self._ok(payload):
            raise RuntimeError(
                str(payload.get("message") or "获取 QQ 空间相册照片失败")
            )
        photo = _parse_photo(payload, album_id=album, pic_key=pic)
        if photo is None:
            raise RuntimeError("QQ 空间相册响应未包含请求的 albumId/picKey")
        if photo.owner_uin and photo.owner_uin != owner:
            raise RuntimeError("QQ 空间相册照片主人与请求目标不一致")
        photo.owner_uin = photo.owner_uin or owner
        return photo

    async def comment_photo(
        self,
        *,
        owner_uin: int | str,
        album_id: str,
        pic_key: str,
        content: str,
        feed_topic_id: str = "",
    ) -> QzonePhotoComment:
        owner = _positive_uin(owner_uin, label="相册主人 QQ")
        album = _photo_identifier(album_id, label="相册 ID")
        pic = _photo_identifier(pic_key, label="照片 picKey")
        topic = normalize_photo_comment_topic(album, pic, feed_topic_id)
        if topic != f"{album}_{pic}_0_0":
            raise RuntimeError("相册动态 topicId 与 albumId/picKey 不一致")
        text = str(content or "").strip()
        if not text:
            raise RuntimeError("相册照片评论内容不能为空")
        ctx = await self.context()
        referer = f"{self.BASE_URL}/{ctx.uin}/infocenter"
        data = {
            "uin": ctx.uin,
            "hostUin": owner,
            "topicId": f"{album}_{pic}",
            "commentUin": ctx.uin,
            "content": text,
            "richval": "",
            "richtype": "",
            "inCharset": "utf-8",
            "outCharset": "utf-8",
            "ref": "photo",
            "need_private_comment": 1,
            "albumId": album,
            "qzone": "qzone",
            "plat": "qzone",
            "private": 0,
            "with_fwd": 0,
            "to_tweet": 0,
            "qzreferrer": referer,
        }
        try:
            payload = await self._request(
                "POST",
                self.PHOTO_COMMENT_URL,
                params={"g_tk": ctx.gtk},
                data=data,
                headers=_photo_form_headers(self, ctx, owner=owner, referer=referer),
                retry_parse_error=False,
            )
        except RuntimeError as error:
            exc = RuntimeError(
                f"{error}（transport=photo_comment, appid=4，提交状态未知）"
            )
            setattr(exc, "submission_unknown", True)
            raise exc from error
        return _photo_submit_result(
            self, payload, content=text, uin=ctx.uin, transport="photo_comment"
        )

    async def reply_photo_comment(
        self,
        *,
        owner_uin: int | str,
        album_id: str,
        pic_key: str,
        comment: QzoneComment,
        content: str,
        feed_topic_id: str = "",
        parent_comment: QzoneComment | None = None,
    ) -> dict[str, Any]:
        """在原照片评论楼层内回评，并 @ 当前被回复者。"""
        owner = _positive_uin(owner_uin, label="相册主人 QQ")
        album = _photo_identifier(album_id, label="相册 ID")
        pic = _photo_identifier(pic_key, label="照片 picKey")
        topic = normalize_photo_comment_topic(album, pic, feed_topic_id)
        if topic != f"{album}_{pic}_0_0":
            raise RuntimeError("相册动态 topicId 与 albumId/picKey 不一致")
        target_error = photo_reply_target_error(
            comment, topic=topic, parent_comment=parent_comment
        )
        if target_error:
            raise RuntimeError(target_error)
        root = parent_comment if parent_comment is not None else comment
        comment_id = str(root.tid).strip()
        commenter = int(root.uin)
        text = str(content or "").strip()
        if not text:
            raise RuntimeError("相册评论回复内容不能为空")
        ctx = await self.context()
        submit_content = self._reply_content(text, comment)
        if (
            parent_comment is not None
            and photo_reply_mention(submit_content)[0] != comment.uin
        ):
            raise RuntimeError("相册续评正文 @ 对象与当前评论人不一致")
        data = {
            "uin": ctx.uin,
            "hostUin": owner,
            "topicId": topic,
            "commentId": comment_id,
            "commentUin": commenter,
            "content": submit_content,
            "inCharset": "utf-8",
            "outCharset": "utf-8",
            "ref": "photo",
            "need_private_comment": 1,
            "albumId": album,
            "qzone": "qzone",
            "plat": "qzone",
            "private": 0,
            "with_fwd": 0,
            "to_tweet": 0,
            "qzreferrer": f"{self.BASE_URL}/{owner}",
        }
        targets = [{"comment_id": comment_id, "comment_uin": commenter}]
        try:
            payload = await self._request(
                "POST",
                self.PHOTO_REPLY_URL,
                params={"g_tk": ctx.gtk},
                data=data,
                headers=_photo_form_headers(self, ctx, owner=owner),
                retry_parse_error=False,
            )
        except RuntimeError as error:
            exc = RuntimeError(
                f"{error}（transport=photo_reply, appid=4，提交状态未知）"
            )
            setattr(exc, "submission_unknown", True)
            setattr(exc, "attempted_targets", targets)
            raise exc from error
        attempt = {
            "transport": "photo_reply",
            "comment_id": comment_id,
            "comment_uin": commenter,
            "code": payload.get("code"),
            "subcode": payload.get("subcode"),
            "http_status": payload.get("_http_status"),
        }
        try:
            reply = _photo_submit_result(
                self,
                payload,
                content=submit_content,
                uin=ctx.uin,
                transport="photo_reply",
            )
        except RuntimeError as exc:
            setattr(exc, "attempted_targets", targets)
            setattr(exc, "attempts", [attempt])
            raise
        self._invalidate_qzone_cache(target_id=str(owner))
        result = {
            "comment_id": comment_id,
            "comment_uin": commenter,
            "reply_id": reply.comment_id,
            "transport": "photo_reply",
            "attempted_targets": targets,
            "attempts": [attempt],
        }
        if parent_comment is not None:
            verification = await _verify_photo_reply(
                self,
                owner=owner,
                album=album,
                pic=pic,
                root=root,
                target=comment,
                reply=reply,
                content=submit_content,
            )
            result.update(verification)
            if verification["verification_status"] != "confirmed":
                exc = RuntimeError(
                    "相册续评已提交，但读取照片未确认回复落点，已停止自动重试"
                    f"（transport=photo_reply, reply_id={reply.comment_id}, "
                    f"verification={verification['verification_status']}）"
                )
                setattr(exc, "reply_verification_failed", True)
                for name, value in result.items():
                    setattr(exc, name, value)
                raise exc
        return result


__all__ = ["QzonePhotoService"]

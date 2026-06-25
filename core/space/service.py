from __future__ import annotations

import asyncio
import base64
import os
import time
from typing import Any

from astrbot.api import logger

from .gateway import QzoneClientServiceMixin
from .discussion import QzoneCommentServiceMixin
from .endpoints import QzoneServiceConstants
from .feed import QzoneFeedServiceMixin
from .models import QzoneComment, QzoneContext, QzonePost
from .parse import parse_upload_result
from .upload import QzoneMediaUploadMixin


class QzoneService(
    QzoneServiceConstants,
    QzoneClientServiceMixin,
    QzoneFeedServiceMixin,
    QzoneCommentServiceMixin,
    QzoneMediaUploadMixin,
):
    def __init__(self, plugin):
        self.plugin = plugin
        self._ctx: QzoneContext | None = None
        self._ctx_at = 0.0
        self._session = None
        self._h2_session = None
        self._session_timeout_seconds: int | None = None
        self._h2_timeout_seconds: int | None = None
        self._h5_transport = ""
        self._h5_transport_logged = False
        self._post_cache: dict[str, QzonePost] = {}
        self._last_friend_feeds_meta: dict[str, Any] = {}


    @staticmethod
    def _text_with_video_links(text: str, video_links: list[str]) -> str:
        links = [str(item or "").strip() for item in video_links if str(item or "").strip()]
        if not links:
            return text or ""
        suffix = "\n".join(f"Video: {link}" for link in links)
        return "\n\n".join(part for part in (str(text or "").strip(), suffix) if part)

    async def _upload_image(self, image) -> tuple[str, str]:
        ctx = await self.context()
        image_data = await self._image_bytes(image)
        filename = "image.jpg" if str(image or "").strip().startswith("base64://") else os.path.basename(str(image) or "image.jpg")
        payload = await self._request(
            "POST",
            self.UPLOAD_IMAGE_URL,
            data={
                "filename": filename[:128] or "image.jpg",
                "uploadtype": "1",
                "albumtype": "7",
                "skey": ctx.skey,
                "uin": ctx.uin,
                "p_skey": ctx.p_skey,
                "output_type": "json",
                "base64": "1",
                "picfile": base64.b64encode(image_data).decode("ascii"),
            },
            headers=self._headers(ctx, referer=f"{self.BASE_URL}/{ctx.uin}", origin=self.BASE_URL),
        )
        if not self._ok(payload, code_key="ret"):
            raise RuntimeError(str(payload.get("msg") or payload.get("message") or "QQ 空间图片上传失败"))
        return parse_upload_result(payload)

    def _publish_data(
        self,
        ctx: QzoneContext,
        *,
        text: str = "",
        pic_bos: list[str] | None = None,
        richvals: list[str] | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "syn_tweet_verson": "1",
            "paramstr": "1",
            "who": "1",
            "con": text or "",
            "feedversion": "1",
            "ver": "1",
            "ugc_right": "1",
            "to_sign": "0",
            "hostuin": ctx.uin,
            "code_version": "1",
            "issyncweibo": 0,
            "format": "json",
            "qzreferrer": f"{self.BASE_URL}/{ctx.uin}",
        }
        if pic_bos and richvals:
            data.update(pic_bo=",".join(pic_bos), richtype="1", richval="\t".join(richvals))
        return data

    def _qzone_error_message(self, payload: dict[str, Any], fallback: str) -> str:
        if not isinstance(payload, dict):
            return fallback
        message = payload.get("message") or payload.get("msg")
        data = payload.get("data")
        if not message and isinstance(data, dict):
            message = data.get("message") or data.get("msg")
        if message:
            return str(message)
        code = payload.get("code")
        if code not in (None, 0, "0"):
            return f"{fallback}，返回码: {code}"
        return fallback

    async def _submit_post(self, ctx: QzoneContext, data: dict[str, Any]) -> dict[str, Any]:
        payload = await self._request(
            "POST",
            self.PUBLISH_URL,
            params={"g_tk": ctx.gtk2, "uin": ctx.uin},
            data=data,
        )
        if not self._ok(payload):
            raise RuntimeError(self._qzone_error_message(payload, "QQ 空间说说发布失败"))
        return payload

    async def publish_post(self, *, text: str = "", images: list | None = None, videos: list | None = None) -> QzonePost:
        ctx = await self.context()
        pic_bos = []
        richvals = []
        submitted_at = int(time.time())
        video_links, post_videos, album_video_post = await self._prepare_publish_videos(
            ctx,
            videos,
            text=text or "",
            submitted_at=submitted_at,
        )
        if album_video_post is not None and not video_links:
            if not album_video_post.text:
                album_video_post.text = text or ""
            self._remember_posts([album_video_post])
            return album_video_post
        if images:
            logger.info(f"[每日分享] 正在上传 QQ 空间配图，共 {len(images)} 张...")
            for image in images:
                picbo, richval = await self._upload_image(image)
                pic_bos.append(picbo)
                richvals.append(richval)
            logger.info("[每日分享] QQ 空间配图上传完成，正在发布说说...")

        if video_links:
            logger.info(f"[每日分享] 已将 {len(video_links)} 个 QQ 空间视频链接追加到说说正文。")

        publish_text = self._text_with_video_links(text, video_links)
        data = self._publish_data(
            ctx,
            text=publish_text,
            pic_bos=pic_bos,
            richvals=richvals,
        )
        try:
            payload = await self._submit_post(ctx, data)
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            if any(key in message for key in ("超时", "Timeout", "timeout", "网络", "Connection", "disconnect")):
                logger.warning(f"[每日分享] QQ 空间说说发布失败: {message}，2 秒后复用已上传图片重试一次。")
                await asyncio.sleep(2)
                try:
                    payload = await self._submit_post(ctx, data)
                except Exception as retry_exc:
                    retry_message = str(retry_exc).strip() or retry_exc.__class__.__name__
                    raise RuntimeError(f"QQ 空间说说重试发布仍失败: {retry_message}") from retry_exc
            else:
                raise RuntimeError(f"QQ 空间说说发布失败: {message}") from exc
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        post = QzonePost(
            tid=str(payload.get("tid") or data.get("tid") or ""),
            uin=ctx.uin,
            name=ctx.nickname or str(ctx.uin),
            text=publish_text or "",
            videos=post_videos or video_links,
            create_time=int(payload.get("now") or data.get("now") or time.time()),
        )
        self._remember_posts([post])
        return post


    async def like(self, post_id: str) -> None:
        post = self._require_post(post_id)
        ctx = await self.context()
        payload = await self._request(
            "POST",
            self.LIKE_URL,
            params={"g_tk": ctx.gtk},
            data={
                "qzreferrer": f"{self.BASE_URL}/{ctx.uin}",
                "opuin": ctx.uin,
                "unikey": f"{self.BASE_URL}/{post.uin}/mood/{post.tid}",
                "curkey": f"{self.BASE_URL}/{post.uin}/mood/{post.tid}",
                "appid": 311,
                "from": 1,
                "typeid": 0,
                "abstime": int(time.time()),
                "fid": post.tid,
                "active": 0,
                "format": "json",
                "fupdate": 1,
            },
        )
        if not self._ok(payload):
            raise RuntimeError(str(payload.get("message") or "QQ 空间点赞失败"))


    async def delete_post(self, post_id: str) -> None:
        post = self._require_post(post_id)
        if not post.tid:
            raise RuntimeError("说说 ID 无效")
        ctx = await self.context()
        if int(post.uin or 0) != int(ctx.uin or 0):
            raise RuntimeError("只能删除自己发布的说说")
        await self._delete_own_post_by_tid(ctx, post.tid)
        self._post_cache.pop(post.key, None)

    async def _delete_own_post_by_tid(self, ctx: QzoneContext, tid: str) -> None:
        tid = str(tid or "").strip()
        if not tid:
            raise RuntimeError("说说 ID 无效")
        payload = await self._request(
            "POST",
            self.DELETE_URL,
            params={"g_tk": ctx.gtk2},
            data={
                "uin": ctx.uin,
                "topicId": f"{ctx.uin}_{tid}__1",
                "feedsType": 0,
                "feedsFlag": 0,
                "feedsKey": tid,
                "feedsAppid": 311,
                "feedsTime": int(time.time()),
                "fupdate": 1,
                "ref": "feeds",
                "qzreferrer": (
                    f"{self.BASE_URL}/proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/"
                    f"feeds_html_module?g_iframeUser=1&i_uin={ctx.uin}&i_login_uin={ctx.uin}"
                    "&mode=4&previewV8=1&style=35&version=8&needDelOpr=true"
                ),
            },
            retry_parse_error=False,
        )
        if not self._ok(payload):
            if self._write_response_without_json_ok(payload):
                logger.debug("[每日分享] QQ 空间删除接口返回内容不是结构化数据，但接口状态正常，按删除成功处理。")
                return
            raise RuntimeError(str(payload.get("message") or "QQ 空间删除失败"))

    @staticmethod
    def _write_response_without_json_ok(payload: dict[str, Any]) -> bool:
        status = int(payload.get("_http_status") or 0)
        message = str(payload.get("message") or "")
        return status in {200, 204} and QzoneService._write_response_without_json_message(message)

    @staticmethod
    def _write_response_without_json_message(message: str) -> bool:
        base = str(message or "").split("（", 1)[0].strip()
        return base in {
            "QQ 空间返回为空",
            "QQ 空间返回内容不是结构化数据",
            "QQ 空间响应解析失败",
            "QQ 空间响应格式异常",
        }

    def _remember_posts(self, posts: list[QzonePost]) -> None:
        for post in posts:
            self._post_cache[post.key] = post

    def _require_post(self, post_id: str) -> QzonePost:
        key = str(post_id or "").strip()
        post = self._post_cache.get(key)
        if post:
            return post
        if ":" in key:
            uin, tid = key.split(":", 1)
            if uin.isdigit() and tid:
                post = QzonePost(uin=int(uin), tid=tid)
                self._post_cache[key] = post
                return post
        raise RuntimeError("说说引用已失效，请先刷新 QQ 空间动态")

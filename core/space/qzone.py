from __future__ import annotations

import asyncio
import base64
import os
import time
from pathlib import Path
from typing import Any

from astrbot.api import logger

from ..platform import ONEBOT_PLATFORM_TYPES, get_platform_bindings, get_platform_client
from .endpoints import QzoneServiceConstants
from .errors import QzoneImageUploadError, QzonePublishUnknownError
from .feeds.detail import QzoneFeedDetailService
from .feeds.extra import QzoneFeedExtraService
from .feeds.homefeed import QzoneFeedHomeService
from .feeds.posts import QzoneFeedPostsService
from .feeds.recent import QzoneFeedRecentService
from .gateway import QzoneClientGateway
from .hfive.error import QzoneH5ErrorService
from .hfive.packets import QzoneH5BaseService
from .hfive.poster import QzoneH5RequestService
from .merge import QzoneFeedMergeService
from .models import QzoneComment as QzoneComment
from .models import QzoneContext, QzonePost
from .parse import parse_upload_result
from .photos import QzonePhotoService
from .query.timeline import QzoneFeedQueryService
from .remark.commenttools import QzoneCommentUtilService
from .remark.delete import QzoneCommentDeleteService
from .remark.publish import QzoneCommentPostService
from .remark.threader import QzoneCommentReplyService
from .reply.commentid import QzoneReplyIdentityService
from .reply.plans import QzoneReplyPlanService
from .reply.recipients import QzoneReplyTargetService
from .reply.replypayload import QzoneReplyPayloadService
from .reply.verify import QzoneReplyVerifyService
from .transport.cookie import QzoneH5CookieService
from .transport.header import QzoneHeaderService
from .transport.native import QzoneH5NativeService


class QzoneService:
    """聚合 QQ 空间网关、动态、评论、回复和上传组件。"""

    def relationship_target(self, uin: str) -> str:
        """返回实际空间客户端对应的原始框架私聊标识；不猜测其他账号。"""
        user_id = str(uin or "").strip()
        if not user_id.isascii() or not user_id.isdigit() or len(user_id) > 20:
            return ""
        if int(user_id) <= 0:
            return ""
        bot = self._get_bot()
        if bot is None:
            return ""
        matches = [
            binding
            for binding in get_platform_bindings(self.ctx_service.context)
            if binding.platform_type in ONEBOT_PLATFORM_TYPES
            and get_platform_client(binding.instance) is bot
        ]
        if len(matches) != 1 or matches[0].conflicted:
            return ""
        # route_id 是插件内部发送标识，关系档案使用框架原始 platform_id。
        return f"{matches[0].platform_id}:FriendMessage:{int(user_id)}"

    _REMOTE_IMAGE_CHUNK_SIZE = 64 * 1024
    _REMOTE_IMAGE_MAX_BYTES = 24 * 1024 * 1024
    _H5_MAX_RESPONSE_BYTES = QzoneH5BaseService._H5_MAX_RESPONSE_BYTES

    def _ensure_qzone_image_size(self, image_data: bytes) -> bytes:
        if len(image_data) > self._REMOTE_IMAGE_MAX_BYTES:
            raise RuntimeError("QQ 空间图片过大")
        return image_data

    async def _image_bytes(self, image) -> bytes:
        if isinstance(image, (bytes, bytearray, memoryview)):
            return self._ensure_qzone_image_size(bytes(image))
        text = str(image or "").strip()
        if not text:
            raise RuntimeError("QQ 空间图片为空")
        if text.startswith(("http://", "https://")):
            return await self._remote_image_bytes(text)
        if text.startswith("base64://"):
            encoded = text.removeprefix("base64://")
            decoded = await asyncio.to_thread(base64.b64decode, encoded)
            return self._ensure_qzone_image_size(decoded)
        path = Path(text)
        if await asyncio.to_thread(path.is_file):
            size = await asyncio.to_thread(lambda: path.stat().st_size)
            if size > self._REMOTE_IMAGE_MAX_BYTES:
                raise RuntimeError("QQ 空间图片过大")
            return self._ensure_qzone_image_size(
                await asyncio.to_thread(path.read_bytes)
            )
        raise RuntimeError(f"QQ 空间图片不存在: {text}")

    async def _remote_image_bytes(self, url: str) -> bytes:
        session = await self._http()
        async with session.get(url) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"下载 QQ 空间图片失败，接口状态码: {resp.status}")
            content_length = getattr(resp, "content_length", None)
            if content_length and content_length > self._REMOTE_IMAGE_MAX_BYTES:
                raise RuntimeError("下载 QQ 空间图片失败，图片过大")
            image_data = bytearray()
            async for chunk in resp.content.iter_chunked(self._REMOTE_IMAGE_CHUNK_SIZE):
                if chunk:
                    image_data.extend(chunk)
                if len(image_data) > self._REMOTE_IMAGE_MAX_BYTES:
                    raise RuntimeError("下载 QQ 空间图片失败，图片过大")
            return bytes(image_data)

    COOKIE_TTL_SECONDS: Any = QzoneServiceConstants.COOKIE_TTL_SECONDS
    API_TIMEOUT_SECONDS: Any = QzoneServiceConstants.API_TIMEOUT_SECONDS
    API_TIMEOUT_MIN_SECONDS: Any = QzoneServiceConstants.API_TIMEOUT_MIN_SECONDS
    API_TIMEOUT_MAX_SECONDS: Any = QzoneServiceConstants.API_TIMEOUT_MAX_SECONDS
    BASE_URL: Any = QzoneServiceConstants.BASE_URL
    UPLOAD_IMAGE_URL: Any = QzoneServiceConstants.UPLOAD_IMAGE_URL
    PHOTO_VIEW_URL: Any = QzoneServiceConstants.PHOTO_VIEW_URL
    PHOTO_COMMENT_URL: Any = QzoneServiceConstants.PHOTO_COMMENT_URL
    PHOTO_REPLY_URL: Any = QzoneServiceConstants.PHOTO_REPLY_URL
    PUBLISH_URL: Any = QzoneServiceConstants.PUBLISH_URL
    LIKE_URL: Any = QzoneServiceConstants.LIKE_URL
    LIST_URL: Any = QzoneServiceConstants.LIST_URL
    COMMENT_URL: Any = QzoneServiceConstants.COMMENT_URL
    H5_COMMENT_URL: Any = QzoneServiceConstants.H5_COMMENT_URL
    ADD_REPLY_UGC_URL: Any = QzoneServiceConstants.ADD_REPLY_UGC_URL
    SNS_COMMENT_URL: Any = QzoneServiceConstants.SNS_COMMENT_URL
    DELETE_COMMENT_URL: Any = QzoneServiceConstants.DELETE_COMMENT_URL
    SNS_DELETE_COMMENT_URL: Any = QzoneServiceConstants.SNS_DELETE_COMMENT_URL
    DETAIL_URL: Any = QzoneServiceConstants.DETAIL_URL
    DETAIL_H5_URL: Any = QzoneServiceConstants.DETAIL_H5_URL
    RECENT_URL: Any = QzoneServiceConstants.RECENT_URL
    HOME_FEED_URL: Any = QzoneServiceConstants.HOME_FEED_URL
    ABOUT_ME_URL: Any = QzoneServiceConstants.ABOUT_ME_URL
    LAST_YEAR_URL: Any = QzoneServiceConstants.LAST_YEAR_URL
    FAVORITE_URL: Any = QzoneServiceConstants.FAVORITE_URL
    MESSAGE_BOARD_URL: Any = QzoneServiceConstants.MESSAGE_BOARD_URL
    RELATION_URL: Any = QzoneServiceConstants.RELATION_URL
    VISITOR_URL: Any = QzoneServiceConstants.VISITOR_URL
    DELETE_URL: Any = QzoneServiceConstants.DELETE_URL
    H5_ORIGIN: Any = QzoneServiceConstants.H5_ORIGIN
    QZONE_COOKIE_DOMAINS: Any = QzoneServiceConstants.QZONE_COOKIE_DOMAINS
    QUERY_CACHE_TTL_SECONDS = 45
    QUERY_CACHE_MAX_ITEMS = 64
    DETAIL_CACHE_TTL_SECONDS = 180
    POST_CACHE_MAX_ITEMS = 500

    @staticmethod
    def _comment_id_aliases(comment):
        return QzoneReplyIdentityService._comment_id_aliases(comment)

    @staticmethod
    def _reply_submit_targets(post, comment, *, parent_comment=None):
        return QzoneReplyTargetService._reply_submit_targets(
            post, comment, parent_comment=parent_comment
        )

    @classmethod
    def _filter_thread_reply_targets(cls, post, comment, *, parent_comment, targets):
        return QzoneReplyTargetService._filter_thread_reply_targets(
            post, comment, parent_comment=parent_comment, targets=targets
        )

    @classmethod
    def unsafe_thread_reply_target_reason(cls, comment, *, parent_comment):
        return QzoneReplyTargetService.unsafe_thread_reply_target_reason(
            comment, parent_comment=parent_comment
        )

    @classmethod
    def _thread_reply_payload_variants(
        cls, post, comment, parent_comment, reply_targets
    ):
        return QzoneReplyPlanService._thread_reply_payload_variants(
            post, comment, parent_comment, reply_targets
        )

    @classmethod
    def _reply_verification_target_ids(cls, comment, *, parent_comment):
        return QzoneReplyVerifyService._reply_verification_target_ids(
            comment, parent_comment=parent_comment
        )

    @classmethod
    def _verify_thread_reply_in_post(
        cls,
        post,
        comment,
        content,
        *,
        self_uin,
        target_ids,
        parent_ids,
        before_ids,
        submitted_at,
    ):
        return QzoneReplyVerifyService._verify_thread_reply_in_post(
            post,
            comment,
            content,
            self_uin=self_uin,
            target_ids=target_ids,
            parent_ids=parent_ids,
            before_ids=before_ids,
            submitted_at=submitted_at,
        )

    def has_thread_reply_submit_plan(self, post, comment, *, parent_comment):
        return self.reply_targets.has_thread_reply_submit_plan(
            post, comment, parent_comment=parent_comment
        )

    def __init__(self, plugin):
        self._qzone_config = lambda: plugin.qzone_conf
        self._qq_adapter_id = lambda: plugin._cached_qq_adapter_id
        self.qzone_conf = plugin.qzone_conf
        self.ctx_service = plugin.ctx_service
        self._ctx: QzoneContext | None = None
        self._ctx_at = 0.0
        self._cache_bot = None
        self._ctx_fetch_lock = asyncio.Lock()
        self._session = None
        self._h2_session = None
        self._session_lock = asyncio.Lock()
        self._h2_session_lock = asyncio.Lock()
        self._session_timeout_seconds: int | None = None
        self._h2_timeout_seconds: int | None = None
        self._h5_transport = ""
        self._h5_transport_logged = False
        self._post_cache: dict[str, QzonePost] = {}
        self._post_detail_cache_at: dict[str, float] = {}
        self._query_cache: dict[
            tuple, tuple[float, list[QzonePost], dict[str, Any]]
        ] = {}
        self._last_friend_feeds_meta: dict[str, Any] = {}
        self.gateway = QzoneClientGateway(self)
        self.native = QzoneH5NativeService(self)
        self.headers = QzoneHeaderService(self)
        self.cookies = QzoneH5CookieService(self)
        self.timeline = QzoneFeedQueryService(self)
        self.errors = QzoneH5ErrorService(self)
        self.packets = QzoneH5BaseService(self)
        self.requests = QzoneH5RequestService(self)
        self.replies = QzoneCommentReplyService(self)
        self.comment_tools = QzoneCommentUtilService(self)
        self.comments = QzoneCommentPostService(self)
        self.deletion = QzoneCommentDeleteService(self)
        self.details = QzoneFeedDetailService(self)
        self.extra = QzoneFeedExtraService(self)
        self.posts = QzoneFeedPostsService(self)
        self.home = QzoneFeedHomeService(self)
        self.recent = QzoneFeedRecentService(self)
        self.merge = QzoneFeedMergeService(self)
        self.reply_targets = QzoneReplyTargetService(self)
        self.reply_payloads = QzoneReplyPayloadService(self)
        self.reply_verification = QzoneReplyVerifyService(self)
        self.reply_plans = QzoneReplyPlanService(self)
        self.reply_identity = QzoneReplyIdentityService(self)
        self.photos = QzonePhotoService(self)

    async def close(self):
        return await self.gateway.close()

    def invalidate(self):
        return self.gateway.invalidate()

    def configured(self):
        return self.gateway.configured()

    async def status(self):
        return await self.gateway.status()

    async def context(self):
        return await self.gateway.context()

    async def comment(self, post_id, content):
        return await self.comments.comment(post_id, content)

    async def query_photo_posts(self, post_id):
        """读取动态中明确标识的照片，分别建立可安全提交的目标。"""
        return await self.photos.query_photo_posts(post_id)

    async def query_photo(
        self, *, owner_uin, album_id, pic_key, photo_t="", comment_count=10
    ):
        return await self.photos.query_photo(
            owner_uin=owner_uin,
            album_id=album_id,
            pic_key=pic_key,
            photo_t=photo_t,
            comment_count=comment_count,
        )

    async def comment_photo(
        self, *, owner_uin, album_id, pic_key, content, feed_topic_id=""
    ):
        return await self.photos.comment_photo(
            owner_uin=owner_uin,
            album_id=album_id,
            pic_key=pic_key,
            content=content,
            feed_topic_id=feed_topic_id,
        )

    async def reply_photo_comment(
        self,
        *,
        owner_uin,
        album_id,
        pic_key,
        comment,
        content,
        feed_topic_id="",
        parent_comment=None,
    ):
        """在原照片评论楼层内回评，并 @ 当前被回复者。"""
        return await self.photos.reply_photo_comment(
            owner_uin=owner_uin,
            album_id=album_id,
            pic_key=pic_key,
            comment=comment,
            content=content,
            feed_topic_id=feed_topic_id,
            parent_comment=parent_comment,
        )

    async def delete_comment(self, post, comment_id, *, comment_uin=0, ctx=None):
        return await self.deletion.delete_comment(
            post, comment_id, comment_uin=comment_uin, ctx=ctx
        )

    async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
        return await self.replies.reply_comment(
            post_id, comment, content, parent_comment=parent_comment
        )

    async def detail(self, post_id):
        return await self.details.detail(post_id)

    @property
    def last_friend_feeds_meta(self):
        return self.timeline.last_friend_feeds_meta

    async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
        return await self.posts.query_posts(
            target_id=target_id, pos=pos, num=num, with_detail=with_detail
        )

    async def query_home_posts(self, *, pos=0, num=5):
        return await self.home.query_home_posts(pos=pos, num=num)

    async def query_recent_posts(self, *, pos=0, num=5, with_detail=False, cursor=""):
        return await self.recent.query_recent_posts(
            pos=pos, num=num, with_detail=with_detail, cursor=cursor
        )

    async def query_about_me(self, *, offset=0, count=10):
        return await self.extra.query_about_me(offset=offset, count=count)

    async def query_mention_posts(self, *, offset=0, count=10, with_detail=True):
        return await self.extra.query_mention_posts(
            offset=offset, count=count, with_detail=with_detail
        )

    async def query_last_year(self, *, year=None, count=10):
        return await self.extra.query_last_year(year=year, count=count)

    async def query_favorites(self, *, start=0, num=10, favorite_type=0):
        return await self.extra.query_favorites(
            start=start, num=num, favorite_type=favorite_type
        )

    async def query_message_board(self, *, target_id="", start=0, num=10):
        return await self.extra.query_message_board(
            target_id=target_id, start=start, num=num
        )

    async def query_relations(self, *, relation_type="care"):
        return await self.extra.query_relations(relation_type=relation_type)

    async def query_visit_stats(self):
        return await self.extra.query_visit_stats()

    @staticmethod
    def _base64_ascii(image_data: bytes) -> str:
        return base64.b64encode(image_data).decode("ascii")

    async def _upload_image(self, image) -> tuple[str, str]:
        ctx = await self.context()
        image_data = await self._image_bytes(image)
        encoded_image = await asyncio.to_thread(self._base64_ascii, image_data)
        filename = (
            "image.jpg"
            if str(image or "").strip().startswith("base64://")
            else os.path.basename(str(image) or "image.jpg")
        )
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
                "picfile": encoded_image,
            },
            headers=self._headers(
                ctx, referer=f"{self.BASE_URL}/{ctx.uin}", origin=self.BASE_URL
            ),
        )
        if not self._ok(payload, code_key="ret"):
            raise RuntimeError(
                str(
                    payload.get("msg")
                    or payload.get("message")
                    or "QQ 空间图片上传失败"
                )
            )
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
            data.update(
                pic_bo=",".join(pic_bos), richtype="1", richval="\t".join(richvals)
            )
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

    async def _submit_post(
        self, ctx: QzoneContext, data: dict[str, Any]
    ) -> dict[str, Any]:
        payload = await self._request(
            "POST",
            self.PUBLISH_URL,
            params={"g_tk": ctx.gtk2, "uin": ctx.uin},
            data=data,
        )
        if not self._ok(payload):
            raise RuntimeError(
                self._qzone_error_message(payload, "QQ 空间说说发布失败")
            )
        return payload

    @staticmethod
    def _normalized_publish_text(value: str) -> str:
        return " ".join(str(value or "").strip().split())

    async def _confirm_ambiguous_publish(
        self,
        ctx: QzoneContext,
        *,
        text: str,
        started_at: int,
    ) -> QzonePost | None:
        expected = self._normalized_publish_text(text)
        if not expected:
            return None
        self._invalidate_qzone_cache(target_id=str(ctx.uin))
        try:
            posts = await self.query_posts(target_id=str(ctx.uin), num=5)
        except Exception as exc:
            logger.warning(f"[日常分享] QQ 空间发布结果核验失败: {exc}")
            return None
        for post in posts:
            if int(post.uin or 0) != int(ctx.uin):
                continue
            if int(post.create_time or 0) < started_at - 30:
                continue
            if self._normalized_publish_text(post.text) == expected:
                return post
        return None

    async def publish_post(
        self, *, text: str = "", images: list | None = None
    ) -> QzonePost:
        ctx = await self.context()
        pic_bos = []
        richvals = []
        if images:
            logger.info(f"[日常分享] 正在上传 QQ 空间配图，共 {len(images)} 张...")
            for image in images:
                try:
                    picbo, richval = await self._upload_image(image)
                except Exception as exc:
                    raise QzoneImageUploadError(
                        f"QQ 空间配图上传失败（尚未提交说说）: {exc}"
                    ) from exc
                pic_bos.append(picbo)
                richvals.append(richval)
            logger.info("[日常分享] QQ 空间配图上传完成，正在发布说说...")

        data = self._publish_data(
            ctx,
            text=text or "",
            pic_bos=pic_bos,
            richvals=richvals,
        )
        submit_started_at = int(time.time())
        try:
            payload = await self._submit_post(ctx, data)
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            if any(
                key in message
                for key in (
                    "超时",
                    "Timeout",
                    "timeout",
                    "网络",
                    "Connection",
                    "disconnect",
                    "状态未知",
                )
            ):
                logger.warning(
                    f"[日常分享] QQ 空间说说提交状态未知: {message}，正在核验最新动态。"
                )
                await asyncio.sleep(2)
                confirmed = await self._confirm_ambiguous_publish(
                    ctx,
                    text=text,
                    started_at=submit_started_at,
                )
                if confirmed is not None:
                    logger.info("[日常分享] 已从最新动态确认 QQ 空间说说发布成功。")
                    return confirmed
                raise QzonePublishUnknownError(
                    "QQ 空间说说提交状态未知，为避免重复发布已停止自动重试；请先检查空间动态"
                ) from exc
            else:
                raise RuntimeError(f"QQ 空间说说发布失败: {message}") from exc
        raw_data = payload.get("data")
        publish_data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
        post = QzonePost(
            tid=str(payload.get("tid") or publish_data.get("tid") or ""),
            uin=ctx.uin,
            name=ctx.nickname or str(ctx.uin),
            text=text or "",
            create_time=int(
                payload.get("now") or publish_data.get("now") or time.time()
            ),
        )
        self._invalidate_qzone_cache(target_id=str(ctx.uin))
        self._remember_posts([post])
        return post

    async def like(self, post_id: str) -> None:
        post = self._require_post(post_id)
        if post.like_target_error:
            raise RuntimeError(post.like_target_error)
        if post.liked:
            return
        unikey, curkey = post.like_keys
        ctx = await self.context()
        referer = f"{self.BASE_URL}/{post.uin}/main"
        payload = await self._request(
            "POST",
            self.LIKE_URL,
            params={"g_tk": ctx.gtk},
            data={
                "qzreferrer": referer,
                "opuin": ctx.uin,
                "unikey": unikey,
                "curkey": curkey,
                "from": -100,
                "fupdate": 1,
                "face": 0,
            },
            headers=self._headers(
                ctx,
                Referer=referer,
                Accept="*/*",
                **{"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            ),
            retry_parse_error=False,
        )
        try:
            success = (
                int(payload["code"]) == 0
                and all(int(payload.get(key) or 0) == 0 for key in ("subcode", "ret"))
                and 200 <= int(payload.get("_http_status", 200)) < 300
            )
        except (KeyError, TypeError, ValueError):
            success = False
        if not success:
            message = self._payload_message(payload) or "QQ 空间点赞失败"
            raise RuntimeError(
                f"{message}（transport=pc_like, appid={post.appid}, "
                f"code={payload.get('code')}, subcode={payload.get('subcode')}, "
                f"ret={payload.get('ret')}, http={payload.get('_http_status')}）"
            )
        post.liked = True
        self._invalidate_qzone_cache(post_id=post.key, target_id=str(post.uin))

    async def delete_post(self, post_id: str) -> None:
        post = self._require_post(post_id)
        if not post.tid:
            raise RuntimeError("说说 ID 无效")
        ctx = await self.context()
        if int(post.uin or 0) != int(ctx.uin or 0):
            raise RuntimeError("只能删除自己发布的说说")
        await self._delete_own_post_by_tid(ctx, post.tid)
        self._invalidate_qzone_cache(
            post_id=post.key, target_id=str(post.uin), drop_post=True
        )

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
                logger.debug(
                    "[日常分享] QQ 空间删除接口返回内容不是结构化数据，但接口状态正常，按删除成功处理。"
                )
                return
            raise RuntimeError(str(payload.get("message") or "QQ 空间删除失败"))

    @staticmethod
    def _write_response_without_json_ok(payload: dict[str, Any]) -> bool:
        status = int(payload.get("_http_status") or 0)
        message = str(payload.get("message") or "")
        return (
            status in {200, 204}
            and bool(payload.get("_raw_blank"))
            and QzoneService._write_response_without_json_message(message)
        )

    @staticmethod
    def _write_response_without_json_message(message: str) -> bool:
        base = str(message or "").split("（", 1)[0].strip()
        return base in {
            "QQ 空间返回为空",
            "QQ 空间返回内容不是结构化数据",
            "QQ 空间响应解析失败",
            "QQ 空间响应格式异常",
        }

    def _remember_posts(
        self, posts: list[QzonePost], *, detailed: bool = False
    ) -> None:
        now = time.monotonic()
        for post in posts:
            self._post_cache[post.key] = post
            if detailed:
                self._post_detail_cache_at[post.key] = now
        self._prune_post_cache()

    @staticmethod
    def _query_cache_key(kind: str, **parts: Any) -> tuple:
        normalized = tuple(
            (key, str(value or "")) for key, value in sorted(parts.items())
        )
        return (kind, *normalized)

    def _cached_query_posts(self, cache_key: tuple) -> list[QzonePost] | None:
        self._ensure_bot_cache_scope()
        entry = self._query_cache.get(cache_key)
        if not entry:
            return None
        cached_at, posts, meta = entry
        if time.monotonic() - cached_at > self.QUERY_CACHE_TTL_SECONDS:
            self._query_cache.pop(cache_key, None)
            return None
        if meta:
            self._last_friend_feeds_meta = dict(meta)
        logger.debug("[日常分享] QQ 空间说说列表命中缓存")
        return list(posts)

    def _store_query_posts(
        self,
        cache_key: tuple,
        posts: list[QzonePost],
        *,
        meta: dict[str, Any] | None = None,
    ) -> None:
        self._query_cache[cache_key] = (
            time.monotonic(),
            list(posts or []),
            dict(meta or {}),
        )
        overflow = len(self._query_cache) - self.QUERY_CACHE_MAX_ITEMS
        if overflow > 0:
            for old_key in list(self._query_cache)[:overflow]:
                self._query_cache.pop(old_key, None)

    def _prune_post_cache(self) -> None:
        overflow = len(self._post_cache) - self.POST_CACHE_MAX_ITEMS
        if overflow <= 0:
            return
        for old_key in list(self._post_cache)[:overflow]:
            self._post_cache.pop(old_key, None)
            self._post_detail_cache_at.pop(old_key, None)

    def _clear_qzone_cache(self) -> None:
        self._post_cache.clear()
        self._post_detail_cache_at.clear()
        self._query_cache.clear()
        self._last_friend_feeds_meta = {}

    def _cached_detail_post(self, post_id: str) -> QzonePost | None:
        self._ensure_bot_cache_scope()
        key = str(post_id or "").strip()
        if not key:
            return None
        cached_at = self._post_detail_cache_at.get(key)
        post = self._post_cache.get(key)
        if not cached_at or post is None:
            return None
        if time.monotonic() - cached_at > self.DETAIL_CACHE_TTL_SECONDS:
            self._post_detail_cache_at.pop(key, None)
            return None
        logger.debug(f"[日常分享] QQ 空间说说详情命中缓存: {key}")
        return post

    def _invalidate_qzone_cache(
        self,
        *,
        post_id: str = "",
        target_id: str = "",
        drop_post: bool = False,
    ) -> None:
        target = str(target_id or "").strip()
        post_key = str(post_id or "").strip()
        if post_key and not target and ":" in post_key:
            target = post_key.split(":", 1)[0].strip()

        if post_key:
            self._post_detail_cache_at.pop(post_key, None)
            if drop_post:
                self._post_cache.pop(post_key, None)

        def affected(cache_key: tuple) -> bool:
            kind = cache_key[0] if cache_key else ""
            if kind in {"recent", "mention"}:
                return True
            if not target:
                return False
            return any(
                key in {"target", "target_id", "uin"} and value == target
                for key, value in cache_key[1:]
            )

        for cache_key in list(self._query_cache):
            if affected(cache_key):
                self._query_cache.pop(cache_key, None)

    def _require_post(self, post_id: str) -> QzonePost:
        self._ensure_bot_cache_scope()
        key = str(post_id or "").strip()
        post = self._post_cache.get(key)
        if post:
            return post
        if ":" in key:
            uin, tid = key.split(":", 1)
            if tid.startswith("photo:"):
                raise RuntimeError("相册照片引用已失效，请先刷新 QQ 空间动态")
            if uin.isdigit() and tid:
                post = QzonePost(uin=int(uin), tid=tid)
                self._post_cache[key] = post
                return post
        raise RuntimeError("说说引用已失效，请先刷新 QQ 空间动态")

    def _refresh_request_credentials(
        self, old_ctx, new_ctx, *, params=None, data=None, headers=None
    ):
        return self.gateway._refresh_request_credentials(
            old_ctx, new_ctx, params=params, data=data, headers=headers
        )

    def _ensure_bot_cache_scope(self):
        """登录态、列表和详情缓存属于同一个机器人实例。"""
        return self.gateway._ensure_bot_cache_scope()

    def _ensure_request_bot(self, bot, method):
        return self.gateway._ensure_request_bot(bot, method)

    def _get_bot(self):
        return self.gateway._get_bot()

    async def _fetch_bot_cookie(self, *, bot=None):
        return await self.gateway._fetch_bot_cookie(bot=bot)

    async def _context_from_cookie(self, cookie, *, bot=None):
        return await self.gateway._context_from_cookie(cookie, bot=bot)

    async def _bot_nickname(self, fallback, *, bot=None):
        return await self.gateway._bot_nickname(fallback, bot=bot)

    async def _http(self):
        return await self.gateway._http()

    async def _h2_http(self):
        return await self.gateway._h2_http()

    def _api_timeout_seconds(self):
        return self.gateway._api_timeout_seconds()

    async def _request(
        self,
        method,
        url,
        *,
        params=None,
        data=None,
        headers=None,
        retry=True,
        retry_parse_error=True,
    ):
        return await self.gateway._request(
            method,
            url,
            params=params,
            data=data,
            headers=headers,
            retry=retry,
            retry_parse_error=retry_parse_error,
        )

    async def _request_text(
        self, method, url, *, params=None, data=None, headers=None, retry=True
    ):
        return await self.gateway._request_text(
            method, url, params=params, data=data, headers=headers, retry=retry
        )

    @staticmethod
    def _ok(payload, *, code_key="code"):
        return QzoneClientGateway._ok(payload, code_key=code_key)

    @staticmethod
    def _h5_native_request_path(url, params=None):
        return QzoneH5NativeService._h5_native_request_path(url, params)

    async def _open_h5_native_h2_connection(self, parsed_url):
        return await self.native._open_h5_native_h2_connection(parsed_url)

    @staticmethod
    def _ensure_h5_native_h2_alpn(writer):
        return QzoneH5NativeService._ensure_h5_native_h2_alpn(writer)

    def _h5_native_h2_header_items(self, ctx, parsed_url, path, headers=None):
        return self.native._h5_native_h2_header_items(ctx, parsed_url, path, headers)

    @staticmethod
    def _send_h5_native_h2_request(writer, conn, header_items, body):
        return QzoneH5NativeService._send_h5_native_h2_request(
            writer, conn, header_items, body
        )

    def _handle_h5_native_h2_event(self, conn, event, response):
        return self.native._handle_h5_native_h2_event(conn, event, response)

    async def _read_h5_native_h2_response(self, reader, writer, conn):
        return await self.native._read_h5_native_h2_response(reader, writer, conn)

    @staticmethod
    def _close_h5_native_h2_writer(writer):
        return QzoneH5NativeService._close_h5_native_h2_writer(writer)

    async def _h5_post_json_native_h2(
        self, ctx, url, payload, *, params=None, headers=None
    ):
        return await self.native._h5_post_json_native_h2(
            ctx, url, payload, params=params, headers=headers
        )

    @staticmethod
    def _cookie_values_from_header(cookie):
        return QzoneHeaderService._cookie_values_from_header(cookie)

    @staticmethod
    def _cookie_header_from_values(values):
        return QzoneHeaderService._cookie_header_from_values(values)

    def _headers(self, ctx, **extra):
        return self.headers._headers(ctx, **extra)

    def _pc_form_headers(self, ctx, *, referer=""):
        return self.headers._pc_form_headers(ctx, referer=referer)

    def _comment_h5_headers(self, ctx, *, referer=""):
        return self.headers._comment_h5_headers(ctx, referer=referer)

    def _comment_sns_headers(self, ctx, *, referer=""):
        return self.headers._comment_sns_headers(ctx, referer=referer)

    def _feeds3_headers(self, ctx):
        return self.headers._feeds3_headers(ctx)

    @staticmethod
    def _has_cookie_header(headers):
        return QzoneHeaderService._has_cookie_header(headers)

    @staticmethod
    def _h5_cookie_uin(ctx):
        return QzoneH5CookieService._h5_cookie_uin(ctx)

    def _h5_minimal_cookie_header(self, ctx, *, o_prefix=False):
        return self.cookies._h5_minimal_cookie_header(ctx, o_prefix=o_prefix)

    def _h5_cookie_header(self, ctx, *, o_prefix=False):
        return self.cookies._h5_cookie_header(ctx, o_prefix=o_prefix)

    def _h5_headers(self, ctx):
        return self.cookies._h5_headers(ctx)

    def _h5_minimal_headers(self, ctx, *, o_prefix=False):
        return self.cookies._h5_minimal_headers(ctx, o_prefix=o_prefix)

    def _h5_cookie_variants(self, ctx):
        return self.cookies._h5_cookie_variants(ctx)

    def _h5_aiohttp_headers(self, ctx):
        return self.cookies._h5_aiohttp_headers(ctx)

    def _recent_posts_params(self, ctx, *, count, cursor=""):
        return self.timeline._recent_posts_params(ctx, count=count, cursor=cursor)

    def _friend_feeds_params(self, ctx, *, count, cursor=""):
        return self.timeline._friend_feeds_params(ctx, count=count, cursor=cursor)

    @staticmethod
    def _friend_feeds_next_cursor(payload):
        return QzoneFeedQueryService._friend_feeds_next_cursor(payload)

    @staticmethod
    def _friend_feeds_has_more(payload, posts):
        return QzoneFeedQueryService._friend_feeds_has_more(payload, posts)

    @staticmethod
    def _friend_feeds_payload_meta(payload):
        return QzoneFeedQueryService._friend_feeds_payload_meta(payload)

    def _h5_error_message(self, payload, fallback):
        return self.errors._h5_error_message(payload, fallback)

    @classmethod
    def _h5_transient_or_unstructured_failure(cls, payload):
        return QzoneH5ErrorService._h5_transient_or_unstructured_failure(payload)

    @staticmethod
    def _h5_transient_or_unstructured_message(message):
        return QzoneH5ErrorService._h5_transient_or_unstructured_message(message)

    @staticmethod
    def _h5_login_expired_message(message):
        return QzoneH5ErrorService._h5_login_expired_message(message)

    @classmethod
    def _h5_login_expired(cls, payload):
        return QzoneH5ErrorService._h5_login_expired(payload)

    def _with_h5_phase(self, message, phase):
        return self.errors._with_h5_phase(message, phase)

    @staticmethod
    def _h5_should_retry_http11(status, transport):
        return QzoneH5ErrorService._h5_should_retry_http11(status, transport)

    @staticmethod
    def _h5_should_retry_same_transport(status):
        return QzoneH5ErrorService._h5_should_retry_same_transport(status)

    def _h5_transport_error(self, exc, *, phase):
        return self.errors._h5_transport_error(exc, phase=phase)

    @staticmethod
    def _h5_json_body(payload):
        return QzoneH5BaseService._h5_json_body(payload)

    @staticmethod
    def _decode_h5_body(raw, encoding=""):
        return QzoneH5BaseService._decode_h5_body(raw, encoding)

    @staticmethod
    def _annotate_h5_response(payload, *, status, text, label, transport):
        return QzoneH5BaseService._annotate_h5_response(
            payload, status=status, text=text, label=label, transport=transport
        )

    @staticmethod
    def _h5_ok(payload):
        return QzoneH5BaseService._h5_ok(payload)

    async def _h5_post_json(
        self,
        ctx,
        url,
        payload,
        *,
        params=None,
        label="",
        prefer_native_h2=False,
        headers=None,
    ):
        return await self.requests._h5_post_json(
            ctx,
            url,
            payload,
            params=params,
            label=label,
            prefer_native_h2=prefer_native_h2,
            headers=headers,
        )

    async def _h5_post_bytes(
        self, ctx, url, body, content_type, *, params=None, label="", headers=None
    ):
        return await self.requests._h5_post_bytes(
            ctx, url, body, content_type, params=params, label=label, headers=headers
        )

    async def _h5_post_body_once(self, ctx, url, body, *, params, headers, use_h2):
        return await self.requests._h5_post_body_once(
            ctx, url, body, params=params, headers=headers, use_h2=use_h2
        )

    async def _h5_post_body(
        self, ctx, url, body, *, params=None, label="", headers, use_h2=True
    ):
        return await self.requests._h5_post_body(
            ctx, url, body, params=params, label=label, headers=headers, use_h2=use_h2
        )

    def _ensure_reply_plans(
        self, plans, *, thread_reply, post, comment, parent_comment, reply_targets
    ):
        return self.replies._ensure_reply_plans(
            plans,
            thread_reply=thread_reply,
            post=post,
            comment=comment,
            parent_comment=parent_comment,
            reply_targets=reply_targets,
        )

    @staticmethod
    def _reply_attempt_key(plan, data):
        return QzoneCommentReplyService._reply_attempt_key(plan, data)

    def _reply_attempt_debug(self, plan, data, payload):
        return self.replies._reply_attempt_debug(plan, data, payload)

    async def _verified_reply_result(
        self,
        post,
        comment,
        content,
        *,
        parent_comment,
        ctx,
        submitted_at,
        thread_reply,
        plan,
        attempt,
        attempts,
        reply_targets,
    ):
        return await self.replies._verified_reply_result(
            post,
            comment,
            content,
            parent_comment=parent_comment,
            ctx=ctx,
            submitted_at=submitted_at,
            thread_reply=thread_reply,
            plan=plan,
            attempt=attempt,
            attempts=attempts,
            reply_targets=reply_targets,
        )

    @staticmethod
    def _payload_message(payload):
        return QzoneCommentUtilService._payload_message(payload)

    @staticmethod
    def _decode_mojibake(value):
        return QzoneCommentUtilService._decode_mojibake(value)

    @staticmethod
    def _reply_target_unavailable(payload):
        return QzoneCommentUtilService._reply_target_unavailable(payload)

    @staticmethod
    def _reply_content(content, comment):
        return QzoneCommentUtilService._reply_content(content, comment)

    def _comment_submit_ok(self, payload):
        return self.comment_tools._comment_submit_ok(payload)

    async def _delete_comment_via_sns(self, ctx, post, *, comment_id, comment_uin):
        return await self.deletion._delete_comment_via_sns(
            ctx, post, comment_id=comment_id, comment_uin=comment_uin
        )

    async def _delete_comment_via_pc(self, ctx, post, *, comment_id):
        return await self.deletion._delete_comment_via_pc(
            ctx, post, comment_id=comment_id
        )

    @staticmethod
    def _parse_detail_post(payload):
        return QzoneFeedDetailService._parse_detail_post(payload)

    async def _safe_post_detail(self, post):
        return await self.details._safe_post_detail(post)

    async def _query_recent_post_details(self, posts):
        return await self.recent._query_recent_post_details(posts)

    @classmethod
    def _merge_post_detail(cls, base, detail):
        return QzoneFeedMergeService._merge_post_detail(base, detail)

    @classmethod
    def _merge_comments(cls, base_comments, detail_comments):
        return QzoneFeedMergeService._merge_comments(base_comments, detail_comments)

    @classmethod
    def _match_detail_comment(
        cls,
        base_comment,
        detail_comments,
        *,
        detail_by_tid,
        detail_by_submit_tid,
        used_detail,
    ):
        return QzoneFeedMergeService._match_detail_comment(
            base_comment,
            detail_comments,
            detail_by_tid=detail_by_tid,
            detail_by_submit_tid=detail_by_submit_tid,
            used_detail=used_detail,
        )

    @staticmethod
    def _comments_equivalent(left, right):
        return QzoneFeedMergeService._comments_equivalent(left, right)

    @staticmethod
    def _comment_submit_tid_rank(value):
        return QzoneFeedMergeService._comment_submit_tid_rank(value)

    @classmethod
    def _prefer_submit_tid(cls, *values):
        return QzoneFeedMergeService._prefer_submit_tid(*values)

    @classmethod
    def _merge_comment(cls, base_comment, detail_comment):
        return QzoneFeedMergeService._merge_comment(base_comment, detail_comment)

    @staticmethod
    def _prefer_h5_reply(comment, *, parent_comment=None):
        return QzoneReplyTargetService._prefer_h5_reply(
            comment, parent_comment=parent_comment
        )

    @classmethod
    def _can_try_addreply_ugc_thread_variant(
        cls, post, comment, *, parent_comment, child_seq
    ):
        return QzoneReplyTargetService._can_try_addreply_ugc_thread_variant(
            post, comment, parent_comment=parent_comment, child_seq=child_seq
        )

    @classmethod
    def _self_reply_thread_state(cls, post, *, self_uin, parent_tid, reply_to_tid):
        return QzoneReplyTargetService._self_reply_thread_state(
            post, self_uin=self_uin, parent_tid=parent_tid, reply_to_tid=reply_to_tid
        )

    @classmethod
    def _unsafe_thread_reply_target_reason(cls, comment, *, parent_comment):
        return QzoneReplyTargetService._unsafe_thread_reply_target_reason(
            comment, parent_comment=parent_comment
        )

    @staticmethod
    def _is_short_numeric_comment_id(value):
        return QzoneReplyTargetService._is_short_numeric_comment_id(value)

    @classmethod
    def _h5_reply_target_id(cls, comment_id, comment):
        return QzoneReplyPayloadService._h5_reply_target_id(comment_id, comment)

    def _mood_v6_referrer(self, post):
        return self.reply_payloads._mood_v6_referrer(post)

    def _h5_comment_data(
        self,
        ctx,
        post,
        *,
        content,
        comment_id="",
        comment_uin=0,
        comment=None,
        payload_comment_id="",
        payload_t2_tid="",
        payload_t2_uin=0,
        reply_uin=0,
        topic_id="",
    ):
        return self.reply_payloads._h5_comment_data(
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

    def _h5_thread_parent_comment_data(
        self, ctx, post, *, content, comment_id, comment_uin, topic_id="", qzreferrer=""
    ):
        return self.reply_payloads._h5_thread_parent_comment_data(
            ctx,
            post,
            content=content,
            comment_id=comment_id,
            comment_uin=comment_uin,
            topic_id=topic_id,
            qzreferrer=qzreferrer,
        )

    def _addreply_ugc_comment_data(
        self,
        ctx,
        post,
        *,
        content,
        comment_id,
        comment_uin,
        payload_comment_id="",
        topic_id="",
    ):
        return self.reply_payloads._addreply_ugc_comment_data(
            ctx,
            post,
            content=content,
            comment_id=comment_id,
            comment_uin=comment_uin,
            payload_comment_id=payload_comment_id,
            topic_id=topic_id,
        )

    def _sns_comment_data(
        self,
        ctx,
        post,
        *,
        content,
        comment_id,
        comment_uin,
        comment=None,
        payload_comment_id="",
        payload_t2_tid="",
        payload_t2_uin=0,
        reply_uin=0,
        topic_id="",
    ):
        return self.reply_payloads._sns_comment_data(
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

    async def _verify_thread_reply_submission(
        self, post, comment, content, *, parent_comment, ctx, submitted_at
    ):
        return await self.reply_verification._verify_thread_reply_submission(
            post,
            comment,
            content,
            parent_comment=parent_comment,
            ctx=ctx,
            submitted_at=submitted_at,
        )

    async def _cleanup_failed_thread_reply(self, post, verification, *, ctx):
        return await self.reply_verification._cleanup_failed_thread_reply(
            post, verification, ctx=ctx
        )

    @classmethod
    def _reply_verification_existing_self_ids(cls, post, self_uin):
        return QzoneReplyVerifyService._reply_verification_existing_self_ids(
            post, self_uin
        )

    @classmethod
    def _comment_alias_map(cls, comments):
        return QzoneReplyVerifyService._comment_alias_map(comments)

    @classmethod
    def _reply_verification_target_status(
        cls, item, *, aliases, target_ids, parent_ids, target_uin
    ):
        return QzoneReplyVerifyService._reply_verification_target_status(
            item,
            aliases=aliases,
            target_ids=target_ids,
            parent_ids=parent_ids,
            target_uin=target_uin,
        )

    @classmethod
    def _reply_verification_text_variants(cls, content):
        return QzoneReplyVerifyService._reply_verification_text_variants(content)

    @staticmethod
    def _normalize_reply_verification_text(content):
        return QzoneReplyVerifyService._normalize_reply_verification_text(content)

    @classmethod
    def _reply_verification_text_matches(cls, item, expected_texts):
        return QzoneReplyVerifyService._reply_verification_text_matches(
            item, expected_texts
        )

    @classmethod
    def _reply_verification_is_new_self_comment(cls, item, *, before_ids, submitted_at):
        return QzoneReplyVerifyService._reply_verification_is_new_self_comment(
            item, before_ids=before_ids, submitted_at=submitted_at
        )

    @staticmethod
    def _reply_verification_candidate_debug(
        item, *, text_matches, is_new, target_status
    ):
        return QzoneReplyVerifyService._reply_verification_candidate_debug(
            item, text_matches=text_matches, is_new=is_new, target_status=target_status
        )

    @staticmethod
    def _reply_verification_debug_fields(verification):
        return QzoneReplyVerifyService._reply_verification_debug_fields(verification)

    @staticmethod
    def _reply_verification_error_message(verification):
        return QzoneReplyVerifyService._reply_verification_error_message(verification)

    @classmethod
    def _attach_reply_failure_debug(
        cls, exc, *, attempts, attempted_targets, verification=None
    ):
        return QzoneReplyVerifyService._attach_reply_failure_debug(
            exc,
            attempts=attempts,
            attempted_targets=attempted_targets,
            verification=verification,
        )

    def _reply_submit_plans(
        self, ctx, post, comment, *, content, parent_comment, reply_targets, prefer_h5
    ):
        return self.reply_plans._reply_submit_plans(
            ctx,
            post,
            comment,
            content=content,
            parent_comment=parent_comment,
            reply_targets=reply_targets,
            prefer_h5=prefer_h5,
        )

    @staticmethod
    def _thread_reply_re_feeds_payload_variants(
        post, comment, parent_comment, reply_targets
    ):
        return QzoneReplyPlanService._thread_reply_re_feeds_payload_variants(
            post, comment, parent_comment, reply_targets
        )

    def _reply_submit_plan(self, ctx, post, comment, *, content, transport, variant):
        return self.reply_plans._reply_submit_plan(
            ctx, post, comment, content=content, transport=transport, variant=variant
        )

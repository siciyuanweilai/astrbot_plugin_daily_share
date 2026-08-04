from __future__ import annotations

import asyncio
import base64
import os
import time
from pathlib import Path
from typing import Any, cast

from astrbot.api import logger

from .endpoints import QzoneServiceConstants
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

    _REMOTE_IMAGE_CHUNK_SIZE = 64 * 1024
    _REMOTE_IMAGE_MAX_BYTES = 24 * 1024 * 1024

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
    def _reply_submit_targets(*args, **kwargs):
        return QzoneReplyTargetService._reply_submit_targets(*args, **kwargs)

    @classmethod
    def _filter_thread_reply_targets(cls, *args, **kwargs):
        return QzoneReplyTargetService._filter_thread_reply_targets(*args, **kwargs)

    @classmethod
    def unsafe_thread_reply_target_reason(cls, *args, **kwargs):
        return QzoneReplyTargetService.unsafe_thread_reply_target_reason(
            *args, **kwargs
        )

    @classmethod
    def _thread_reply_payload_variants(cls, *args, **kwargs):
        return QzoneReplyPlanService._thread_reply_payload_variants(*args, **kwargs)

    @classmethod
    def _reply_verification_target_ids(cls, *args, **kwargs):
        return QzoneReplyVerifyService._reply_verification_target_ids(*args, **kwargs)

    @classmethod
    def _verify_thread_reply_in_post(cls, *args, **kwargs):
        return QzoneReplyVerifyService._verify_thread_reply_in_post(*args, **kwargs)

    def has_thread_reply_submit_plan(self, *args, **kwargs):
        return QzoneReplyTargetService.has_thread_reply_submit_plan(
            self, *args, **kwargs
        )

    def __init__(self, plugin):
        self._qzone_config = lambda: plugin.qzone_conf
        self._qq_adapter_id = lambda: plugin._cached_qq_adapter_id
        self.qzone_conf = plugin.qzone_conf
        self.ctx_service = plugin.ctx_service
        self._ctx: QzoneContext | None = None
        self._ctx_at = 0.0
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

    _addreply_ugc_comment_data: Any = (
        QzoneReplyPayloadService._addreply_ugc_comment_data
    )
    _annotate_h5_response = staticmethod(QzoneH5BaseService._annotate_h5_response)
    _api_timeout_seconds: Any = QzoneClientGateway._api_timeout_seconds
    _attach_reply_failure_debug: Any = classmethod(
        cast(Any, QzoneReplyVerifyService._attach_reply_failure_debug).__func__
    )
    _bot_nickname: Any = QzoneClientGateway._bot_nickname
    _can_try_addreply_ugc_thread_variant: Any = classmethod(
        cast(Any, QzoneReplyTargetService._can_try_addreply_ugc_thread_variant).__func__
    )
    _cleanup_failed_thread_reply: Any = (
        QzoneReplyVerifyService._cleanup_failed_thread_reply
    )
    _close_h5_native_h2_writer = staticmethod(
        QzoneH5NativeService._close_h5_native_h2_writer
    )
    _comment_alias_map: Any = classmethod(
        cast(Any, QzoneReplyVerifyService._comment_alias_map).__func__
    )
    _comment_h5_headers: Any = QzoneHeaderService._comment_h5_headers
    _comment_sns_headers: Any = QzoneHeaderService._comment_sns_headers
    _comment_submit_ok: Any = QzoneCommentUtilService._comment_submit_ok
    _comment_submit_tid_rank = staticmethod(
        QzoneFeedMergeService._comment_submit_tid_rank
    )
    _comments_equivalent = staticmethod(QzoneFeedMergeService._comments_equivalent)
    _context_from_cookie: Any = QzoneClientGateway._context_from_cookie
    _cookie_header_from_values = staticmethod(
        QzoneHeaderService._cookie_header_from_values
    )
    _cookie_values_from_header = staticmethod(
        QzoneHeaderService._cookie_values_from_header
    )
    _decode_h5_body = staticmethod(QzoneH5BaseService._decode_h5_body)
    _decode_mojibake = staticmethod(QzoneCommentUtilService._decode_mojibake)
    _delete_comment_via_pc: Any = QzoneCommentDeleteService._delete_comment_via_pc
    _delete_comment_via_sns: Any = QzoneCommentDeleteService._delete_comment_via_sns
    _ensure_h5_native_h2_alpn = staticmethod(
        QzoneH5NativeService._ensure_h5_native_h2_alpn
    )
    _ensure_reply_plans: Any = QzoneCommentReplyService._ensure_reply_plans
    _feeds3_headers: Any = QzoneHeaderService._feeds3_headers
    _fetch_bot_cookie: Any = QzoneClientGateway._fetch_bot_cookie
    _friend_feeds_has_more = staticmethod(QzoneFeedQueryService._friend_feeds_has_more)
    _friend_feeds_next_cursor = staticmethod(
        QzoneFeedQueryService._friend_feeds_next_cursor
    )
    _friend_feeds_params: Any = QzoneFeedQueryService._friend_feeds_params
    _friend_feeds_payload_meta = staticmethod(
        QzoneFeedQueryService._friend_feeds_payload_meta
    )
    _get_bot: Any = QzoneClientGateway._get_bot
    _h2_http: Any = QzoneClientGateway._h2_http
    _h5_aiohttp_headers: Any = QzoneH5CookieService._h5_aiohttp_headers
    _h5_comment_data: Any = QzoneReplyPayloadService._h5_comment_data
    _h5_cookie_header: Any = QzoneH5CookieService._h5_cookie_header
    _h5_cookie_uin = staticmethod(QzoneH5CookieService._h5_cookie_uin)
    _h5_cookie_variants: Any = QzoneH5CookieService._h5_cookie_variants
    _h5_error_message: Any = QzoneH5ErrorService._h5_error_message
    _h5_headers: Any = QzoneH5CookieService._h5_headers
    _h5_json_body = staticmethod(QzoneH5BaseService._h5_json_body)
    _h5_login_expired: Any = classmethod(
        cast(Any, QzoneH5ErrorService._h5_login_expired).__func__
    )
    _h5_login_expired_message = staticmethod(
        QzoneH5ErrorService._h5_login_expired_message
    )
    _h5_minimal_cookie_header: Any = QzoneH5CookieService._h5_minimal_cookie_header
    _h5_minimal_headers: Any = QzoneH5CookieService._h5_minimal_headers
    _h5_native_h2_header_items: Any = QzoneH5NativeService._h5_native_h2_header_items
    _h5_native_request_path = staticmethod(QzoneH5NativeService._h5_native_request_path)
    _h5_ok = staticmethod(QzoneH5BaseService._h5_ok)
    _h5_post_body: Any = QzoneH5RequestService._h5_post_body
    _h5_post_body_once: Any = QzoneH5RequestService._h5_post_body_once
    _h5_post_bytes: Any = QzoneH5RequestService._h5_post_bytes
    _h5_post_json: Any = QzoneH5RequestService._h5_post_json
    _h5_post_json_native_h2: Any = QzoneH5NativeService._h5_post_json_native_h2
    _h5_reply_target_id: Any = classmethod(
        cast(Any, QzoneReplyPayloadService._h5_reply_target_id).__func__
    )
    _h5_should_retry_http11 = staticmethod(QzoneH5ErrorService._h5_should_retry_http11)
    _h5_should_retry_same_transport = staticmethod(
        QzoneH5ErrorService._h5_should_retry_same_transport
    )
    _h5_thread_parent_comment_data: Any = (
        QzoneReplyPayloadService._h5_thread_parent_comment_data
    )
    _h5_transient_or_unstructured_failure: Any = classmethod(
        cast(Any, QzoneH5ErrorService._h5_transient_or_unstructured_failure).__func__
    )
    _h5_transient_or_unstructured_message = staticmethod(
        QzoneH5ErrorService._h5_transient_or_unstructured_message
    )
    _h5_transport_error: Any = QzoneH5ErrorService._h5_transport_error
    _handle_h5_native_h2_event: Any = QzoneH5NativeService._handle_h5_native_h2_event
    _has_cookie_header = staticmethod(QzoneHeaderService._has_cookie_header)
    _headers: Any = QzoneHeaderService._headers
    _http: Any = QzoneClientGateway._http
    _is_short_numeric_comment_id = staticmethod(
        QzoneReplyTargetService._is_short_numeric_comment_id
    )
    _match_detail_comment: Any = classmethod(
        cast(Any, QzoneFeedMergeService._match_detail_comment).__func__
    )
    _merge_comment: Any = classmethod(
        cast(Any, QzoneFeedMergeService._merge_comment).__func__
    )
    _merge_comments: Any = classmethod(
        cast(Any, QzoneFeedMergeService._merge_comments).__func__
    )
    _merge_post_detail: Any = classmethod(
        cast(Any, QzoneFeedMergeService._merge_post_detail).__func__
    )
    _mood_v6_referrer: Any = QzoneReplyPayloadService._mood_v6_referrer
    _normalize_reply_verification_text = staticmethod(
        QzoneReplyVerifyService._normalize_reply_verification_text
    )
    _ok = staticmethod(QzoneClientGateway._ok)
    _open_h5_native_h2_connection: Any = (
        QzoneH5NativeService._open_h5_native_h2_connection
    )
    _parse_detail_post = staticmethod(QzoneFeedDetailService._parse_detail_post)
    _payload_message = staticmethod(QzoneCommentUtilService._payload_message)
    _pc_form_headers: Any = QzoneHeaderService._pc_form_headers
    _prefer_h5_reply = staticmethod(QzoneReplyTargetService._prefer_h5_reply)
    _prefer_submit_tid: Any = classmethod(
        cast(Any, QzoneFeedMergeService._prefer_submit_tid).__func__
    )
    _query_recent_post_details: Any = QzoneFeedRecentService._query_recent_post_details
    _read_h5_native_h2_response: Any = QzoneH5NativeService._read_h5_native_h2_response
    _recent_posts_params: Any = QzoneFeedQueryService._recent_posts_params
    _reply_attempt_debug: Any = QzoneCommentReplyService._reply_attempt_debug
    _reply_attempt_key = staticmethod(QzoneCommentReplyService._reply_attempt_key)
    _reply_content = staticmethod(QzoneCommentUtilService._reply_content)
    _reply_submit_plan: Any = QzoneReplyPlanService._reply_submit_plan
    _reply_submit_plans: Any = QzoneReplyPlanService._reply_submit_plans
    _reply_target_unavailable = staticmethod(
        QzoneCommentUtilService._reply_target_unavailable
    )
    _reply_verification_candidate_debug = staticmethod(
        QzoneReplyVerifyService._reply_verification_candidate_debug
    )
    _reply_verification_debug_fields = staticmethod(
        QzoneReplyVerifyService._reply_verification_debug_fields
    )
    _reply_verification_error_message = staticmethod(
        QzoneReplyVerifyService._reply_verification_error_message
    )
    _reply_verification_existing_self_ids: Any = classmethod(
        cast(
            Any, QzoneReplyVerifyService._reply_verification_existing_self_ids
        ).__func__
    )
    _reply_verification_is_new_self_comment: Any = classmethod(
        cast(
            Any, QzoneReplyVerifyService._reply_verification_is_new_self_comment
        ).__func__
    )
    _reply_verification_target_status: Any = classmethod(
        cast(Any, QzoneReplyVerifyService._reply_verification_target_status).__func__
    )
    _reply_verification_text_matches: Any = classmethod(
        cast(Any, QzoneReplyVerifyService._reply_verification_text_matches).__func__
    )
    _reply_verification_text_variants: Any = classmethod(
        cast(Any, QzoneReplyVerifyService._reply_verification_text_variants).__func__
    )
    _request: Any = QzoneClientGateway._request
    _request_text: Any = QzoneClientGateway._request_text
    _safe_post_detail: Any = QzoneFeedDetailService._safe_post_detail
    _self_reply_thread_state: Any = classmethod(
        cast(Any, QzoneReplyTargetService._self_reply_thread_state).__func__
    )
    _send_h5_native_h2_request = staticmethod(
        QzoneH5NativeService._send_h5_native_h2_request
    )
    _sns_comment_data: Any = QzoneReplyPayloadService._sns_comment_data
    _thread_reply_re_feeds_payload_variants = staticmethod(
        QzoneReplyPlanService._thread_reply_re_feeds_payload_variants
    )
    _unsafe_thread_reply_target_reason: Any = classmethod(
        cast(Any, QzoneReplyTargetService._unsafe_thread_reply_target_reason).__func__
    )
    _verified_reply_result: Any = QzoneCommentReplyService._verified_reply_result
    _verify_thread_reply_submission: Any = (
        QzoneReplyVerifyService._verify_thread_reply_submission
    )
    _with_h5_phase: Any = QzoneH5ErrorService._with_h5_phase

    async def close(self) -> None:
        await QzoneClientGateway.close(self)

    def invalidate(self) -> None:
        QzoneClientGateway.invalidate(self)

    def configured(self) -> bool:
        return QzoneClientGateway.configured(self)

    async def status(self) -> dict:
        return await QzoneClientGateway.status(self)

    async def context(self) -> QzoneContext:
        return await QzoneClientGateway.context(self)

    async def comment(self, post_id: str, content: str) -> None:
        await QzoneCommentPostService.comment(self, post_id, content)

    async def delete_comment(
        self,
        post: QzonePost | str,
        comment_id: str,
        *,
        comment_uin: int = 0,
        ctx: QzoneContext | None = None,
    ) -> dict:
        return await QzoneCommentDeleteService.delete_comment(
            self,
            post,
            comment_id,
            comment_uin=comment_uin,
            ctx=ctx,
        )

    async def reply_comment(
        self,
        post_id: str,
        comment: QzoneComment,
        content: str,
        *,
        parent_comment: QzoneComment | None = None,
    ) -> dict[str, Any]:
        return await QzoneCommentReplyService.reply_comment(
            self,
            post_id,
            comment,
            content,
            parent_comment=parent_comment,
        )

    async def detail(self, post_id: str) -> QzonePost:
        return await QzoneFeedDetailService.detail(self, post_id)

    @property
    def last_friend_feeds_meta(self) -> dict[str, Any]:
        return QzoneFeedQueryService.last_friend_feeds_meta.fget(self)

    async def query_posts(
        self,
        *,
        target_id: str = "",
        pos: int = 0,
        num: int = 5,
        with_detail: bool = False,
    ) -> list[QzonePost]:
        return await QzoneFeedPostsService.query_posts(
            self,
            target_id=target_id,
            pos=pos,
            num=num,
            with_detail=with_detail,
        )

    async def query_home_posts(self, *, pos: int = 0, num: int = 5) -> list[QzonePost]:
        return await QzoneFeedHomeService.query_home_posts(self, pos=pos, num=num)

    async def query_recent_posts(
        self,
        *,
        pos: int = 0,
        num: int = 5,
        with_detail: bool = False,
        cursor: str = "",
    ) -> list[QzonePost]:
        return await QzoneFeedRecentService.query_recent_posts(
            self,
            pos=pos,
            num=num,
            with_detail=with_detail,
            cursor=cursor,
        )

    async def query_about_me(
        self, *, offset: int = 0, count: int = 10
    ) -> dict[str, Any]:
        return await QzoneFeedExtraService.query_about_me(
            self, offset=offset, count=count
        )

    async def query_mention_posts(
        self,
        *,
        offset: int = 0,
        count: int = 10,
        with_detail: bool = True,
    ) -> list[QzonePost]:
        return await QzoneFeedExtraService.query_mention_posts(
            self,
            offset=offset,
            count=count,
            with_detail=with_detail,
        )

    async def query_last_year(
        self, *, year: int | None = None, count: int = 10
    ) -> dict[str, Any]:
        return await QzoneFeedExtraService.query_last_year(self, year=year, count=count)

    async def query_favorites(
        self, *, start: int = 0, num: int = 10, favorite_type: int = 0
    ) -> dict[str, Any]:
        return await QzoneFeedExtraService.query_favorites(
            self,
            start=start,
            num=num,
            favorite_type=favorite_type,
        )

    async def query_message_board(
        self, *, target_id: str = "", start: int = 0, num: int = 10
    ) -> dict[str, Any]:
        return await QzoneFeedExtraService.query_message_board(
            self,
            target_id=target_id,
            start=start,
            num=num,
        )

    async def query_relations(self, *, relation_type: str = "care") -> dict[str, Any]:
        return await QzoneFeedExtraService.query_relations(
            self, relation_type=relation_type
        )

    async def query_visit_stats(self) -> dict[str, Any]:
        return await QzoneFeedExtraService.query_visit_stats(self)

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

    async def publish_post(
        self, *, text: str = "", images: list | None = None
    ) -> QzonePost:
        ctx = await self.context()
        pic_bos = []
        richvals = []
        if images:
            logger.info(f"[日常分享] 正在上传 QQ 空间配图，共 {len(images)} 张...")
            for image in images:
                picbo, richval = await self._upload_image(image)
                pic_bos.append(picbo)
                richvals.append(richval)
            logger.info("[日常分享] QQ 空间配图上传完成，正在发布说说...")

        data = self._publish_data(
            ctx,
            text=text or "",
            pic_bos=pic_bos,
            richvals=richvals,
        )
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
                )
            ):
                logger.warning(
                    f"[日常分享] QQ 空间说说发布失败: {message}，2 秒后复用已上传图片重试一次。"
                )
                await asyncio.sleep(2)
                try:
                    payload = await self._submit_post(ctx, data)
                except Exception as retry_exc:
                    retry_message = (
                        str(retry_exc).strip() or retry_exc.__class__.__name__
                    )
                    raise RuntimeError(
                        f"QQ 空间说说重试发布仍失败: {retry_message}"
                    ) from retry_exc
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
        post.liked = True

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

    def _cached_detail_post(self, post_id: str) -> QzonePost | None:
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

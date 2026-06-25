from __future__ import annotations

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ...toolkit import format_exception, log_exception


class TaskDeliverySendMixin:
    async def send(
        self,
        uid,
        text,
        img_path,
        audio_path=None,
        video_url=None,
        event: AstrMessageEvent = None,
        image_optional: bool = False,
        media_result: dict = None,
    ) -> bool:
        """分享内容（支持分开分享，支持语音和视频）"""
        if self.plugin._is_terminated:
            return False

        sent_any = False
        try:
            separate_img = self.image_conf.get("separate_text_and_image", True)
            if image_optional:
                separate_img = True
            clean_text = str(text or "").strip()
            should_send_text = not (audio_path and self.tts_conf.get("prefer_audio_only", False))

            downloaded_img_path, img_path = await self._prepare_delivery_image(
                uid,
                img_path,
                image_optional=image_optional,
            )
            self._init_media_result(
                media_result,
                downloaded_img_path=downloaded_img_path or "",
                img_path=img_path or "",
                video_url=video_url or "",
            )

            text_sent = False
            if should_send_text and clean_text:
                text_sent = await self._send_delivery_text(
                    uid,
                    clean_text,
                    img_path=img_path,
                    audio_path=audio_path,
                    video_url=video_url,
                    separate_img=separate_img,
                    event=event,
                    media_result=media_result,
                )
                sent_any = True

                if audio_path or ((img_path or video_url) and separate_img):
                    await self.random_sleep()

            if audio_path:
                await self._send_chain_stage(
                    uid,
                    self._build_audio_chain(audio_path),
                    "audio",
                    event,
                    media_result,
                )
                sent_any = True
                if (img_path or video_url) and separate_img:
                    await self.random_sleep()

            if video_url:
                await self._send_chain_stage(
                    uid,
                    self._build_video_chain(video_url),
                    "video",
                    event,
                    media_result,
                )
                sent_any = True
            elif img_path and (separate_img or audio_path):
                try:
                    await self._send_image_chain_with_retry(uid, img_path, event, media_result)
                    sent_any = True
                except Exception as image_error:
                    if image_optional and (text_sent or sent_any):
                        logger.warning(
                            f"[每日分享] 配图发送失败，已保留已发送内容: {format_exception(image_error)}"
                        )
                        return True
                    raise

            return sent_any

        except Exception as e:
            if sent_any or self._has_sent_stage(media_result):
                logger.warning(
                    f"[每日分享] 分享内容给 {uid} 部分已发送，后续阶段失败: {format_exception(e)}"
                )
                return True
            log_exception(f"[每日分享] 分享内容给 {uid} 失败", e, with_traceback=False)
            return False

    async def _prepare_delivery_image(
        self,
        uid: str,
        img_path: str,
        *,
        image_optional: bool,
    ) -> tuple[str | None, str | None]:
        downloaded_img_path = None
        if img_path and img_path.startswith("http"):
            filename = self._build_news_image_filename(img_path)
            dl_path = await self._download_image_to_local(img_path, filename)
            if dl_path:
                img_path = dl_path
                downloaded_img_path = dl_path
            else:
                logger.warning("[每日分享] 图片下载失败，已跳过发送该图片。")
                img_path = None

        img_path = await self._prepare_image_for_target(uid, img_path)
        if image_optional and img_path and self.ctx_service._is_weixin_platform(uid):
            img_path = await self._prepare_weixin_retry_image(img_path)
        return downloaded_img_path, img_path

    async def _send_delivery_text(
        self,
        uid: str,
        clean_text: str,
        *,
        img_path: str,
        audio_path: str,
        video_url: str,
        separate_img: bool,
        event: AstrMessageEvent = None,
        media_result: dict = None,
    ) -> bool:
        attach_image = bool(img_path and not video_url and not separate_img and not audio_path)
        await self._send_chain_stage(
            uid,
            self._build_text_chain(clean_text, img_path, attach_image=attach_image),
            "text",
            event,
            media_result,
        )
        if attach_image:
            self._mark_send_stage_success(media_result, "image")
        return True

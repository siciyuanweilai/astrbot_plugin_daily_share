from __future__ import annotations

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Record, Video

from ...toolkit import format_exception


class TaskDeliveryMediaMixin:
    async def _send_image_chain(
        self,
        uid: str,
        img_path: str,
        event: AstrMessageEvent = None,
        media_result: dict = None,
    ):
        await self._send_chain_stage(
            uid,
            self._build_image_chain(img_path),
            "image",
            event,
            media_result,
        )

    async def _send_image_chain_with_retry(
        self,
        uid: str,
        img_path: str,
        event: AstrMessageEvent = None,
        media_result: dict = None,
    ):
        errors_before = (
            len(media_result.get("partial_errors", []))
            if isinstance(media_result, dict)
            else 0
        )
        try:
            await self._send_image_chain(uid, img_path, event, media_result)
            return
        except Exception as first_error:
            if not self.ctx_service._is_weixin_platform(uid):
                raise

            retry_path = await self._prepare_weixin_retry_image(img_path)
            if not retry_path or retry_path == img_path:
                raise

            logger.warning(
                f"[每日分享] 个人微信平台图片发送失败，改用更小副本重试: {format_exception(first_error)}"
            )
            await self._send_image_chain(uid, retry_path, event, media_result)
            if isinstance(media_result, dict):
                errors = media_result.get("partial_errors", [])
                if len(errors) > errors_before:
                    del errors[errors_before:]

    def _build_text_chain(self, clean_text: str, img_path: str = "", *, attach_image: bool = False) -> MessageChain:
        chain = MessageChain().message(clean_text)
        if attach_image:
            self._append_image_to_chain(chain, img_path)
        return chain

    @staticmethod
    def _build_audio_chain(audio_path: str) -> MessageChain:
        chain = MessageChain()
        chain.chain.append(Record(file=audio_path))
        return chain

    @staticmethod
    def _build_video_chain(video_url: str) -> MessageChain:
        chain = MessageChain()
        if video_url.startswith("http"):
            chain.chain.append(Video.fromURL(video_url))
        else:
            chain.chain.append(Video.fromFileSystem(video_url))
        return chain

    def _build_image_chain(self, img_path: str) -> MessageChain:
        chain = MessageChain()
        self._append_image_to_chain(chain, img_path)
        return chain

    @staticmethod
    def _append_image_to_chain(chain: MessageChain, img_path: str) -> None:
        if img_path.startswith("http"):
            chain.url_image(img_path)
        else:
            chain.file_image(img_path)

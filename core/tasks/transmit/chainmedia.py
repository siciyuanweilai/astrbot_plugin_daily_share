from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Record, Video

from ...toolkit import format_exception
from ..taskbase import TaskServiceBase
from .chain import TaskDeliveryChainService

if TYPE_CHECKING:
    from ..runtime import TaskRuntime
    from ..taskbase import TaskConfigState, TaskSharedState


class TaskDeliveryMediaService(TaskServiceBase):
    """准备媒体、构建消息链，并处理微信图片缩小重试。"""

    def __init__(
        self,
        runtime: TaskRuntime,
        config: TaskConfigState,
        state: TaskSharedState,
        *,
        chains: TaskDeliveryChainService,
    ) -> None:
        super().__init__(runtime, config, state)
        self.chains = chains

    async def prepare_image(
        self,
        uid: str,
        img_path: str | None,
        *,
        image_optional: bool,
    ) -> tuple[str | None, str | None]:
        downloaded_img_path = None
        if img_path and img_path.startswith("http"):
            filename = self.services.delivery_assets.build_news_image_filename(img_path)
            dl_path = await self.services.delivery_assets.download_image_to_local(
                img_path, filename
            )
            if dl_path:
                img_path = dl_path
                downloaded_img_path = dl_path
            else:
                logger.warning("[日常分享] 图片下载失败，已跳过发送该图片。")
                img_path = None

        img_path = await self.services.weixin_delivery.prepare_image_for_target(
            uid, img_path
        )
        if image_optional and img_path and self.ctx_service.is_weixin_platform(uid):
            img_path = await self.services.weixin_delivery.prepare_weixin_retry_image(
                img_path
            )
        return downloaded_img_path, img_path

    async def send_image_chain(
        self,
        uid: str,
        img_path: str,
        event: AstrMessageEvent | None = None,
        media_result: dict | None = None,
    ):
        await self.chains.send_chain_stage(
            uid,
            self.build_image_chain(img_path),
            "image",
            event,
            media_result,
        )

    async def send_image_chain_with_retry(
        self,
        uid: str,
        img_path: str,
        event: AstrMessageEvent | None = None,
        media_result: dict | None = None,
    ):
        errors_before = (
            len(media_result.get("partial_errors", []))
            if isinstance(media_result, dict)
            else 0
        )
        try:
            await self.send_image_chain(uid, img_path, event, media_result)
            return
        except Exception as first_error:
            if not self.ctx_service.is_weixin_platform(uid):
                raise

            retry_path = await self.services.weixin_delivery.prepare_weixin_retry_image(
                img_path
            )
            if not retry_path or retry_path == img_path:
                raise

            logger.warning(
                f"[日常分享] 个人微信平台图片发送失败，改用更小副本重试: {format_exception(first_error)}"
            )
            await self.send_image_chain(uid, retry_path, event, media_result)
            if isinstance(media_result, dict):
                errors = media_result.get("partial_errors", [])
                if len(errors) > errors_before:
                    del errors[errors_before:]

    def build_text_chain(
        self, clean_text: str, img_path: str = "", *, attach_image: bool = False
    ) -> MessageChain:
        chain = MessageChain().message(clean_text)
        if attach_image:
            self._append_image_to_chain(chain, img_path)
        return chain

    @staticmethod
    def build_audio_chain(audio_path: str) -> MessageChain:
        chain = MessageChain()
        chain.chain.append(Record(file=audio_path))
        return chain

    @staticmethod
    def build_video_chain(video_url: str) -> MessageChain:
        chain = MessageChain()
        if video_url.startswith("http"):
            chain.chain.append(Video.fromURL(video_url))
        else:
            chain.chain.append(Video.fromFileSystem(video_url))
        return chain

    def build_image_chain(self, img_path: str) -> MessageChain:
        chain = MessageChain()
        self._append_image_to_chain(chain, img_path)
        return chain

    @staticmethod
    def _append_image_to_chain(chain: MessageChain, img_path: str) -> None:
        if img_path.startswith("http"):
            chain.url_image(img_path)
        else:
            chain.file_image(img_path)

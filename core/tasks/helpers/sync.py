import asyncio

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Video


class TaskHelperSyncMixin:
    """QQ 空间发布结果同步到触发会话。"""

    async def _sync_qzone_result_to_event(
        self,
        event: AstrMessageEvent,
        text: str,
        img_path: str = None,
        video_url: str = None,
    ):
        """QQ 空间发布成功后，把结果同步回当前触发会话。"""
        if not event:
            return

        target_uid = str(getattr(event, "unified_msg_origin", "") or "").strip()
        if target_uid and self.ctx_service._is_weixin_platform(target_uid):
            ok = await self.send(target_uid, text, img_path, video_url=video_url, event=event, image_optional=True)
            if not ok:
                logger.error("[每日分享] 同步发送内容到会话失败")
            return

        text_chain = MessageChain().message(text)
        await event.send(text_chain)

        if img_path:
            await asyncio.sleep(1.0)
            img_chain = MessageChain()
            if img_path.startswith("http"):
                img_chain.url_image(img_path)
            else:
                img_chain.file_image(img_path)
            await event.send(img_chain)
        if video_url:
            await asyncio.sleep(1.0)
            video_chain = MessageChain()
            if str(video_url).startswith("http"):
                video_chain.chain.append(Video.fromURL(video_url))
            else:
                video_chain.chain.append(Video.fromFileSystem(video_url))
            await event.send(video_chain)

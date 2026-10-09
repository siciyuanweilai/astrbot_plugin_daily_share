from datetime import datetime

from astrbot.api import logger

from ..space.errors import QzoneImageUploadError, QzonePublishUnknownError
from .supportcomponent import SupportComponent


class PluginQzoneService(SupportComponent):
    """内置 QQ 空间发布封装。"""

    async def publish_qzone(self, text: str = "", images: list | None = None):
        """发布 QQ 空间说说，登录态失效时重新获取登录态再重试一次。"""
        service = self.qzone_service
        if service is None:
            raise RuntimeError("QQ 空间服务未初始化")

        def error_message(exc: Exception) -> str:
            return str(exc).strip() or exc.__class__.__name__

        async def publish_once(*, action: str = "登录"):
            logger.info(f"[日常分享] 正在{action} QQ 空间并校验登录态...")
            ctx = await service.context()
            account = ctx.nickname or str(ctx.uin)
            logger.info(f"[日常分享] QQ 空间登录态已就绪: {account}({ctx.uin})")
            logger.info("[日常分享] 正在发布 QQ 空间说说...")
            post = await service.publish_post(text=text or "", images=images or [])
            try:
                bridge = getattr(self.plugin, "daily_life_bridge", None)
                record = getattr(bridge, "record_public_activity", None)
                if callable(record) and getattr(post, "tid", ""):
                    await record(
                        {
                            "event_id": f"qzone_post:{post.key}",
                            "scene": "qzone_post",
                            "post_id": post.key,
                            "content": text or "[公开图片]",
                            "image_sent": bool(images),
                            "occurred_at": datetime.now().isoformat(),
                        }
                    )
            except Exception as exc:
                logger.warning(
                    f"[日常分享] 说说已发布，回执登记失败：{type(exc).__name__}"
                )
            return post

        try:
            return await publish_once()
        except QzonePublishUnknownError:
            raise
        except Exception as exc:
            message = error_message(exc)
            if any(
                key in message
                for key in ("登录", "Cookie", "-100", "-3000", "失效", "403", "401")
            ):
                logger.info("[日常分享] QQ 空间登录态异常，正在重新登录后重试发布。")
                service.invalidate()
                try:
                    return await publish_once(action="重新登录")
                except QzonePublishUnknownError:
                    raise
                except Exception as retry_exc:
                    retry_message = error_message(retry_exc)
                    error_type = (
                        QzoneImageUploadError
                        if isinstance(retry_exc, QzoneImageUploadError)
                        else RuntimeError
                    )
                    raise error_type(
                        f"QQ 空间重新登录后发布仍失败: {retry_message}"
                    ) from retry_exc
            error_type = (
                QzoneImageUploadError
                if isinstance(exc, QzoneImageUploadError)
                else RuntimeError
            )
            raise error_type(f"QQ 空间发布失败: {message}") from exc

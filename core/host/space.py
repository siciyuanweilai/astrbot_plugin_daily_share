from astrbot.api import logger


class PluginQzoneMixin:
    """内置 QQ 空间发布封装。"""

    async def _safe_publish_qzone(self, text: str = "", images: list = None, videos: list = None):
        """发布 QQ 空间说说，登录态失效时重新获取登录态再重试一次。"""
        service = getattr(self, "qzone_service", None)
        if not service:
            raise RuntimeError("QQ 空间服务未初始化")

        def error_message(exc: Exception) -> str:
            return str(exc).strip() or exc.__class__.__name__

        async def publish_once(*, action: str = "登录"):
            logger.info(f"[每日分享] 正在{action} QQ 空间并校验登录态...")
            ctx = await service.context()
            account = ctx.nickname or str(ctx.uin)
            logger.info(f"[每日分享] QQ 空间登录态已就绪: {account}({ctx.uin})")
            logger.info("[每日分享] 正在发布 QQ 空间说说...")
            return await service.publish_post(text=text or "", images=images or [], videos=videos or [])

        try:
            return await publish_once()
        except Exception as exc:
            message = error_message(exc)
            if any(key in message for key in ("登录", "Cookie", "-100", "-3000", "失效", "403", "401")):
                logger.info("[每日分享] QQ 空间登录态异常，正在重新登录后重试发布。")
                service.invalidate()
                try:
                    return await publish_once(action="重新登录")
                except Exception as retry_exc:
                    retry_message = error_message(retry_exc)
                    raise RuntimeError(f"QQ 空间重新登录后发布仍失败: {retry_message}") from retry_exc
            raise RuntimeError(f"QQ 空间发布失败: {message}") from exc

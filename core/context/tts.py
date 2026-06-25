from .shared import Optional, ShareType, TimePeriod, logger

from ..toolkit import call_default_daily_life_media_tool


class ContextTtsMixin:
    def _resolve_voice_emotion(
        self,
        share_type: ShareType = None,
        period: TimePeriod = None,
    ) -> tuple[str, str]:
        if share_type == ShareType.GREETING:
            if period in (TimePeriod.DAWN, TimePeriod.LATE_NIGHT):
                return "安静的睡前问候", "neutral"
            return "轻快的问候", "happy"
        if share_type == ShareType.RECOMMENDATION:
            return "轻快的分享", "happy"
        if share_type == ShareType.MOOD:
            if period in (TimePeriod.DAWN, TimePeriod.LATE_NIGHT):
                return "安静的心情低语", "neutral"
            return "自然随性的心情", "neutral"
        if share_type == ShareType.NEWS:
            return "自然讲述", "neutral"
        if share_type == ShareType.KNOWLEDGE:
            return "清楚讲述", "neutral"
        return "自然讲述", "neutral"

    async def text_to_speech(
        self,
        text: str,
        target_umo: str,
        share_type: ShareType = None,
        period: TimePeriod = None,
        event=None,
    ) -> Optional[str]:
        """调用 daily_life 语音服务生成语音文件路径。"""
        if not self.tts_conf.get("enable_tts", False):
            return None

        if self._is_weixin_platform(target_umo):
            logger.info("[每日分享] 当前平台为个人微信，目前不支持发送语音，跳过语音发送。")
            return None

        final_text = str(text or "").strip()
        if not final_text:
            return None

        target_emotion, target_category = self._resolve_voice_emotion(share_type, period)
        return await call_default_daily_life_media_tool(
            self.context,
            media_kind="audio",
            prompt=final_text,
            text=final_text,
            emotion=target_emotion,
            emotion_category=target_category,
        )

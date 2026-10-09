from ..toolkit import call_default_daily_life_media_tool
from .contextbase import ContextComponent
from .shared import Optional, ShareType, TimePeriod, logger


class ContextTtsService(ContextComponent):
    def _resolve_voice_emotion(
        self,
        share_type: ShareType | None = None,
        period: TimePeriod | None = None,
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
        share_type: ShareType | None = None,
        period: TimePeriod | None = None,
        event=None,
    ) -> Optional[str]:
        """调用生活插件语音服务生成语音文件路径。"""
        if not self.tts_conf.get("enable_tts", False):
            return None

        if self.is_weixin_platform(target_umo):
            logger.info(
                "[日常分享] 当前平台为个人微信，目前不支持发送语音，跳过语音发送。"
            )
            return None

        final_text = str(text or "").strip()
        if not final_text:
            return None

        target_emotion, target_category = self._resolve_voice_emotion(
            share_type, period
        )
        voice_style = ""
        prepare = getattr(self.service.daily_life_bridge, "prepare_expression", None)
        if callable(prepare):
            expression = await prepare(final_text, scene="share_voice")
            target_emotion = str(expression.get("emotion") or "")
            target_category = str(expression.get("emotion_category") or "neutral")
            voice_style = str(expression.get("voice_style") or "neutral")
        return await call_default_daily_life_media_tool(
            self.context,
            media_kind="audio",
            prompt=final_text,
            text=final_text,
            emotion=target_emotion,
            emotion_category=target_category,
            voice_style=voice_style,
            event=event,
            bridge=self.service.daily_life_bridge,
        )

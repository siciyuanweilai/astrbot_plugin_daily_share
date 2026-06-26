from ..config import DEFAULT_KNOWLEDGE_CATS, DEFAULT_REC_CATS
from .common import _PAGE_BASIC_SEQUENCE_DEFAULTS, _PAGE_QZONE_SEQUENCE_DEFAULTS


class DashboardConfigPayloadMixin:
    """设置页配置数据组装。"""

    def _page_config_payload(self) -> dict:
        basic = self.config.setdefault("basic_conf", {})
        extra = self.config.setdefault("extra_shares", {})
        qzone = self.config.setdefault("qzone_conf", {})
        content = self.config.setdefault("content_library", {})
        image = self.config.setdefault("image_conf", {})
        tts = self.config.setdefault("tts_conf", {})
        news = self.config.setdefault("news_conf", {})
        receiver = self.config.setdefault("receiver", {})
        context_conf = self.config.setdefault("context_conf", {})
        llm = self.config.setdefault("llm_conf", {})
        return {
            "enabled": bool(self.config.get("enable_auto_share", False)),
            "sections": {
                "target": {
                    "groups": list(receiver.get("groups") or []),
                    "users": list(receiver.get("users") or []),
                    "briefing_groups": list(extra.get("briefing_groups") or []),
                    "briefing_users": list(extra.get("briefing_users") or []),
                    "contact_aliases": list(self.config.get("contact_aliases") or []),
                },
                "basic": {
                    "trigger_mode": basic.get("trigger_mode", "llm_smart"),
                    "fixed_times": list(basic.get("fixed_times") or ["08:00", "20:00"]),
                    "random_periods": list(basic.get("random_periods") or ["08:00-10:00", "19:00-21:00"]),
                    "share_cron": basic.get("share_cron", "0 8,20 * * *"),
                    "smart_schedule_max_count": int(basic.get("smart_schedule_max_count", 2) or 2),
                    "smart_schedule_quiet_hours": list(basic.get("smart_schedule_quiet_hours", ["23:30-07:30"]) or []),
                    "smart_schedule_prompt": str(basic.get("smart_schedule_prompt", "") or ""),
                    "cron_random_delay": int(basic.get("cron_random_delay", 0) or 0),
                    "share_type": basic.get("share_type", "自动"),
                    "data_retention_days": int(basic.get("data_retention_days", 60) or 60),
                    "dashboard_dynamic_days": int(basic.get("dashboard_dynamic_days", 60) or 60),
                },
                "sequence": {
                    key: list(basic.get(key) or default)
                    for key, default in _PAGE_BASIC_SEQUENCE_DEFAULTS.items()
                },
                "briefing": {
                    "enable_60s_news": bool(extra.get("enable_60s_news", False)),
                    "enable_ai_news": bool(extra.get("enable_ai_news", False)),
                    "sync_briefing_to_qzone": bool(extra.get("sync_briefing_to_qzone", False)),
                    "briefing_schedule_mode": extra.get("briefing_schedule_mode", "llm_smart"),
                    "briefing_fixed_times": list(extra.get("briefing_fixed_times") or ["08:00"]),
                    "briefing_random_periods": list(extra.get("briefing_random_periods") or ["08:00-09:00"]),
                    "cron_briefing": extra.get("cron_briefing", "0 8 * * *"),
                    "briefing_smart_schedule_max_count": int(extra.get("briefing_smart_schedule_max_count", 1) or 1),
                    "briefing_smart_schedule_quiet_hours": list(extra.get("briefing_smart_schedule_quiet_hours", ["23:30-07:30"]) or []),
                    "briefing_smart_schedule_prompt": str(extra.get("briefing_smart_schedule_prompt", "") or ""),
                    "briefing_cron_random_delay": int(extra.get("briefing_cron_random_delay", 0) or 0),
                },
                "qzone": {
                    "enable_qzone": bool(qzone.get("enable_qzone", False)),
                    "qzone_api_timeout_seconds": int(qzone.get("qzone_api_timeout_seconds", 120) or 120),
                    "qzone_trigger_mode": qzone.get("qzone_trigger_mode", "llm_smart"),
                    "qzone_fixed_times": list(qzone.get("qzone_fixed_times") or ["20:00"]),
                    "qzone_random_periods": list(qzone.get("qzone_random_periods") or ["19:00-21:00"]),
                    "qzone_cron": qzone.get("qzone_cron", "0 20 * * *"),
                    "qzone_smart_schedule_max_count": int(qzone.get("qzone_smart_schedule_max_count", 1) or 1),
                    "qzone_smart_schedule_quiet_hours": list(qzone.get("qzone_smart_schedule_quiet_hours", ["23:30-07:30"]) or []),
                    "qzone_smart_schedule_prompt": str(qzone.get("qzone_smart_schedule_prompt", "") or ""),
                    "qzone_share_type": qzone.get("qzone_share_type", "自动"),
                    "qzone_enable_image": bool(qzone.get("qzone_enable_image", False)),
                    "qzone_attach_hot_news_image": bool(qzone.get("qzone_attach_hot_news_image", True)),
                    "qzone_image_enabled_types": list(qzone.get("qzone_image_enabled_types") or ["问候", "心情"]),
                    "qzone_enable_video": bool(qzone.get("qzone_enable_video", False)),
                    "qzone_video_enabled_types": list(qzone.get("qzone_video_enabled_types") or ["问候", "心情"]),
                    "qzone_enable_auto_interaction": bool(qzone.get("qzone_enable_auto_interaction", False)),
                    "qzone_auto_interaction_interval_minutes": int(
                        qzone.get("qzone_auto_interaction_interval_minutes", 45)
                        or 0
                    ),
                    "qzone_auto_interaction_cron": qzone.get("qzone_auto_interaction_cron", "0 */2 * * *"),
                    "qzone_enable_auto_like": bool(qzone.get("qzone_enable_auto_like", False)),
                    "qzone_auto_like_limit": int(qzone.get("qzone_auto_like_limit", 3) or 3),
                    "qzone_enable_auto_comment": bool(qzone.get("qzone_enable_auto_comment", False)),
                    "qzone_auto_comment_limit": int(qzone.get("qzone_auto_comment_limit", 3) or 3),
                    "qzone_auto_comment_prompt": str(qzone.get("qzone_auto_comment_prompt", "") or ""),
                    "qzone_enable_auto_comment_image_vision": bool(
                        qzone.get("qzone_enable_auto_comment_image_vision", False)
                    ),
                    "qzone_auto_comment_image_vision_limit": int(
                        qzone.get("qzone_auto_comment_image_vision_limit", 1)
                        or 1
                    ),
                    "qzone_auto_comment_image_vision_provider": str(
                        qzone.get("qzone_auto_comment_image_vision_provider", "") or ""
                    ),
                    "qzone_enable_auto_reply": bool(qzone.get("qzone_enable_auto_reply", False)),
                    "qzone_auto_reply_limit": int(qzone.get("qzone_auto_reply_limit", 3) or 3),
                    "qzone_auto_reply_prompt": str(qzone.get("qzone_auto_reply_prompt", "") or ""),
                },
                "qzone_sequence": {
                    key: list(qzone.get(key) or default)
                    for key, default in _PAGE_QZONE_SEQUENCE_DEFAULTS.items()
                },
                "content": {
                    "knowledge_cats": self._page_category_lines(
                        content.get("knowledge_cats"), DEFAULT_KNOWLEDGE_CATS
                    ),
                    "rec_cats": self._page_category_lines(
                        content.get("rec_cats"), DEFAULT_REC_CATS
                    ),
                    "show_knowledge_type_prefix": bool(content.get("show_knowledge_type_prefix", True)),
                    "show_rec_type_prefix": bool(content.get("show_rec_type_prefix", True)),
                },
                "media": {
                    "enable_ai_image": bool(image.get("enable_ai_image", False)),
                    "attach_hot_news_image": bool(image.get("attach_hot_news_image", True)),
                    "news_image_cleanup_max_count": int(image.get("news_image_cleanup_max_count", 200) or 0),
                    "priority_text_over_schedule": bool(image.get("priority_text_over_schedule", True)),
                    "enable_ai_video": bool(image.get("enable_ai_video", False)),
                    "image_enabled_types": list(image.get("image_enabled_types") or ["问候", "心情", "知识", "推荐"]),
                    "video_enabled_types": list(image.get("video_enabled_types") or ["问候", "心情"]),
                    "separate_text_and_image": bool(image.get("separate_text_and_image", True)),
                    "separate_send_delay": str(image.get("separate_send_delay", "1.0-2.0") or "1.0-2.0"),
                    "record_image_description": bool(image.get("record_image_description", True)),
                    "appearance_prompt": str(image.get("appearance_prompt", "") or ""),
                    "image_always_include_self": bool(image.get("image_always_include_self", False)),
                    "image_never_include_self": bool(image.get("image_never_include_self", False)),
                    "enable_tts": bool(tts.get("enable_tts", False)),
                    "tts_enabled_types": list(tts.get("tts_enabled_types") or ["问候", "心情"]),
                    "prefer_audio_only": bool(tts.get("prefer_audio_only", False)),
                },
                "weixin": {
                    "weixin_compress_images": bool(image.get("weixin_compress_images", True)),
                    "weixin_image_max_side": int(image.get("weixin_image_max_side", 4096) or 4096),
                    "weixin_image_max_size_kb": int(image.get("weixin_image_max_size_kb", 10240) or 10240),
                    "weixin_api_timeout_seconds": int(image.get("weixin_api_timeout_seconds", 60) or 60),
                    "weixin_temp_cleanup_max_count": int(image.get("weixin_temp_cleanup_max_count", 10) or 0),
                },
                "context": {
                    "reference_history_count": int(context_conf.get("reference_history_count", 3) or 0),
                    "enable_life_context": bool(context_conf.get("enable_life_context", True)),
                    "life_context_in_group": bool(context_conf.get("life_context_in_group", True)),
                    "group_share_schedule": bool(context_conf.get("group_share_schedule", False)),
                    "enable_chat_history": bool(context_conf.get("enable_chat_history", True)),
                    "enable_deep_history": bool(context_conf.get("enable_deep_history", True)),
                    "deep_history_hours": int(context_conf.get("deep_history_hours", 24) or 24),
                    "deep_history_max_count": int(context_conf.get("deep_history_max_count", 50) or 50),
                    "private_history_count": int(context_conf.get("private_history_count", 20) or 20),
                    "group_intensity_check_count": int(context_conf.get("group_intensity_check_count", 30) or 30),
                    "group_share_strategy": context_conf.get("group_share_strategy", "cautious"),
                    "record_share_to_memory": bool(context_conf.get("record_share_to_memory", True)),
                },
                "news": {
                    "enable_news_api": bool(news.get("enable_news_api", True)),
                    "nycnm_api_key": str(news.get("nycnm_api_key", "") or ""),
                    "news_random_mode": news.get("news_random_mode", "config"),
                    "news_api_source": news.get("news_api_source", "zhihu"),
                    "news_random_sources": list(news.get("news_random_sources") or ["zhihu", "weibo", "bili"]),
                    "news_items_count": int(news.get("news_items_count", 5) or 5),
                    "news_share_count": str(news.get("news_share_count", "1-2") or "1-2"),
                    "news_api_timeout": int(news.get("news_api_timeout", 30) or 30),
                    "enable_tavily_search": bool(news.get("enable_tavily_search", True)),
                },
                "llm": {
                    "llm_provider_id": str(llm.get("llm_provider_id", "") or ""),
                    "llm_timeout": int(llm.get("llm_timeout", 120) or 120),
                    "use_persona": bool(llm.get("use_persona", True)),
                    "persona_id": str(llm.get("persona_id", "") or ""),
                },
            },
            "options": self._page_config_options(),
            "schema_meta": self._page_config_schema_meta(),
            "schema_values": self._page_config_schema_values(),
        }

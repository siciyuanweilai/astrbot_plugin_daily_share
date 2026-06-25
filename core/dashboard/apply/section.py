from __future__ import annotations

import re

from ...config import NEWS_SOURCE_MAP
from ..common import _PAGE_CONTEXT_STRATEGY_OPTIONS, _PAGE_NEWS_RANDOM_MODE_OPTIONS


class DashboardApplySectionMixin:
    def _page_apply_content_section(self, sections: dict) -> None:
        content_body = self._page_payload_section(sections, "content")
        content = self.config.setdefault("content_library", {})
        if "knowledge_cats" in content_body:
            content["knowledge_cats"] = self._page_list_value(
                content_body.get("knowledge_cats"), max_items=300, item_max_len=500
            )
        if "rec_cats" in content_body:
            content["rec_cats"] = self._page_list_value(
                content_body.get("rec_cats"), max_items=300, item_max_len=500
            )
        self._page_apply_bool_fields(
            content,
            content_body,
            ("show_knowledge_type_prefix", "show_rec_type_prefix"),
        )

    def _page_apply_media_section(self, sections: dict) -> None:
        media_body = self._page_payload_section(sections, "media")
        image = self.config.setdefault("image_conf", {})
        tts = self.config.setdefault("tts_conf", {})
        self._page_apply_bool_fields(
            image,
            media_body,
            (
                "enable_ai_image",
                "attach_hot_news_image",
                "priority_text_over_schedule",
                "enable_ai_video",
                "separate_text_and_image",
                "record_image_description",
                "image_always_include_self",
                "image_never_include_self",
            ),
        )
        self._page_apply_int_fields(
            image,
            media_body,
            (("news_image_cleanup_max_count", 200, 0, 1000),),
        )
        if "image_enabled_types" in media_body:
            image["image_enabled_types"] = self._page_type_list_value(
                media_body.get("image_enabled_types"), "配图类型"
            )
        if "video_enabled_types" in media_body:
            image["video_enabled_types"] = self._page_type_list_value(
                media_body.get("video_enabled_types"), "视频类型"
            )
        if "separate_send_delay" in media_body:
            image["separate_send_delay"] = self._page_delay_range_value(
                media_body.get("separate_send_delay"), "1.0-2.0"
            )
        if "appearance_prompt" in media_body:
            image["appearance_prompt"] = self._page_clean_text(
                media_body.get("appearance_prompt"), max_len=2000
            )
        self._page_apply_bool_fields(tts, media_body, ("enable_tts", "prefer_audio_only"))
        if "tts_enabled_types" in media_body:
            tts["tts_enabled_types"] = self._page_type_list_value(
                media_body.get("tts_enabled_types"), "语音类型"
            )

        weixin_body = self._page_payload_section(sections, "weixin")
        self._page_apply_bool_fields(image, weixin_body, ("weixin_compress_images",))
        self._page_apply_int_fields(
            image,
            weixin_body,
            (
                ("weixin_image_max_side", 4096, 1600, 8192),
                ("weixin_image_max_size_kb", 10240, 512, 40960),
                ("weixin_api_timeout_seconds", 60, 1, 180),
                ("weixin_temp_cleanup_max_count", 10, 0, 100),
            ),
        )

    def _page_apply_context_section(self, sections: dict) -> None:
        context_body = self._page_payload_section(sections, "context")
        context_conf = self.config.setdefault("context_conf", {})
        self._page_apply_bool_fields(
            context_conf,
            context_body,
            (
                "enable_life_context",
                "life_context_in_group",
                "group_share_schedule",
                "enable_chat_history",
                "enable_deep_history",
                "record_share_to_memory",
            ),
        )
        self._page_apply_int_fields(
            context_conf,
            context_body,
            (
                ("reference_history_count", 3, 0, 10),
                ("deep_history_hours", 24, 1, 168),
                ("deep_history_max_count", 50, 20, 200),
                ("private_history_count", 20, 5, 100),
                ("group_intensity_check_count", 30, 10, 100),
            ),
        )
        if "group_share_strategy" in context_body:
            context_conf["group_share_strategy"] = self._page_choice_value(
                context_body.get("group_share_strategy"),
                _PAGE_CONTEXT_STRATEGY_OPTIONS,
                "cautious",
                "群聊分享策略",
            )

    def _page_apply_news_section(self, sections: dict) -> None:
        news_body = self._page_payload_section(sections, "news")
        news = self.config.setdefault("news_conf", {})
        self._page_apply_bool_fields(news, news_body, ("enable_news_api", "enable_tavily_search"))
        if "nycnm_api_key" in news_body:
            news["nycnm_api_key"] = self._page_clean_text(news_body.get("nycnm_api_key"), max_len=200)
        if "news_random_mode" in news_body:
            news["news_random_mode"] = self._page_choice_value(
                news_body.get("news_random_mode"), _PAGE_NEWS_RANDOM_MODE_OPTIONS, "config", "新闻源模式"
            )
        if "news_api_source" in news_body:
            news["news_api_source"] = self._page_choice_value(
                news_body.get("news_api_source"), set(NEWS_SOURCE_MAP), "zhihu", "固定新闻源"
            )
        if "news_random_sources" in news_body:
            news["news_random_sources"] = self._page_news_source_list_value(
                news_body.get("news_random_sources"), "随机新闻源"
            )
        if news.get("news_random_mode") in {"config", "time_based"} and not news.get("news_random_sources"):
            raise RuntimeError("随机新闻源列表不能为空")
        self._page_apply_int_fields(
            news,
            news_body,
            (("news_items_count", 5, 1, 20),),
        )
        if "news_share_count" in news_body:
            share_count = self._page_clean_text(news_body.get("news_share_count"), max_len=16)
            if not re.match(r"^\d{1,2}(?:-\d{1,2})?$", share_count):
                raise RuntimeError("新闻分享条数格式应为数字或范围，例如 1-2")
            news["news_share_count"] = share_count
        self._page_apply_int_fields(
            news,
            news_body,
            (("news_api_timeout", 30, 1, 60),),
        )

    def _page_apply_llm_section(self, sections: dict) -> None:
        llm_body = self._page_payload_section(sections, "llm")
        llm = self.config.setdefault("llm_conf", {})
        if "llm_provider_id" in llm_body:
            llm["llm_provider_id"] = self._page_clean_text(llm_body.get("llm_provider_id"), max_len=160)
        self._page_apply_int_fields(
            llm,
            llm_body,
            (("llm_timeout", 120, 1, 180),),
        )
        self._page_apply_bool_fields(llm, llm_body, ("use_persona",))
        if "persona_id" in llm_body:
            llm["persona_id"] = self._page_clean_text(llm_body.get("persona_id"), max_len=160)

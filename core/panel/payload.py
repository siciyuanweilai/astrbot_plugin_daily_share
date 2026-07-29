from __future__ import annotations

from .panelcomponent import PanelComponent

from typing import Any

from ..config import DEFAULT_KNOWLEDGE_CATS, DEFAULT_REC_CATS
from .common import _PAGE_BASIC_SEQUENCE_DEFAULTS, _PAGE_QZONE_SEQUENCE_DEFAULTS


_FieldSpec = tuple[str, str, Any, bool]


def _field(
    key: str, kind: str, fallback: Any | None = None, *, zero_as_default: bool = False
) -> _FieldSpec:
    return (key, kind, fallback, zero_as_default)


_PAGE_BASIC_FIELDS: tuple[_FieldSpec, ...] = (
    _field("llm_provider_id", "str", ""),
    _field("llm_timeout", "int", 120, zero_as_default=True),
    _field("trigger_mode", "raw", "llm_smart"),
    _field("fixed_times", "list", ["08:00", "20:00"]),
    _field("random_periods", "list", ["08:00-10:00", "19:00-21:00"]),
    _field("share_cron", "raw", "0 8,20 * * *"),
    _field("smart_schedule_max_count", "int", 2, zero_as_default=True),
    _field("smart_schedule_quiet_hours", "list", ["23:30-07:30"]),
    _field("smart_schedule_prompt", "str", ""),
    _field("cron_random_delay", "int", 0),
    _field("share_type", "raw", "\u81ea\u52a8"),
    _field("share_output_format", "str", ""),
    _field("data_retention_days", "int", 60, zero_as_default=True),
    _field("dashboard_dynamic_days", "int", 60, zero_as_default=True),
)

_PAGE_BRIEFING_FIELDS: tuple[_FieldSpec, ...] = (
    _field("enable_60s_news", "bool", False),
    _field("enable_ai_news", "bool", False),
    _field("sync_briefing_to_qzone", "bool", False),
    _field("briefing_schedule_mode", "raw", "llm_smart"),
    _field("briefing_fixed_times", "list", ["08:00"]),
    _field("briefing_random_periods", "list", ["08:00-09:00"]),
    _field("cron_briefing", "raw", "0 8 * * *"),
    _field("briefing_smart_schedule_max_count", "int", 1, zero_as_default=True),
    _field("briefing_smart_schedule_quiet_hours", "list", ["23:30-07:30"]),
    _field("briefing_smart_schedule_prompt", "str", ""),
    _field("briefing_cron_random_delay", "int", 0),
)

_PAGE_QZONE_FIELDS: tuple[_FieldSpec, ...] = (
    _field("enable_qzone", "bool", False),
    _field("qzone_api_timeout_seconds", "int", 120, zero_as_default=True),
    _field("qzone_trigger_mode", "raw", "llm_smart"),
    _field("qzone_fixed_times", "list", ["20:00"]),
    _field("qzone_random_periods", "list", ["19:00-21:00"]),
    _field("qzone_cron", "raw", "0 20 * * *"),
    _field("qzone_cron_random_delay", "int", 0),
    _field("qzone_smart_schedule_max_count", "int", 1, zero_as_default=True),
    _field("qzone_smart_schedule_quiet_hours", "list", ["23:30-07:30"]),
    _field("qzone_smart_schedule_prompt", "str", ""),
    _field("qzone_share_type", "raw", "\u81ea\u52a8"),
    _field("qzone_share_output_format", "str", ""),
    _field("qzone_enable_image", "bool", False),
    _field("qzone_attach_hot_news_image", "bool", True),
    _field("qzone_image_enabled_types", "list", ["\u95ee\u5019", "\u5fc3\u60c5"]),
    _field("qzone_enable_auto_interaction", "bool", False),
    _field("qzone_auto_interaction_cron", "raw", "0 */2 * * *"),
    _field("qzone_auto_interaction_active_hours", "int", 24),
    _field("qzone_enable_auto_like", "bool", False),
    _field("qzone_auto_like_limit", "int", 3, zero_as_default=True),
    _field("qzone_enable_auto_comment", "bool", False),
    _field("qzone_auto_comment_limit", "int", 3, zero_as_default=True),
    _field("qzone_auto_comment_prompt", "str", ""),
    _field("qzone_enable_auto_comment_image_vision", "bool", False),
    _field("qzone_auto_comment_image_vision_limit", "int", 1, zero_as_default=True),
    _field("qzone_auto_comment_image_vision_provider", "str", ""),
    _field("qzone_enable_auto_reply", "bool", False),
    _field("qzone_auto_reply_limit", "int", 3, zero_as_default=True),
    _field("qzone_auto_reply_prompt", "str", ""),
)

_PAGE_MEDIA_FIELDS: tuple[_FieldSpec, ...] = (
    _field("enable_ai_image", "bool", False),
    _field("attach_hot_news_image", "bool", True),
    _field("news_image_cleanup_max_count", "int", 200),
    _field("priority_text_over_schedule", "bool", True),
    _field("enable_ai_video", "bool", False),
    _field(
        "image_enabled_types",
        "list",
        ["\u95ee\u5019", "\u5fc3\u60c5", "\u77e5\u8bc6", "\u63a8\u8350"],
    ),
    _field("video_enabled_types", "list", ["\u95ee\u5019", "\u5fc3\u60c5"]),
    _field("separate_text_and_image", "bool", True),
    _field("separate_send_delay", "str", "1.0-2.0"),
    _field("record_image_description", "bool", True),
    _field("appearance_prompt", "str", ""),
    _field("image_always_include_self", "bool", False),
    _field("image_never_include_self", "bool", False),
)

_PAGE_WEIXIN_FIELDS: tuple[_FieldSpec, ...] = (
    _field("weixin_compress_images", "bool", True),
    _field("weixin_image_max_side", "int", 4096, zero_as_default=True),
    _field("weixin_image_max_size_kb", "int", 10240, zero_as_default=True),
    _field("weixin_api_timeout_seconds", "int", 60, zero_as_default=True),
    _field("weixin_temp_cleanup_max_count", "int", 10),
)

_PAGE_TTS_FIELDS: tuple[_FieldSpec, ...] = (
    _field("enable_tts", "bool", False),
    _field("tts_enabled_types", "list", ["\u95ee\u5019", "\u5fc3\u60c5"]),
    _field("prefer_audio_only", "bool", False),
)

_PAGE_CONTEXT_FIELDS: tuple[_FieldSpec, ...] = (
    _field("reference_history_count", "int", 3),
    _field("enable_life_context", "bool", True),
    _field("life_context_in_group", "bool", True),
    _field("group_share_schedule", "bool", False),
    _field("enable_chat_history", "bool", True),
    _field("enable_deep_history", "bool", True),
    _field("deep_history_hours", "int", 24, zero_as_default=True),
    _field("deep_history_max_count", "int", 50, zero_as_default=True),
    _field("private_history_count", "int", 20, zero_as_default=True),
    _field("group_intensity_check_count", "int", 30, zero_as_default=True),
    _field("group_share_strategy", "raw", "cautious"),
    _field("record_share_to_memory", "bool", True),
)

_PAGE_NEWS_FIELDS: tuple[_FieldSpec, ...] = (
    _field("enable_news_api", "bool", True),
    _field("nycnm_api_key", "str", ""),
    _field("news_random_mode", "raw", "config"),
    _field("news_api_source", "raw", "zhihu"),
    _field("news_random_sources", "list", ["zhihu", "weibo", "bili"]),
    _field("news_items_count", "int", 5, zero_as_default=True),
    _field("news_share_count", "str", "1-2"),
    _field("news_api_timeout", "int", 30, zero_as_default=True),
    _field("enable_web_search", "bool", True),
)


class DashboardConfigPayloadService(PanelComponent):
    """设置页配置数据组装。"""

    def _page_field_default(
        self, config_key: str, field_key: str, fallback: Any
    ) -> Any:
        section = self.meta._page_config_schema().get(config_key, {})
        fields = section.get("items") if isinstance(section, dict) else {}
        field = fields.get(field_key) if isinstance(fields, dict) else None
        return (
            self.meta._page_schema_default(field)
            if isinstance(field, dict)
            else fallback
        )

    def _page_config_value(
        self,
        source: dict,
        config_key: str,
        field_key: str,
        kind: str,
        fallback: Any,
        *,
        zero_as_default: bool = False,
    ):
        default = self.payload._page_field_default(config_key, field_key, fallback)
        raw = source.get(field_key, default) if isinstance(source, dict) else default
        if raw in (None, "") or (zero_as_default and not raw):
            raw = default

        if kind == "bool":
            return bool(raw)
        if kind == "int":
            return int(raw or 0)
        if kind == "list":
            return list(raw or [])
        if kind == "str":
            return str(raw or "")
        return raw

    def _page_section_payload(
        self, config_key: str, source: dict, fields: tuple[_FieldSpec, ...]
    ) -> dict:
        return {
            key: self.payload._page_config_value(
                source,
                config_key,
                key,
                kind,
                fallback,
                zero_as_default=zero_as_default,
            )
            for key, kind, fallback, zero_as_default in fields
        }

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

        media = self.payload._page_section_payload(
            "image_conf", image, _PAGE_MEDIA_FIELDS
        )
        media.update(
            self.payload._page_section_payload("tts_conf", tts, _PAGE_TTS_FIELDS)
        )

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
                "basic": self.payload._page_section_payload(
                    "basic_conf", basic, _PAGE_BASIC_FIELDS
                ),
                "sequence": {
                    key: list(basic.get(key) or default)
                    for key, default in _PAGE_BASIC_SEQUENCE_DEFAULTS.items()
                },
                "briefing": self.payload._page_section_payload(
                    "extra_shares", extra, _PAGE_BRIEFING_FIELDS
                ),
                "qzone": self.payload._page_section_payload(
                    "qzone_conf", qzone, _PAGE_QZONE_FIELDS
                ),
                "qzone_sequence": {
                    key: list(qzone.get(key) or default)
                    for key, default in _PAGE_QZONE_SEQUENCE_DEFAULTS.items()
                },
                "content": {
                    "knowledge_cats": self.validation._page_category_lines(
                        content.get("knowledge_cats"), DEFAULT_KNOWLEDGE_CATS
                    ),
                    "rec_cats": self.validation._page_category_lines(
                        content.get("rec_cats"), DEFAULT_REC_CATS
                    ),
                    "show_knowledge_type_prefix": bool(
                        content.get("show_knowledge_type_prefix", True)
                    ),
                    "show_rec_type_prefix": bool(
                        content.get("show_rec_type_prefix", True)
                    ),
                },
                "media": media,
                "weixin": self.payload._page_section_payload(
                    "image_conf", image, _PAGE_WEIXIN_FIELDS
                ),
                "context": self.payload._page_section_payload(
                    "context_conf", context_conf, _PAGE_CONTEXT_FIELDS
                ),
                "news": self.payload._page_section_payload(
                    "news_conf", news, _PAGE_NEWS_FIELDS
                ),
            },
            "options": self.meta._page_config_options(),
            "schema_meta": self.meta._page_config_schema_meta(),
            "schema_values": self.meta._page_config_schema_values(),
        }

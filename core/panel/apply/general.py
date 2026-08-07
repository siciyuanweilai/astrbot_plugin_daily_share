from __future__ import annotations

from ...constants import TYPE_CN_MAP
from ...schedule import BRIEFING_SCHEDULE, GLOBAL_SCHEDULE
from ..common import (
    _PAGE_BASIC_SEQUENCE_DEFAULTS,
)
from ..panelcomponent import PanelComponent


class DashboardApplyBasicService(PanelComponent):
    def _page_apply_target_section(self, sections: dict) -> None:
        target_body = self.runtime.fields._page_payload_section(sections, "target")
        if "contact_aliases" in target_body:
            aliases = self.validation._page_contact_aliases_value(
                target_body.get("contact_aliases")
            )
            self.config["contact_aliases"] = aliases
            self.contact_aliases = aliases

    def _page_apply_basic_section(self, sections: dict) -> None:
        basic_body = self.runtime.fields._page_payload_section(sections, "basic")
        basic = self.config.setdefault("basic_conf", {})
        if "llm_provider_id" in basic_body:
            basic["llm_provider_id"] = self.validation._page_clean_text(
                basic_body.get("llm_provider_id"), max_len=160
            )
        self.schedule_apply._page_apply_schedule_fields(
            basic,
            basic_body,
            GLOBAL_SCHEDULE,
        )
        if "cron_random_delay" in basic_body:
            basic["cron_random_delay"] = self.validation._page_int_value(
                basic_body.get("cron_random_delay"), 0, min_value=0, max_value=60
            )
        if "share_type" in basic_body:
            share_type = self.validation._page_share_type(basic_body.get("share_type"))
            basic["share_type"] = (
                TYPE_CN_MAP[share_type.value] if share_type else "自动"
            )
        if "share_output_format" in basic_body:
            basic["share_output_format"] = self.validation._page_clean_text(
                basic_body.get("share_output_format"),
                max_len=1200,
            )
        self.fields._page_apply_int_fields(
            basic,
            basic_body,
            (
                ("llm_timeout", 120, 1, 180),
                ("data_retention_days", 60, 7, 365),
                ("dashboard_dynamic_days", 60, 0, 365),
            ),
        )

        sequence_body = self.runtime.fields._page_payload_section(sections, "sequence")
        for key, default in _PAGE_BASIC_SEQUENCE_DEFAULTS.items():
            if key in sequence_body:
                basic[key] = self.validation._page_sequence_value(
                    sequence_body.get(key), default, f"全局{key}"
                )

    def _page_apply_briefing_section(self, sections: dict) -> None:
        briefing_body = self.runtime.fields._page_payload_section(sections, "briefing")
        extra = self.config.setdefault("extra_shares", {})
        self.fields._page_apply_bool_fields(
            extra,
            briefing_body,
            ("enable_60s_news", "enable_ai_news", "sync_briefing_to_qzone"),
        )
        self.schedule_apply._page_apply_schedule_fields(
            extra,
            briefing_body,
            BRIEFING_SCHEDULE,
        )
        if "briefing_cron_random_delay" in briefing_body:
            extra["briefing_cron_random_delay"] = self.validation._page_int_value(
                briefing_body.get("briefing_cron_random_delay"),
                0,
                min_value=0,
                max_value=60,
            )

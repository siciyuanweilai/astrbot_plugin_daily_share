from __future__ import annotations

from ...constants import TYPE_CN_MAP
from ..common import (
    _PAGE_BASIC_SEQUENCE_DEFAULTS,
    _PAGE_BRIEFING_SCHEDULE_MODE_OPTIONS,
    _PAGE_TRIGGER_MODE_OPTIONS,
)


class DashboardApplyBasicMixin:
    def _page_apply_target_section(self, sections: dict) -> None:
        target_body = self._page_payload_section(sections, "target")
        receiver = self.config.setdefault("receiver", {})
        extra = self.config.setdefault("extra_shares", {})
        if "groups" in target_body:
            receiver["groups"] = self._normalize_page_target_list(target_body.get("groups", []))
        if "users" in target_body:
            receiver["users"] = self._normalize_page_target_list(target_body.get("users", []))
        if "briefing_groups" in target_body:
            extra["briefing_groups"] = self._normalize_page_target_list(
                target_body.get("briefing_groups", []),
                briefing=True,
            )
        if "briefing_users" in target_body:
            extra["briefing_users"] = self._normalize_page_target_list(
                target_body.get("briefing_users", []),
                briefing=True,
            )
        if "contact_aliases" in target_body:
            aliases = self._page_contact_aliases_value(target_body.get("contact_aliases"))
            self.config["contact_aliases"] = aliases
            self.contact_aliases = aliases

    def _page_apply_basic_section(self, sections: dict) -> None:
        basic_body = self._page_payload_section(sections, "basic")
        basic = self.config.setdefault("basic_conf", {})
        self._page_apply_schedule_fields(
            basic,
            basic_body,
            mode_key="trigger_mode",
            mode_default="llm_smart",
            mode_label="全局触发模式",
            mode_options=_PAGE_TRIGGER_MODE_OPTIONS,
            fixed_key="fixed_times",
            fixed_default=["08:00", "20:00"],
            fixed_label="全局固定时间",
            random_key="random_periods",
            random_default=["08:00-10:00", "19:00-21:00"],
            random_label="全局随机时段",
            cron_key="share_cron",
            cron_default="0 8,20 * * *",
            cron_label="全局高级定时表达式",
            smart_max_key="smart_schedule_max_count",
            smart_max_default=2,
            smart_quiet_key="smart_schedule_quiet_hours",
            smart_quiet_default=["23:30-07:30"],
            smart_quiet_label="全局智能定时勿扰时间",
            smart_prompt_key="smart_schedule_prompt",
        )
        if "cron_random_delay" in basic_body:
            basic["cron_random_delay"] = self._page_int_value(
                basic_body.get("cron_random_delay"), 0, min_value=0, max_value=60
            )
        if "share_type" in basic_body:
            share_type = self._page_share_type(basic_body.get("share_type"))
            basic["share_type"] = TYPE_CN_MAP[share_type.value] if share_type else "自动"
        self._page_apply_int_fields(
            basic,
            basic_body,
            (
                ("data_retention_days", 60, 7, 365),
                ("dashboard_dynamic_days", 60, 0, 365),
            ),
        )

        sequence_body = self._page_payload_section(sections, "sequence")
        for key, default in _PAGE_BASIC_SEQUENCE_DEFAULTS.items():
            if key in sequence_body:
                basic[key] = self._page_sequence_value(sequence_body.get(key), default, f"全局{key}")

    def _page_apply_briefing_section(self, sections: dict) -> None:
        briefing_body = self._page_payload_section(sections, "briefing")
        extra = self.config.setdefault("extra_shares", {})
        self._page_apply_bool_fields(
            extra,
            briefing_body,
            ("enable_60s_news", "enable_ai_news", "sync_briefing_to_qzone"),
        )
        self._page_apply_schedule_fields(
            extra,
            briefing_body,
            mode_key="briefing_schedule_mode",
            mode_default="llm_smart",
            mode_label="早报触发模式",
            mode_options=_PAGE_BRIEFING_SCHEDULE_MODE_OPTIONS,
            fixed_key="briefing_fixed_times",
            fixed_default=["08:00"],
            fixed_label="早报固定时间",
            random_key="briefing_random_periods",
            random_default=["08:00-09:00"],
            random_label="早报随机时段",
            cron_key="cron_briefing",
            cron_default="0 8 * * *",
            cron_label="早报高级定时表达式",
            smart_max_key="briefing_smart_schedule_max_count",
            smart_max_default=1,
            smart_quiet_key="briefing_smart_schedule_quiet_hours",
            smart_quiet_default=["23:30-07:30"],
            smart_quiet_label="早报智能定时勿扰时间",
            smart_prompt_key="briefing_smart_schedule_prompt",
        )
        if "briefing_cron_random_delay" in briefing_body:
            extra["briefing_cron_random_delay"] = self._page_int_value(
                briefing_body.get("briefing_cron_random_delay"), 0, min_value=0, max_value=60
            )

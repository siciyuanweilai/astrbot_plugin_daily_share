from __future__ import annotations

from ...constants import TYPE_CN_MAP
from ..common import _PAGE_QZONE_SEQUENCE_DEFAULTS, _PAGE_TRIGGER_MODE_OPTIONS


class DashboardApplyQzoneMixin:
    def _page_apply_qzone_auto_interaction_fields(
        self,
        target: dict,
        source: dict,
        *,
        kind: str,
        interval_default: int,
        cron_default: str,
        label: str,
    ) -> None:
        prefix = f"qzone_auto_{kind}"
        interval_key = f"{prefix}_interval_minutes"
        if interval_key in source:
            target[interval_key] = self._page_int_value(
                source.get(interval_key),
                interval_default,
                min_value=0,
                max_value=1440,
            )
        if f"{prefix}_cron" in source:
            target[f"{prefix}_cron"] = self._page_cron_value(
                source.get(f"{prefix}_cron"),
                cron_default,
                label,
            )
        if f"{prefix}_limit" in source:
            target[f"{prefix}_limit"] = self._page_int_value(
                source.get(f"{prefix}_limit"),
                3,
                min_value=1,
                max_value=10,
            )
        if f"{prefix}_prompt" in source:
            target[f"{prefix}_prompt"] = self._page_clean_text(
                source.get(f"{prefix}_prompt"),
                max_len=500,
            )

    def _page_apply_qzone_section(self, sections: dict) -> None:
        qzone_body = self._page_payload_section(sections, "qzone")
        qzone = self.config.setdefault("qzone_conf", {})
        self._page_apply_bool_fields(
            qzone,
            qzone_body,
            (
                "enable_qzone",
                "qzone_enable_image",
                "qzone_enable_video",
                "qzone_attach_hot_news_image",
                "qzone_enable_auto_interaction",
                "qzone_enable_auto_like",
                "qzone_enable_auto_comment",
                "qzone_enable_auto_comment_image_vision",
                "qzone_enable_auto_reply",
            ),
        )
        if "qzone_api_timeout_seconds" in qzone_body:
            self._page_apply_int_fields(
                qzone,
                qzone_body,
                (("qzone_api_timeout_seconds", 120, 10, 300),),
            )
        self._page_apply_schedule_fields(
            qzone,
            qzone_body,
            mode_key="qzone_trigger_mode",
            mode_default="llm_smart",
            mode_label="空间触发模式",
            mode_options=_PAGE_TRIGGER_MODE_OPTIONS,
            fixed_key="qzone_fixed_times",
            fixed_default=["20:00"],
            fixed_label="空间固定时间",
            random_key="qzone_random_periods",
            random_default=["19:00-21:00"],
            random_label="空间随机时段",
            cron_key="qzone_cron",
            cron_default="0 20 * * *",
            cron_label="空间高级定时表达式",
            smart_max_key="qzone_smart_schedule_max_count",
            smart_max_default=1,
            smart_quiet_key="qzone_smart_schedule_quiet_hours",
            smart_quiet_default=["23:30-07:30"],
            smart_quiet_label="空间智能定时勿扰时间",
            smart_prompt_key="qzone_smart_schedule_prompt",
        )
        if "qzone_share_type" in qzone_body:
            share_type = self._page_share_type(qzone_body.get("qzone_share_type"))
            qzone["qzone_share_type"] = TYPE_CN_MAP[share_type.value] if share_type else "自动"
        if "qzone_image_enabled_types" in qzone_body:
            qzone["qzone_image_enabled_types"] = self._page_type_list_value(
                qzone_body.get("qzone_image_enabled_types"), "空间配图类型"
            )
        if "qzone_video_enabled_types" in qzone_body:
            qzone["qzone_video_enabled_types"] = self._page_type_list_value(
                qzone_body.get("qzone_video_enabled_types"), "空间视频类型"
            )
        self._page_apply_qzone_auto_interaction_fields(
            qzone,
            qzone_body,
            kind="interaction",
            interval_default=45,
            cron_default="0 */2 * * *",
            label="空间自动互动",
        )
        self._page_apply_qzone_auto_interaction_fields(
            qzone,
            qzone_body,
            kind="like",
            interval_default=45,
            cron_default="0 */2 * * *",
            label="空间自动点赞",
        )
        self._page_apply_qzone_auto_interaction_fields(
            qzone,
            qzone_body,
            kind="comment",
            interval_default=60,
            cron_default="0 */2 * * *",
            label="空间自动评论",
        )
        self._page_apply_qzone_auto_interaction_fields(
            qzone,
            qzone_body,
            kind="reply",
            interval_default=30,
            cron_default="30 */2 * * *",
            label="空间自动回评",
        )

        qzone_sequence_body = self._page_payload_section(sections, "qzone_sequence")
        for key, default in _PAGE_QZONE_SEQUENCE_DEFAULTS.items():
            if key in qzone_sequence_body:
                qzone[key] = self._page_sequence_value(qzone_sequence_body.get(key), default, f"空间{key}")

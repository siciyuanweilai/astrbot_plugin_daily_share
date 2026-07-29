from __future__ import annotations

from ..panelcomponent import PanelComponent

from ...constants import TYPE_CN_MAP
from ...schedule import QZONE_SCHEDULE
from ..common import _PAGE_QZONE_SEQUENCE_DEFAULTS


class DashboardApplyQzoneService(PanelComponent):
    def _page_apply_qzone_auto_fields(
        self,
        target: dict,
        source: dict,
        *,
        prefix: str,
        cron_default: str = "",
        cron_label: str = "",
    ) -> None:
        if f"{prefix}_cron" in source:
            target[f"{prefix}_cron"] = self.validation._page_cron_value(
                source.get(f"{prefix}_cron"),
                cron_default,
                cron_label,
            )
        if f"{prefix}_limit" in source:
            target[f"{prefix}_limit"] = self.validation._page_int_value(
                source.get(f"{prefix}_limit"),
                3,
                min_value=1,
                max_value=10,
            )
        if f"{prefix}_prompt" in source:
            target[f"{prefix}_prompt"] = self.validation._page_clean_text(
                source.get(f"{prefix}_prompt"),
                max_len=500,
            )

    def _page_apply_qzone_section(self, sections: dict) -> None:
        qzone_body = self.runtime.fields._page_payload_section(sections, "qzone")
        qzone = self.config.setdefault("qzone_conf", {})
        self.fields._page_apply_bool_fields(
            qzone,
            qzone_body,
            (
                "enable_qzone",
                "qzone_enable_image",
                "qzone_attach_hot_news_image",
                "qzone_enable_auto_interaction",
                "qzone_enable_auto_like",
                "qzone_enable_auto_comment",
                "qzone_enable_auto_comment_image_vision",
                "qzone_enable_auto_reply",
            ),
        )
        if "qzone_api_timeout_seconds" in qzone_body:
            self.fields._page_apply_int_fields(
                qzone,
                qzone_body,
                (("qzone_api_timeout_seconds", 120, 10, 300),),
            )
        self.schedule_apply._page_apply_schedule_fields(
            qzone,
            qzone_body,
            QZONE_SCHEDULE,
        )
        if "qzone_cron_random_delay" in qzone_body:
            qzone["qzone_cron_random_delay"] = self.validation._page_int_value(
                qzone_body.get("qzone_cron_random_delay"),
                0,
                min_value=0,
                max_value=60,
            )
        if "qzone_share_type" in qzone_body:
            share_type = self.validation._page_share_type(
                qzone_body.get("qzone_share_type")
            )
            qzone["qzone_share_type"] = (
                TYPE_CN_MAP[share_type.value] if share_type else "自动"
            )
        if "qzone_share_output_format" in qzone_body:
            qzone["qzone_share_output_format"] = self.validation._page_clean_text(
                qzone_body.get("qzone_share_output_format"),
                max_len=1200,
            )
        if "qzone_image_enabled_types" in qzone_body:
            qzone["qzone_image_enabled_types"] = self.validation._page_type_list_value(
                qzone_body.get("qzone_image_enabled_types"), "空间配图类型"
            )
        self.qzone_apply._page_apply_qzone_auto_fields(
            qzone,
            qzone_body,
            prefix="qzone_auto_interaction",
            cron_default="0 */2 * * *",
            cron_label="空间自动互动",
        )
        self.fields._page_apply_int_fields(
            qzone,
            qzone_body,
            (("qzone_auto_interaction_active_hours", 24, 0, 168),),
        )
        self.qzone_apply._page_apply_qzone_auto_fields(
            qzone,
            qzone_body,
            prefix="qzone_auto_like",
        )
        self.qzone_apply._page_apply_qzone_auto_fields(
            qzone,
            qzone_body,
            prefix="qzone_auto_comment",
        )
        self.qzone_apply._page_apply_qzone_auto_fields(
            qzone,
            qzone_body,
            prefix="qzone_auto_reply",
        )

        qzone_sequence_body = self.runtime.fields._page_payload_section(
            sections, "qzone_sequence"
        )
        for key, default in _PAGE_QZONE_SEQUENCE_DEFAULTS.items():
            if key in qzone_sequence_body:
                qzone[key] = self.validation._page_sequence_value(
                    qzone_sequence_body.get(key), default, f"空间{key}"
                )

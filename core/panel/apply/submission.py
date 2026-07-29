from __future__ import annotations

from ..panelcomponent import PanelComponent


class DashboardApplyPayloadService(PanelComponent):
    def _apply_page_config_payload(self, body: dict) -> None:
        sections = (
            body.get("sections") if isinstance(body.get("sections"), dict) else body
        )
        if "enabled" in body:
            self.config["enable_auto_share"] = bool(body.get("enabled"))

        runtime = self.runtime
        runtime.general_apply._page_apply_target_section(sections)
        runtime.general_apply._page_apply_basic_section(sections)
        runtime.general_apply._page_apply_briefing_section(sections)
        runtime.qzone_apply._page_apply_qzone_section(sections)
        runtime.sections._page_apply_content_section(sections)
        runtime.sections._page_apply_media_section(sections)
        runtime.sections._page_apply_context_section(sections)
        runtime.sections._page_apply_news_section(sections)
        runtime.fields._page_apply_schema_extra(body)

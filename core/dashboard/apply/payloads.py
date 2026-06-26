from __future__ import annotations


class DashboardApplyPayloadMixin:
    def _apply_page_config_payload(self, body: dict) -> None:
        sections = body.get("sections") if isinstance(body.get("sections"), dict) else body
        if "enabled" in body:
            self.config["enable_auto_share"] = bool(body.get("enabled"))

        self._page_apply_target_section(sections)
        self._page_apply_basic_section(sections)
        self._page_apply_briefing_section(sections)
        self._page_apply_qzone_section(sections)
        self._page_apply_content_section(sections)
        self._page_apply_media_section(sections)
        self._page_apply_context_section(sections)
        self._page_apply_news_section(sections)
        self._page_apply_llm_section(sections)
        self._page_apply_schema_extra(body)

from __future__ import annotations


class DashboardApplyFieldMixin:
    @staticmethod
    def _page_payload_section(sections: dict, name: str) -> dict:
        section = sections.get(name) if isinstance(sections, dict) else {}
        return section if isinstance(section, dict) else {}

    @staticmethod
    def _page_apply_bool_fields(target: dict, source: dict, keys: tuple) -> None:
        for key in keys:
            if key in source:
                target[key] = bool(source.get(key))

    def _page_apply_int_fields(self, target: dict, source: dict, specs: tuple) -> None:
        for key, default, min_value, max_value in specs:
            if key in source:
                target[key] = self._page_int_value(
                    source.get(key),
                    default,
                    min_value=min_value,
                    max_value=max_value,
                )

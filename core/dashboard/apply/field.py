from __future__ import annotations

from typing import Any


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

    def _page_schema_extra_value(self, value: Any, item: dict, label: str):
        item_type = str(item.get("type") or "string").lower()
        default = self._page_schema_default(item)
        options = item.get("options") if isinstance(item.get("options"), list) else None

        if item_type == "bool":
            return bool(value)
        if item_type == "int":
            slider = item.get("slider") if isinstance(item.get("slider"), dict) else {}
            return self._page_int_value(
                value,
                int(default or 0),
                min_value=int(slider.get("min", -2147483648)),
                max_value=int(slider.get("max", 2147483647)),
            )
        if item_type in {"float", "number"}:
            if value in (None, ""):
                value = default or 0
            try:
                number = float(value)
            except Exception as exc:
                raise RuntimeError(f"{label} 必须是数字") from exc
            slider = item.get("slider") if isinstance(item.get("slider"), dict) else {}
            if "min" in slider:
                number = max(float(slider["min"]), number)
            if "max" in slider:
                number = min(float(slider["max"]), number)
            return number
        if item_type == "list":
            child = item.get("items") if isinstance(item.get("items"), dict) else {}
            child_options = child.get("options") if isinstance(child.get("options"), list) else None
            values = self._page_list_value(value, max_items=300, item_max_len=1000, split_commas=True)
            if child_options:
                allowed = {str(option) for option in child_options}
                invalid = [entry for entry in values if entry not in allowed]
                if invalid:
                    raise RuntimeError(f"{label} 包含不支持的选项: {', '.join(invalid)}")
            return values

        text_value = self._page_clean_text(value, max_len=5000)
        if options and text_value not in {str(option) for option in options}:
            raise RuntimeError(f"{label} 不支持: {text_value}")
        return text_value

    def _page_apply_schema_extra(self, body: dict) -> None:
        extra = body.get("schema_extra")
        if not isinstance(extra, dict):
            return

        raw_schema = self._page_config_schema()
        root_extra = extra.get("root") if isinstance(extra.get("root"), dict) else {}
        for key, value in root_extra.items():
            item = raw_schema.get(key)
            if not isinstance(item, dict) or item.get("type") == "object":
                continue
            if key == "contact_aliases":
                aliases = self._page_contact_aliases_value(value)
                self.config[key] = aliases
                self.contact_aliases = aliases
                continue
            self.config[key] = self._page_schema_extra_value(
                value,
                item,
                str(item.get("description") or item.get("title") or key),
            )

        section_extra = extra.get("sections") if isinstance(extra.get("sections"), dict) else {}
        for section_key, values in section_extra.items():
            section_schema = raw_schema.get(section_key)
            if not isinstance(section_schema, dict) or section_schema.get("type") != "object":
                continue
            if not isinstance(values, dict):
                continue
            section_items = section_schema.get("items") if isinstance(section_schema.get("items"), dict) else {}
            target = self.config.setdefault(section_key, {})
            if not isinstance(target, dict):
                target = {}
                self.config[section_key] = target
            for field_key, value in values.items():
                item = section_items.get(field_key)
                if not isinstance(item, dict):
                    continue
                target[field_key] = self._page_schema_extra_value(
                    value,
                    item,
                    str(item.get("description") or item.get("title") or field_key),
                )

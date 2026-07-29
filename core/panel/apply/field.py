from __future__ import annotations

from ..panelcomponent import PanelComponent

from typing import Any


class DashboardApplyFieldService(PanelComponent):
    def _page_payload_section(self, sections: dict, name: str) -> dict:
        """读取设置页分区，保持组件调用的实例方法契约。"""
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
                target[key] = self.validation._page_int_value(
                    source.get(key),
                    default,
                    min_value=min_value,
                    max_value=max_value,
                )

    def _page_schema_extra_value(self, value: Any, item: dict, label: str):
        item_type = str(item.get("type") or "string").lower()
        default = self.meta._page_schema_default(item)
        raw_options = item.get("options")
        options = raw_options if isinstance(raw_options, list) else None

        if item_type == "bool":
            return bool(value)
        if item_type == "int":
            raw_slider = item.get("slider")
            slider = raw_slider if isinstance(raw_slider, dict) else {}
            return self.validation._page_int_value(
                value,
                int(default or 0),
                min_value=int(slider.get("min", -2147483648)),
                max_value=int(slider.get("max", 2147483647)),
            )
        if item_type in {"float", "number"}:
            return self.fields._page_schema_number_value(value, default, item, label)
        if item_type == "list":
            return self.fields._page_schema_list_value(value, item, label)

        text_value = self.validation._page_clean_text(value, max_len=5000)
        if options and text_value not in {str(option) for option in options}:
            raise RuntimeError(f"{label} 不支持: {text_value}")
        return text_value

    @staticmethod
    def _page_schema_number_value(value, default, item: dict, label: str) -> float:
        raw_value = default or 0 if value in (None, "") else value
        try:
            number = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"{label} 必须是数字") from exc
        raw_slider = item.get("slider")
        slider = raw_slider if isinstance(raw_slider, dict) else {}
        if "min" in slider:
            number = max(float(slider["min"]), number)
        if "max" in slider:
            number = min(float(slider["max"]), number)
        return number

    def _page_schema_list_value(self, value, item: dict, label: str) -> list:
        raw_child = item.get("items")
        child = raw_child if isinstance(raw_child, dict) else {}
        raw_child_options = child.get("options")
        child_options = raw_child_options if isinstance(raw_child_options, list) else []
        values = self.validation._page_list_value(
            value, max_items=300, item_max_len=1000, split_commas=True
        )
        allowed = {str(option) for option in child_options}
        invalid = [entry for entry in values if allowed and entry not in allowed]
        if invalid:
            raise RuntimeError(f"{label} 包含不支持的选项: {', '.join(invalid)}")
        return values

    def _page_apply_schema_extra(self, body: dict) -> None:
        extra = body.get("schema_extra")
        if not isinstance(extra, dict):
            return

        raw_schema = self.meta._page_config_schema()
        raw_root_extra = extra.get("root")
        root_extra = raw_root_extra if isinstance(raw_root_extra, dict) else {}
        self.fields._page_apply_schema_root_extra(raw_schema, root_extra)

        raw_section_extra = extra.get("sections")
        section_extra = raw_section_extra if isinstance(raw_section_extra, dict) else {}
        for section_key, values in section_extra.items():
            self.fields._page_apply_schema_section_extra(
                raw_schema, section_key, values
            )

    def _page_apply_schema_root_extra(self, raw_schema: dict, root_extra: dict) -> None:
        for key, value in root_extra.items():
            item = raw_schema.get(key)
            if not isinstance(item, dict) or item.get("type") == "object":
                continue
            if key == "contact_aliases":
                aliases = self.validation._page_contact_aliases_value(value)
                self.config[key] = aliases
                self.contact_aliases = aliases
                continue
            self.config[key] = self.fields._page_schema_extra_value(
                value,
                item,
                str(item.get("description") or item.get("title") or key),
            )

    def _page_apply_schema_section_extra(
        self, raw_schema: dict, section_key: str, values: Any
    ) -> None:
        section_schema = raw_schema.get(section_key)
        if (
            not isinstance(section_schema, dict)
            or section_schema.get("type") != "object"
        ):
            return
        if not isinstance(values, dict):
            return
        section_items = section_schema.get("items")
        section_items = section_items if isinstance(section_items, dict) else {}
        target = self.config.setdefault(section_key, {})
        if not isinstance(target, dict):
            target = {}
            self.config[section_key] = target
        for field_key, value in values.items():
            item = section_items.get(field_key)
            if not isinstance(item, dict):
                continue
            label = str(item.get("description") or item.get("title") or field_key)
            target[field_key] = self.fields._page_schema_extra_value(value, item, label)

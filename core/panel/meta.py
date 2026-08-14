import asyncio
import copy
import json

from astrbot.api import logger

from ..config import NEWS_SOURCE_MAP, ShareType
from ..constants import TYPE_CN_MAP
from ..platform import (
    get_platform_bindings,
)
from .common import _PAGE_CONF_SCHEMA_PATH
from .panelcomponent import PanelComponent


class DashboardConfigMetaService(PanelComponent):
    """仪表盘配置选项和结构元信息。"""

    @staticmethod
    def _read_page_config_schema_sync() -> dict:
        return json.loads(_PAGE_CONF_SCHEMA_PATH.read_text(encoding="utf-8"))

    async def load_config_schema(self) -> dict:
        if self._page_config_schema_raw_cache is not None:
            return self._page_config_schema_raw_cache
        try:
            raw_schema = await asyncio.to_thread(
                self.meta._read_page_config_schema_sync
            )
        except Exception as exc:
            logger.warning(f"[日常分享] 读取仪表盘配置结构失败: {exc}")
            raw_schema = {}
        self._page_config_schema_raw_cache = raw_schema
        return raw_schema

    def _page_config_schema(self) -> dict:
        return self._page_config_schema_raw_cache or {}

    def _page_provider_options(self) -> list:
        options = [{"value": "", "label": "跟随会话默认"}]
        seen = {""}

        def add_option(value, label=None) -> None:
            value_s = str(value or "").strip()
            if not value_s or value_s in seen:
                return
            label_s = str(label or value_s).strip() or value_s
            options.append({"value": value_s, "label": label_s})
            seen.add(value_s)

        try:
            for provider in self.context.get_all_providers():
                meta = provider.meta()
                provider_id = str(meta.id or "").strip()
                model = str(meta.model or "").strip()
                add_option(provider_id, f"{provider_id} · {model}" if model else None)
        except Exception as exc:
            logger.debug(f"[日常分享] 读取模型服务提供商实例失败: {exc}")

        return options

    def _page_adapter_options(self) -> list:
        options: list[dict[str, object]] = [{"value": "", "label": "自动选择唯一实例"}]
        try:
            for binding in get_platform_bindings(self.context):
                adapter_id = binding.platform_id
                route_id = binding.route_id
                platform_type = binding.platform_type
                if platform_type == "webchat":
                    label = f"网页聊天 · {adapter_id}"
                else:
                    label = (
                        f"{adapter_id} · {platform_type}"
                        if platform_type
                        else adapter_id
                    )
                if binding.conflicted:
                    label += "（实例 ID 冲突）"
                options.append(
                    {
                        "value": route_id,
                        "label": label,
                        "platform_type": platform_type,
                        "supports_proactive": binding.supports_proactive,
                        "supports_group": binding.supports_group,
                        "conflicted": binding.conflicted,
                    }
                )
        except Exception as exc:
            logger.debug(f"[日常分享] 读取机器人实例配置失败: {exc}")
        return options

    def _page_config_options(self) -> dict:
        return {
            "trigger_modes": [
                {"value": "fixed_time", "label": "固定时间"},
                {"value": "random_period", "label": "随机时段"},
                {"value": "llm_smart", "label": "智能定时"},
                {"value": "cron", "label": "高级定时表达式"},
            ],
            "share_types": [
                {"value": "自动", "label": "自动"},
                *[
                    {
                        "value": TYPE_CN_MAP.get(item.value, item.value),
                        "label": TYPE_CN_MAP.get(item.value, item.value),
                    }
                    for item in ShareType
                ],
            ],
            "cron_presets": [
                {"value": key, "label": label}
                for key, label in (
                    ("morning", "早上 8 点"),
                    ("noon", "中午 12 点"),
                    ("afternoon", "下午 3 点"),
                    ("evening", "晚上 7 点"),
                    ("night", "晚上 10 点"),
                    ("twice", "早晚各一次"),
                    ("three_times", "早中晚"),
                )
            ],
            "news_random_modes": [
                {"value": "fixed", "label": "固定新闻源"},
                {"value": "random", "label": "全量随机"},
                {"value": "config", "label": "配置列表随机"},
                {"value": "time_based", "label": "按时段智能选择"},
            ],
            "news_sources": [
                {"value": key, "label": str(value.get("name") or key)}
                for key, value in NEWS_SOURCE_MAP.items()
            ],
            "context_strategies": [
                {"value": "cautious", "label": "谨慎模式"},
                {"value": "active", "label": "主动模式"},
                {"value": "minimal", "label": "最小模式"},
            ],
            "providers": self.meta._page_provider_options(),
            "adapters": self.meta._page_adapter_options(),
        }

    @staticmethod
    def _page_schema_meta_item(item: dict) -> dict:
        if not isinstance(item, dict):
            return {}
        meta = {}
        for key in (
            "title",
            "description",
            "hint",
            "type",
            "options",
            "default",
            "_special",
        ):
            value = item.get(key)
            if value not in (None, ""):
                meta[key] = value
        slider = item.get("slider")
        if isinstance(slider, dict):
            meta["slider"] = {
                key: slider[key] for key in ("min", "max", "step") if key in slider
            }
        child = item.get("items")
        if isinstance(child, dict):
            child_meta = {}
            for key in ("type", "options"):
                value = child.get(key)
                if value not in (None, ""):
                    child_meta[key] = value
            if child_meta:
                meta["items"] = child_meta
        return meta

    @staticmethod
    def _page_schema_default(item: dict):
        if not isinstance(item, dict):
            return None
        if "default" in item:
            return copy.deepcopy(item.get("default"))
        item_type = str(item.get("type") or "string").lower()
        if item_type == "bool":
            return False
        if item_type in {"int", "float", "number"}:
            return 0
        if item_type == "list":
            return []
        if item_type == "object":
            return {}
        return ""

    def _page_schema_config_value(self, source: dict, key: str, item: dict):
        if isinstance(source, dict) and key in source:
            return copy.deepcopy(source.get(key))
        return self.meta._page_schema_default(item)

    def _page_config_schema_values(self) -> dict:
        root_values = {}
        section_values = {}
        for section_key, section_value in self.meta._page_config_schema().items():
            if not isinstance(section_value, dict):
                continue
            section_items = section_value.get("items")
            if section_value.get("type") == "object" and isinstance(
                section_items, dict
            ):
                source = self.config.get(section_key, {})
                source = source if isinstance(source, dict) else {}
                section_values[section_key] = {
                    field_key: self.meta._page_schema_config_value(
                        source, field_key, field_value
                    )
                    for field_key, field_value in section_items.items()
                    if isinstance(field_value, dict)
                }
            else:
                root_values[section_key] = self.meta._page_schema_config_value(
                    self.config,
                    section_key,
                    section_value,
                )
        return {
            "root": root_values,
            "sections": section_values,
        }

    def _page_config_schema_meta(self) -> dict:
        raw_schema = self.meta._page_config_schema()
        if not raw_schema:
            return self._page_config_schema_meta_cache or {}

        root_fields = {}
        sections = {}
        for section_key, section_value in raw_schema.items():
            if not isinstance(section_value, dict):
                continue

            section_items = section_value.get("items")
            if section_value.get("type") == "object" and isinstance(
                section_items, dict
            ):
                section_meta = self.meta._page_schema_meta_item(section_value)
                section_meta["fields"] = {
                    field_key: self.meta._page_schema_meta_item(field_value)
                    for field_key, field_value in section_items.items()
                    if isinstance(field_value, dict)
                }
                sections[section_key] = section_meta
            else:
                root_fields[section_key] = self.meta._page_schema_meta_item(
                    section_value
                )

        adapter_options = self.meta._page_adapter_options()
        for section_meta in sections.values():
            for field_meta in (section_meta.get("fields") or {}).values():
                if field_meta.get("_special") == "select_adapter":
                    field_meta["options"] = copy.deepcopy(adapter_options)

        meta = {
            "root": root_fields,
            "sections": sections,
        }
        self._page_config_schema_meta_cache = meta
        return meta

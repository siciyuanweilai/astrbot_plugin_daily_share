from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from ...config import ShareType, TimePeriod


class ImageVisualFrameService:
    """图像视觉组件共享的显式依赖契约。"""

    if TYPE_CHECKING:
        context: Any
        config: dict
        img_conf: dict
        call_llm: Callable[..., Awaitable[Any]]

        async def _call_llm(
            self, *args: Any, target_umo: str | None = None, **kwargs: Any
        ) -> Any: ...

        def _get_current_period(self) -> TimePeriod: ...

        async def _check_involves_self(
            self,
            content: str,
            share_type: ShareType,
            target_umo: str | None = None,
        ) -> bool: ...

    """视觉构图和穿搭一致性提示。"""

    @staticmethod
    def _has_visual_subject(visuals: dict) -> bool:
        subject = str(visuals.get("subject", "") or "").strip()
        return bool(subject and subject not in {"无", "N/A", "None"})

    def _resolve_visual_mode(self, visuals: dict, contains_character: bool) -> str:
        if contains_character:
            return "person"
        return "object" if self._has_visual_subject(visuals) else "landscape"

    def _enforce_visual_mode(self, visuals: dict, contains_character: bool) -> dict:
        """固定人物、静物或风景模式，避免模型构图覆盖上游决策。"""
        normalized = dict(visuals or {})
        visual_mode = self._resolve_visual_mode(normalized, contains_character)
        normalized["visual_mode"] = visual_mode
        if visual_mode != "person":
            normalized["composition"] = ""
            normalized["frame_logic"] = ""
            normalized["composition_logic"] = ""
        return normalized

    def _resolve_composition(
        self, visuals: dict, involves_self: bool
    ) -> tuple[str, str]:
        visual_mode = self._resolve_visual_mode(visuals, involves_self)
        composition = str(visuals.get("composition", "") or "").strip()
        frame_logic = str(
            visuals.get("frame_logic", "") or visuals.get("composition_logic", "") or ""
        ).strip()
        if visual_mode == "person" and composition:
            return (
                composition,
                frame_logic
                or "画面范围遵循已选择的自然构图；穿搭、动作和环境只呈现入镜内容。",
            )

        if visual_mode == "object":
            return (
                "自然静物构图, 景别由主体关系决定",
                "画面范围根据主体和环境关系自然确定；不要为了补充背景扩大构图。",
            )
        if visual_mode == "landscape":
            return (
                "自然风景构图, 景别由环境氛围决定",
                "画面范围根据环境、光影和天气自然确定；不要加入额外人物。",
            )
        return (
            "自然生活构图, 景别由人物动作和场景重点决定",
            "画面范围根据人物动作、环境和情绪自然确定；穿搭和动作只呈现入镜部分。",
        )

    def _format_outfit_consistency_hint(
        self, visuals: dict, frame_hint: str = ""
    ) -> str:
        scene_type = str(visuals.get("scene_type", "") or "").strip()
        temperature = str(visuals.get("temperature_feel", "") or "").strip()
        weather = str(visuals.get("weather_condition", "") or "").strip()

        details = []
        if scene_type and scene_type != "未知":
            details.append(f"场景：{scene_type}")
        if temperature and temperature != "未知":
            details.append(f"温感：{temperature}")
        if weather and weather != "未知":
            details.append(f"天气：{weather}")

        prefix = f"{'，'.join(details)}，" if details else ""
        base_rule = "穿搭、外观、动作和场景必须符合当前地点、天气、温度和预设构图范围。"
        return f"{prefix}{frame_hint or base_rule}"

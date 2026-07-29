from __future__ import annotations

from typing import Dict

from ...config import ShareType, TimePeriod
from .persona import ImageVisualPersonaService


class ImageVisualPromptService(ImageVisualPersonaService):
    """组装最终图片生成提示词。"""

    async def _assemble_final_prompt(
        self,
        content: str,
        share_type: ShareType,
        involves_self: bool,
        visuals: Dict,
        target_umo: str | None = None,
    ) -> str:
        prompts: list[str] = []
        quality_tags = (
            "8K分辨率, 高质量, 写实, 高分辨率, 细节丰富, 色彩鲜艳, 电影级光影效果"
        )

        if involves_self:
            await self._append_self_visual_prompts(prompts, visuals, target_umo)
        else:
            self._append_subject_visual_prompts(prompts, visuals)

        comp_desc, frame_hint = self._resolve_composition(visuals, involves_self)

        if comp_desc:
            prompts.append(comp_desc)

        self._append_environment_prompts(prompts, visuals)

        if involves_self:
            outfit_consistency = self._format_outfit_consistency_hint(
                visuals, frame_hint
            )
            if outfit_consistency:
                prompts.append(outfit_consistency)

        prompts.append(quality_tags)
        return ", ".join(filter(None, prompts))

    async def _append_self_visual_prompts(
        self, prompts: list[str], visuals: Dict, target_umo: str | None
    ) -> None:
        prompts.append("画面主体是当前角色本人，保持角色外貌身份一致")
        appearance = await self._get_appearance_keywords(target_umo=target_umo)
        prompts.append(
            appearance or await self._get_persona_figure_keywords() or "1个人物, 独奏"
        )
        for value in (visuals.get("outfit"), visuals.get("action")):
            if text := str(value or "").strip():
                prompts.append(text)

    @staticmethod
    def _append_subject_visual_prompts(prompts: list[str], visuals: Dict) -> None:
        subject = visuals.get("subject", "")
        if subject and subject not in {"无", "N/A", "None"}:
            prompts.extend(("无人, 静物", subject))
        else:
            prompts.append("无人, 风景, 景观, 细节丰富")

    def _append_environment_prompts(self, prompts: list[str], visuals: Dict) -> None:
        environment = visuals.get("environment", "")
        prompts.append(f"位于 {environment}" if environment else "简单的背景")
        lighting = visuals.get("lighting", "")
        if lighting:
            prompts.append(lighting)
        elif self._get_current_period() in {TimePeriod.NIGHT, TimePeriod.LATE_NIGHT}:
            prompts.append("夜晚, 城市灯光")
        else:
            prompts.append("白天, 自然光")
        if visuals.get("weather_vibe"):
            prompts.append(visuals["weather_vibe"])

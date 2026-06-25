from __future__ import annotations

from typing import Dict

from ...config import ShareType, TimePeriod


class ImageVisualPromptMixin:
    """组装最终图片生成提示词。"""

    async def _assemble_final_prompt(self, content: str, share_type: ShareType, involves_self: bool, visuals: Dict, target_umo: str = None) -> str:
        prompts = []
        quality_tags = "8K分辨率, 高质量, 写实, 高分辨率, 细节丰富, 色彩鲜艳, 电影级光影效果"

        if involves_self:
            action = str(visuals.get("action", "") or "").strip()
            appearance = await self._get_appearance_keywords(target_umo=target_umo)
            if appearance:
                prompts.append(appearance)
            else:
                prompts.append(await self._get_persona_figure_keywords() or "1个人物, 独奏")

            comp_desc, frame_hint = self._resolve_composition(visuals, involves_self)
            raw_outfit = str(visuals.get("outfit", "") or "").strip()
            if raw_outfit:
                prompts.append(raw_outfit)
            if action:
                prompts.append(action)
        else:
            subject = visuals.get("subject", "")
            is_valid_subject = subject and subject not in ["无", "N/A", "None", ""]
            comp_desc, frame_hint = self._resolve_composition(visuals, involves_self)
            if is_valid_subject:
                prompts.append("无人, 静物")
                prompts.append(subject)
            else:
                prompts.append("无人, 风景, 景观, 细节丰富")

        if comp_desc:
            prompts.append(comp_desc)

        env = visuals.get("environment", "")
        lighting = visuals.get("lighting", "")
        weather_vibe = visuals.get("weather_vibe", "")

        if env:
            prompts.append(f"位于 {env}")
        else:
            prompts.append("简单的背景")

        if lighting:
            prompts.append(lighting)
        else:
            period = self._get_current_period()
            if period in [TimePeriod.NIGHT, TimePeriod.LATE_NIGHT]:
                prompts.append("夜晚, 城市灯光")
            else:
                prompts.append("白天, 自然光")

        if weather_vibe:
            prompts.append(weather_vibe)

        if involves_self:
            outfit_consistency = self._format_outfit_consistency_hint(visuals, frame_hint)
            if outfit_consistency:
                prompts.append(outfit_consistency)

        prompts.append(quality_tags)
        return ", ".join(filter(None, prompts))

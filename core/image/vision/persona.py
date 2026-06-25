from __future__ import annotations

from astrbot.api import logger

from ...identity import build_persona_figure_prompt


class ImageVisualPersonaMixin:
    """提取图片生成所需的人设外观信息。"""

    async def _get_appearance_keywords(self, target_umo: str = None) -> str:
        """获取人设外貌。"""
        conf_p = self.img_conf.get("appearance_prompt", "").strip()
        if conf_p:
            return conf_p
        try:
            p_obj = await self.context.persona_manager.get_default_persona_v3()
            p_text = p_obj.get("prompt", "") if p_obj else ""
            if not p_text:
                return ""
            prompt = f"""请从以下人设描述中提取外貌特征，并转换为中文的图片生成描述片段。
人设描述：
{p_text}
要求：
1. 【重要】必须包含人种/国籍描述
2. 提取外貌细节（发型、发色、眼睛、肤色、体型）
3. 转换为简短的中文描述片段，用逗号分隔
4. 不要包含性格、职业等非外貌信息
5. 直接输出中文描述片段，不要解释
请输出："""
            res = await self._call_llm(prompt, timeout=20, target_umo=target_umo)
            return res.strip() if res else ""
        except Exception as e:
            logger.debug(f"[图像服务] 提取人设外貌失败: {e}")
            return ""

    async def _get_persona_figure_keywords(self) -> str:
        try:
            p_obj = await self.context.persona_manager.get_default_persona_v3()
            p_text = p_obj.get("prompt", "") if p_obj else ""
            return build_persona_figure_prompt(p_text)
        except Exception as e:
            logger.debug(f"[图像服务] 提取人设身份失败: {e}")
            return ""

from __future__ import annotations

import json
from datetime import datetime
from typing import Dict

from astrbot.api import logger

from ...config import ShareType, TimePeriod
from .json import _extract_json_object


def _visual_time_hint(period: TimePeriod, hour: int) -> str:
    if period == TimePeriod.DAWN:
        if hour < 4:
            return "凌晨深夜的寂静，漆黑的夜空，漆黑的夜色，路灯或城市灯光"
        return "黎明前的微光，天空是非常深的暗蓝色，微弱的冷光，清冷寂静，朦胧感"
    if period == TimePeriod.MORNING:
        return "早晨的日出晨光, 柔和的朝阳, 清晨柔和的漫射光，丁达尔效应, 梦幻光影"
    if period == TimePeriod.FORENOON:
        return "上午的明亮日光，通透，晴朗的天空, 充满活力的光线"
    if period == TimePeriod.NOON:
        return "中午明亮而柔和的日光，清爽通透，带一点午休前后的轻盈生活感"
    if period == TimePeriod.AFTERNOON:
        return "下午的充足阳光，光影对比清晰，慵懒或明亮的氛围, 清晰的照明"
    if period == TimePeriod.EVENING:
        return "傍晚的暖色调，温暖的金色夕阳, 晚霞或暮色，柔和的长阴影，逆光轮廓"
    if period == TimePeriod.NIGHT:
        return "夜晚的漆黑天空, 深沉的夜景，城市霓虹灯光, 室内温馨的人造暖光"
    return "深夜的幽暗氛围，漆黑的环境，城市夜景，昏暗的室内人造光，宁静的氛围"


def _visual_outfit_hint(is_night: bool) -> str:
    if is_night:
        return "当前是休息时间，优先提取睡衣、家居服等可见居家穿搭；只有文案或日程明确正在外出时，才使用完整外出穿搭。"
    return "当前是活动时间，请结合生活日程里的地点、天气、温度、今日穿搭提取合理穿搭。"


def _visual_outfit_rules() -> str:
    return """
【穿搭合理性规则】
1. 必须优先参考【生活日程】里的天气、温度、今日穿搭、当前活动、完整时间轴；缺失时再根据【分享文案】和当前时段推断。
   - 【今日穿搭】只属于主角/你本人，只能用于画面主角的 outfit。
   - 日程、记忆或关系档案里的其他人不得继承主角的今日穿搭；如果画面必须出现其他人，对方外观只按文案或关系原文明确写出的内容处理，缺失时保持概括，不补衣着细节。
2. 判断场景类型：
   - 家里：可穿家居服、睡衣、拖鞋或赤脚；炎热时可以不穿外套；寒冷时可以加针织开衫、毛绒拖鞋、毯子。
   - 室内公共场所：可脱外套或把外套搭在椅背，但一般保留日常鞋子；只有酒店房间、瑜伽馆、榻榻米、换鞋区等场景才允许拖鞋或赤脚。
   - 室外：必须是合理外出状态；寒冷要有外套、围巾、长裤或保暖鞋子；炎热要轻薄衣物、凉鞋或透气鞋；雨雪天气要体现伞、防水鞋、湿润地面等细节。
3. 脚部状态不要无条件写进 outfit；要先理解文案里的动作、地点、身体姿态、地面接触方式和生活习惯，再决定是否需要呈现赤脚、拖鞋、居家鞋、居家袜或外出鞋：
   - 如果文案强调脚感、光脚、刚洗澡、泡脚、蜷在沙发/床上、瑜伽垫/榻榻米、海边沙滩等语境，赤脚可能更自然。
   - 如果文案只是描述在家中木地板、客厅、厨房、玄关等位置站立、走动或踩着地面，要判断日常生活里是否更自然是拖鞋、居家鞋或居家袜，不要为了画面氛围强行赤脚。
   - 只有构图、动作或文案明确会看见脚部时，才把脚部状态写进 outfit；无法确定是否可见时，放在 outfit_logic 里说明，不作为可见画面词。
4. 不要让人物在室外赤脚，除非文案明确说明。
5. 不要让人物在家里穿厚重大衣和外出鞋，除非文案明确说明刚回家或准备出门。
6. 如果生活日程给了“今日穿搭”，可以在此基础上按当前地点和温度微调：例如在家可脱外套、换拖鞋；到室内公共场所可把外套搭在椅背；到室外则保持完整外出穿搭。
"""


def _visual_location_logic(priority_text: bool, hour: int) -> str:
    if priority_text:
        return f"""
1. **第一优先级（文案主导）**：首先检查【分享文案】。如果文案中明确提及了当前画面地点，优先绘制文案描述的地点。
2. **第二优先级（日程补缺）**：只有当【分享文案】**完全未提及**地点时，才提取日程中 **{hour}:00 正在进行** 的状态来设定背景场景。
"""
    return f"""
1. **第一优先级（日程主导）**：首先检查【生活日程】。如果 **{hour}:00** 有明确的活动地点，优先绘制日程地点；文案中的地点只在与当前状态一致时采用。
2. **第二优先级（文案补缺）**：只有当【生活日程】为空或未明确指定地点时，才参考【分享文案】中的地点描述。
"""


class ImageVisualExtractMixin:
    """用 LLM 提取图像视觉要素。"""

    def _format_visual_extraction_frame(self, share_type: ShareType = None, involves_self: bool = False) -> str:
        if not involves_self:
            return (
                "请根据文案主体、地点、情绪和画面重点自然选择构图，不要按分享类型固定镜头；"
                "可以选择静物特写、环境中景、远景或全景。若出现人物，也只作为环境尺度参考，不补充完整衣着细节。"
            )
        return (
            "请根据文案主体、情绪、动作、地点和画面重点自然选择构图，不要按分享类型固定镜头；"
            "可以选择脸部近景、半身、中景、远景、全景、手部或物品特写。"
            "composition 写最终构图，frame_logic 说明为什么这样取景以及哪些内容在画面范围内可见。"
            "outfit 和 action 只写入该构图中能直接看见的内容，不把生活状态里未入镜的内容写进画面词。"
        )

    def _visual_extraction_system_prompt(
        self,
        *,
        hour: int,
        time_hint: str,
        outfit_hint: str,
        logic_prompt: str,
        frame_prompt: str,
    ) -> str:
        return f"""你是一个专业的 AI 绘画视觉导演。
任务：根据用户的【分享文案】和【生活日程】，提取画面要素。

【预设构图】
{frame_prompt}

【提取逻辑】
1. **分析主体 (Subject)**：首先判断文案是否在描述或推荐一个**具体物品**（如美食、书籍、电子产品、电影海报）。
   - 如果是：该物品就是【subject】。
   - 如果否（文案是纯风景描绘）：【subject】填“无”。
2. **分析背景 (Environment)**：
{logic_prompt}
3. **时间边界**：不要提取 {hour}:00 之后尚未发生的未来日程作为背景；若当前时段没有明确地点，使用当前状态、室内外线索或“未知”。
4. **场景与穿搭判断**：先判断当前画面属于“家里 / 室内公共场所 / 室外 / 未知”，再根据天气和温度决定外套、脚部状态、层次和材质。

{_visual_outfit_rules()}

【提取要求】
1. **主体 (subject)**：【最重要】画面的核心物体描述（例如：精致的荷花酥，一杯牛奶或者一本封皮复古的书）。如果是纯风景或画人，此项填“无”。
2. **环境 (environment)**：根据逻辑确定的具体地点。
3. **光影 (lighting)**：参考时间段[{time_hint}]。如果是室内，强调人造光；如果是室外，强调自然天气氛围。
4. **场景 (scene_type)**：填“家里 / 室内公共场所 / 室外 / 未知”之一。
5. **温感 (temperature_feel)**：根据天气温度和文案判断，填“寒冷 / 微凉 / 舒适 / 温暖 / 炎热 / 未知”之一。
6. **天气 (weather_condition)**：提取晴、雨、雪、阴、闷热、潮湿等真实天气；不明确则填“未知”。
7. **构图 (composition)**：根据文案主体、动作、情绪、地点、光影和物品关系自然选择景别；可用近景、半身、中景、远景、全景、手部特写、物品特写、静物构图等，不要按分享类型固定镜头。
8. **构图逻辑 (frame_logic)**：用一句话说明为什么这样取景，并说明哪些身体范围、物品或环境会进入画面。
9. **穿搭 (outfit)**：只描述主角/你本人在 composition 里可能看见的穿搭。{outfit_hint} 请明确区分"内搭"和"外穿"层次，并说明外套是否穿着、半脱、挂在椅背或不需要；不可见部位不要写进此字段，可放入 outfit_logic 解释。不要在此字段描写其他人的衣着。
10. **穿搭逻辑 (outfit_logic)**：用一句话说明为什么主角这样穿，重点说明你如何根据地点、温度、动作、构图范围和文案语气判断外套与脚部状态。
11. **动作 (action)**：只描述 composition 里能看见的人物动作。

请严格输出 JSON 格式：
{{
    "subject": "...",
    "environment": "...",
    "lighting": "...",
    "scene_type": "...",
    "temperature_feel": "...",
    "weather_condition": "...",
    "composition": "...",
    "frame_logic": "...",
    "outfit": "...",
    "outfit_logic": "...",
    "action": "...",
    "weather_vibe": "..."
}}
"""

    async def _agent_extract_visuals(
        self,
        content: str,
        life_context: str,
        share_type: ShareType = None,
        involves_self: bool = False,
        target_umo: str = None,
    ) -> Dict[str, str]:
        """使用智能体一次性提取：主体、环境、光影、场景、天气温感、穿搭、动作。"""
        if not content and not life_context:
            return {}

        now = datetime.now()
        period = self._get_current_period()
        hour = now.hour
        system_prompt = self._visual_extraction_system_prompt(
            hour=hour,
            time_hint=_visual_time_hint(period, hour),
            outfit_hint=_visual_outfit_hint(period in [TimePeriod.LATE_NIGHT, TimePeriod.DAWN]),
            logic_prompt=_visual_location_logic(self.img_conf.get("priority_text_over_schedule", True), hour),
            frame_prompt=self._format_visual_extraction_frame(share_type, involves_self),
        )
        user_prompt = f"【分享文案】：{content}\n【生活日程】：{life_context}\n\n请提取视觉元素："

        try:
            res = await self._call_llm(user_prompt, system_prompt, timeout=45, target_umo=target_umo)
            if not res:
                return {}
            clean_json = _extract_json_object(res)
            return json.loads(clean_json)
        except Exception as e:
            logger.warning(f"[每日分享] 智能提取失败: {e}")
            return {}

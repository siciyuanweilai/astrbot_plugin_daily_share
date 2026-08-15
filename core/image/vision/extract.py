from __future__ import annotations

import asyncio
import json
from datetime import datetime

from astrbot.api import logger

from ...config import ShareType, TimePeriod
from .frame import ImageVisualFrameService
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
        return (
            "当前是休息时间；如果【生活日程】提供了【今日穿搭】，它就是已经穿上的当前事实，"
            "必须按原文提取，不得因为深夜、居家、卧床或晚安文案自行替换成睡衣。"
            "只有【今日穿搭】为空时，才能根据明确的睡前状态推断睡衣或家居服。"
        )
    return (
        "如果【生活日程】提供了【今日穿搭】，必须按原文提取；"
        "只有【今日穿搭】为空时，才能结合地点、天气和温度推断合理穿搭。"
    )


def _life_current_outfit(life_context: str | None) -> str:
    prefix = "【今日穿搭】"
    for line in str(life_context or "").splitlines():
        text = line.strip()
        if text.startswith(prefix):
            return text.removeprefix(prefix).strip()
    return ""


def _life_current_appearance(life_context: str | None) -> dict[str, str]:
    prefix = "【当前外观】"
    fields = {
        "发型名称": "hair_style",
        "发型细节": "hair",
        "妆容": "makeup",
        "美甲": "nails",
    }
    for line in str(life_context or "").splitlines():
        text = line.strip()
        if not text.startswith(prefix):
            continue
        appearance: dict[str, str] = {}
        for item in text.removeprefix(prefix).replace("｜", "|").split("|"):
            normalized = item.strip().replace("：", ":", 1)
            label, separator, value = normalized.partition(":")
            key = fields.get(label.strip()) if separator else None
            value = value.strip()
            if key and value:
                appearance[key] = value
        return appearance
    return {}


def _visual_outfit_policy() -> str:
    return """
【主角外观决策策略】
- 信息优先级：生活日程中的今日穿搭/当前外观 > 分享文案明确描述 > 天气温度与当前时段推断；资料没有支持的衣着、外观、动作和人物关系不要补全。
- 穿搭事实：【今日穿搭】是主角当前已经穿上的事实，不是搭配建议。存在该字段时必须保持服装类别、颜色、款式和组成，不得因场景或时段替换成睡衣、家居服或其他服装。
- 归属边界：【今日穿搭】和【当前外观】只属于主角/你本人；其他人物只按文案或关系原文明确写出的外观处理。
- 动态优先：生活日程明确提供的当前发型、妆容和美甲是当天事实，优先于角色人设中的固定造型；不得改写或套用给其他人物。
- 场景策略：家里偏居家状态；室内公共场所保留日常外出合理性；室外必须符合天气、温度和外出场景。
- 可见性策略：outfit 可按构图省略完全不可见的组成，但不得改变可见服装；hair_style、hair、makeup、nails 只写构图中能看见的内容，不可见或不确定时留空。
- 推断边界：只有【今日穿搭】为空时才允许根据地点、天气、温度和时段推断服装，并把依据写入 outfit_logic。
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


class ImageVisualExtractService(ImageVisualFrameService):
    """用大语言模型提取图像视觉要素。"""

    def _format_visual_extraction_frame(
        self, share_type: ShareType | None = None, involves_self: bool = False
    ) -> str:
        if not involves_self:
            return (
                "请根据文案主体、地点、情绪和画面重点自然选择构图，不要按分享类型固定镜头；"
                "可以选择静物特写、环境中景、远景或全景。若出现人物，也只作为环境尺度参考，不补充完整衣着细节。"
            )
        return (
            "请根据文案主体、情绪、动作、地点和画面重点自然选择构图，不要按分享类型固定镜头；"
            "可以选择脸部近景、半身、中景、远景、全景、手部或物品特写。"
            "composition 写最终构图，frame_logic 说明为什么这样取景以及哪些内容在画面范围内可见。"
            "outfit、hair_style、hair、makeup、nails 和 action 只写入该构图中能直接看见的内容，"
            "不把生活状态里未入镜的内容写进画面词。"
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
4. **场景与外观判断**：先判断当前画面属于“家里 / 室内公共场所 / 室外 / 未知”，再根据地点、天气、温度、动作和构图可见范围决定穿搭与当前外观。

{_visual_outfit_policy()}

【提取要求】
1. **主体 (subject)**：【最重要】画面的核心物体描述（例如：精致的荷花酥，一杯牛奶或者一本封皮复古的书）。如果是纯风景或画人，此项填“无”。
2. **环境 (environment)**：根据逻辑确定的具体地点。
3. **光影 (lighting)**：参考时间段[{time_hint}]。如果是室内，强调人造光；如果是室外，强调自然天气氛围。
4. **场景 (scene_type)**：填“家里 / 室内公共场所 / 室外 / 未知”之一。
5. **温感 (temperature_feel)**：根据天气温度和文案判断，填“寒冷 / 微凉 / 舒适 / 温暖 / 炎热 / 未知”之一。
6. **天气 (weather_condition)**：提取晴、雨、雪、阴、闷热、潮湿等真实天气；不明确则填“未知”。
7. **构图 (composition)**：根据文案主体、动作、情绪、地点、光影和物品关系自然选择景别；可用近景、半身、中景、远景、全景、手部特写、物品特写、静物构图等，不要按分享类型固定镜头。
8. **构图逻辑 (frame_logic)**：用一句话说明为什么这样取景，并说明哪些身体范围、物品或环境会进入画面。
9. **穿搭 (outfit)**：只描述主角/你本人在 composition 里能看见的穿搭。{outfit_hint} 可说明内搭/外穿层次、外套状态和可见鞋袜；不要描写其他人的衣着。
10. **发型名称 (hair_style)**：只提取【当前外观】明确提供且在 composition 里可见的主角当天发型名称；没有则留空。
11. **发型细节 (hair)**：只提取【当前外观】明确提供且在 composition 里可见的主角当天发型细节；没有则留空。
12. **妆容 (makeup)**：只提取【当前外观】明确提供且在 composition 里可见的主角当天妆容；没有则留空。
13. **美甲 (nails)**：只提取【当前外观】明确提供且在 composition 里可见的主角当天美甲；没有则留空。
14. **穿搭逻辑 (outfit_logic)**：用一句话说明穿搭判断依据，覆盖地点、温度、动作、构图可见范围和是否引用今日穿搭。
15. **动作 (action)**：只描述 composition 里能看见的人物动作。

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
    "hair_style": "...",
    "hair": "...",
    "makeup": "...",
    "nails": "...",
    "outfit_logic": "...",
    "action": "...",
    "weather_vibe": "..."
}}
"""

    async def _agent_extract_visuals(
        self,
        content: str,
        life_context: str | None,
        share_type: ShareType | None = None,
        involves_self: bool = False,
        target_umo: str | None = None,
    ) -> dict[str, str]:
        """使用智能体一次性提取：主体、环境、光影、场景、天气温感、穿搭、动作。"""
        if not content and not life_context:
            return {}

        now = datetime.now()
        period = self._get_current_period()
        hour = now.hour
        system_prompt = self._visual_extraction_system_prompt(
            hour=hour,
            time_hint=_visual_time_hint(period, hour),
            outfit_hint=_visual_outfit_hint(
                period in [TimePeriod.LATE_NIGHT, TimePeriod.DAWN]
            ),
            logic_prompt=_visual_location_logic(
                self.img_conf.get("priority_text_over_schedule", True), hour
            ),
            frame_prompt=self._format_visual_extraction_frame(
                share_type, involves_self
            ),
        )
        user_prompt = (
            f"【分享文案】：{content}\n【生活日程】：{life_context}\n\n请提取视觉元素："
        )

        try:
            res = await self._call_llm(
                user_prompt, system_prompt, timeout=45, target_umo=target_umo
            )
            if not res:
                return {}
            clean_json = _extract_json_object(res)
            visuals = await asyncio.to_thread(json.loads, clean_json)
            if not isinstance(visuals, dict):
                return {}
            current_outfit = _life_current_outfit(life_context) if involves_self else ""
            current_appearance = (
                _life_current_appearance(life_context) if involves_self else {}
            )
            if current_outfit:
                visuals["outfit"] = current_outfit
                visuals["outfit_source"] = "daily_life"
                visuals["outfit_logic"] = "使用生活插件明确提供的当前穿搭"
            if current_appearance:
                visuals.update(current_appearance)
                visuals["appearance_source"] = "daily_life"
            return visuals
        except Exception as e:
            logger.warning(f"[日常分享] 智能提取失败: {e}")
            return {}

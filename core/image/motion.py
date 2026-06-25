import json
from typing import Optional

from astrbot.api import logger

from ..toolkit import call_default_daily_life_media_tool, format_exception, log_exception
from .composer import _extract_json_object


VIDEO_MOTION_FALLBACK = (
    "保持原图主体、人物五官、服装、场景、光线、构图重心、景别和主体位置一致；根据画面加入自然轻微镜头运动"
    "（缓慢推近、缓慢横移或少量手持呼吸感）、人物或物体细微动作和氛围变化，不改变人物比例或画面关系"
)
VIDEO_SOUND_FALLBACK = (
    "根据画面铺一层自然环境声和细微动作声，默认加入轻柔背景声；若画面有人物且情绪适合，"
    "加入一句短促的画面内自然台词并配合口型；禁止旁白、画外音、解说或朗读文案"
)


class ImageVideoMixin:
    @staticmethod
    def _normalize_video_design_value(value: object, limit: int) -> str:
        text = str(value or "").replace("```json", "").replace("```", "").strip()
        text = " ".join(text.split()).strip(" ：:，,。")
        return text[:limit]

    async def _build_video_design_prompts(
        self,
        image_description: str,
        content: str = "",
        target_umo: str = None,
    ) -> tuple[str, str]:
        """根据画面描述和文案一次性生成匹配的动态与声音提示词。"""
        image_description = str(image_description or "").strip()
        content = str(content or "").strip()
        if not image_description and not content:
            return VIDEO_MOTION_FALLBACK, VIDEO_SOUND_FALLBACK

        system_prompt = """
你是短视频导演兼声音设计师。根据画面描述和分享文案，为生活感图生视频生成互相匹配的动态设计和声音设计。
要求：
1. 只输出 JSON 对象，格式为 {"motion":"...","sound":"..."}，不要解释，不加 Markdown。
2. 视频化方式由画面本身、文案情绪、主体关系自然决定；motion 默认要包含自然镜头运动、人物或物体细微动作和氛围变化，优先从轻微推近、缓慢横移或少量手持呼吸感中选择一种，不改变原图景别、构图重心和人物比例。
3. 必须保持原图主体、人物身份、五官、脸型、发型、年龄感、气质、服装、场景、光线、构图、景别、主体位置和人物关系一致；不新增人物、物体、剧情动作或夸张表演。
4. 如果画面有人物，人物应在不破坏原图姿态和朝向的前提下，自然看向镜头或与镜头产生轻微眼神交流，保持原有神态和气质；不要强行微笑、挥手或夸张表演。
5. motion 写成有生活感的连续动态：镜头运动、人物或物体微动、光影/天气/环境氛围变化都要自然衔接；不要默认写静止镜头，只有画面明显需要安静凝固时才可弱化镜头运动。
6. 若 sound 有人物台词，motion 必须包含嘴唇轻微自然开合并与说话节奏同步，可有细微点头、眨眼、呼吸感；若 sound 没有台词，人物不要出现明显说话口型。
7. sound 必须有真实生活声层次，默认考虑环境声、动作声和轻柔背景声；不要默认写无人声、无背景音乐，只有画面明显不适合时才排除人声或音乐。
8. 如果画面有人物，优先判断是否适合让人物根据文案内容自然开口说话；台词应口语化、生活化、短句表达，可提炼成一句符合人物状态和情绪的话。
9. 人声需符合人物的年龄、性别、气质和场景氛围，语气自然，像真实生活中随口说出，并对应画面人物的口型。
10. 当同时包含人声和背景声时，环境声、动作声与背景声要自然融合，保持真实生活场景里的声音层次，人物说话清晰可听但不过分贴耳，背景声持续存在但不喧宾夺主。
11. 禁止旁白、画外音、解说或朗读文案；不要把分享文案原样念出来。
12. motion 和 sound 都写成一行中文，真实、克制、贴合生活感短视频。
"""
        user_prompt = (
            f"画面描述：{image_description}\n"
            f"分享文案：{content}\n\n"
            '请输出 JSON：{"motion":"...","sound":"..."}'
        )

        try:
            res = await self._call_llm(user_prompt, system_prompt, timeout=18, target_umo=target_umo)
            data = json.loads(_extract_json_object(res))
            if not isinstance(data, dict):
                raise ValueError("视频设计结果不是 JSON 对象")

            motion = self._normalize_video_design_value(data.get("motion"), 260)
            sound = self._normalize_video_design_value(data.get("sound"), 240)
            if motion and sound:
                return motion, sound
            if motion:
                return motion, VIDEO_SOUND_FALLBACK
            if sound:
                return VIDEO_MOTION_FALLBACK, sound
        except Exception as e:
            log_exception("[每日分享] 生成视频动态与声音提示词失败，使用默认视频提示词", e, level="debug", with_traceback=False)

        return VIDEO_MOTION_FALLBACK, VIDEO_SOUND_FALLBACK

    async def generate_video_from_image(
        self,
        image_path: str,
        content: str,
        target_umo: str = None,
        event=None,
    ) -> Optional[str]:
        """图片转视频"""
        if not self.img_conf.get("enable_ai_video", False):
            return None

        try:
            if not image_path:
                return None
            logger.info("[每日分享] 正在将配图转换为视频...")
            
            # 构建视频提示词（复用之前的图片描述，生成匹配的动态和声音设计）
            image_description = self._last_image_description or ""
            motion_prompt, sound_prompt = await self._build_video_design_prompts(
                image_description,
                content,
                target_umo=target_umo,
            )
            video_prompt = f"画面：{image_description}。动态：{motion_prompt}。声音：{sound_prompt}。"
            logger.info(f"[每日分享] 视频动态提取：动态: {motion_prompt[:180]}...")
            logger.info(f"[每日分享] 声音设计提取：声音: {sound_prompt[:180]}...")
            logger.info(f"[每日分享] 最终视频提示词: {video_prompt[:180]}...")

            return await call_default_daily_life_media_tool(
                self.context,
                media_kind="video",
                prompt=video_prompt,
                image_ref=image_path,
            )
                
        except Exception as e:
            log_exception("[每日分享] 视频生成流程异常", e, with_traceback=False)
            return None

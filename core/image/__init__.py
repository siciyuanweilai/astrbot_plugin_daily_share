from datetime import datetime

from astrbot.api import logger

from ..config import ShareType, TimePeriod
from ..constants import share_type_label
from ..integrations.mediajob import current_share_job
from ..toolkit import call_default_daily_life_media_tool
from .motion import ImageVideoService
from .result import GeneratedImage
from .vision.extract import ImageVisualExtractService
from .vision.frame import ImageVisualFrameService
from .vision.instruction import ImageVisualPromptService
from .vision.judge import ImageVisualJudgeService
from .vision.persona import ImageVisualPersonaService


class ImageService:
    def __init__(self, context, config, llm_func, daily_life_bridge=None):
        self.context = context
        self.config = config
        self.call_llm = llm_func
        self.daily_life_bridge = daily_life_bridge

        # 获取配置引用
        self.img_conf = self.config.get("image_conf", {})
        self.prompts = ImageVisualPromptService(self)
        self.persona = ImageVisualPersonaService(self)
        self.judge = ImageVisualJudgeService(self)
        self.extract = ImageVisualExtractService(self)
        self.frame = ImageVisualFrameService(self)
        self.video = ImageVideoService(self)

    async def _call_llm(self, *args, target_umo: str | None = None, **kwargs):
        if target_umo:
            kwargs["umo"] = target_umo
        return await self.call_llm(*args, **kwargs)

    def _get_current_period(self) -> TimePeriod:
        """获取当前时间段"""
        hour = datetime.now().hour
        if 0 <= hour < 6:
            return TimePeriod.DAWN
        elif 6 <= hour < 9:
            return TimePeriod.MORNING
        elif 9 <= hour < 12:
            return TimePeriod.FORENOON
        elif 12 <= hour < 14:
            return TimePeriod.NOON
        elif 14 <= hour < 16:
            return TimePeriod.AFTERNOON
        elif 16 <= hour < 19:
            return TimePeriod.EVENING
        elif 19 <= hour < 22:
            return TimePeriod.NIGHT
        else:
            return TimePeriod.LATE_NIGHT

    async def generate_image(
        self,
        content: str,
        share_type: ShareType,
        life_context: str | None = None,
        target_umo: str | None = None,
        event=None,
    ) -> GeneratedImage | None:
        """生成图片的入口函数"""
        if not self.img_conf.get("enable_ai_image", False):
            return None
        job = current_share_job.get()
        if job is not None and job.get("image_failed"):
            return None
        if job is not None and job.get("image_path"):
            return GeneratedImage(
                path=job["image_path"],
                description=job.get("image_description", ""),
                contains_character=bool(job.get("contains_character")),
            )

        # 1. 智能判断：是否画人
        involves_self = await self._check_involves_self(
            content, share_type, target_umo=target_umo
        )
        mode_str = "人物+场景" if involves_self else "纯静物/风景"
        is_text_priority = self.img_conf.get("priority_text_over_schedule", True)
        logic_str = "文案主导" if is_text_priority else "日程主导"

        logger.info(
            f"[日常分享] 配图决策: {mode_str} ({logic_str}) | 类型: {share_type_label(share_type)}"
        )

        # 3. 智能提取视觉元素
        visuals = {}
        if content or life_context:
            visuals = await self._agent_extract_visuals(
                content,
                life_context,
                share_type=share_type,
                involves_self=involves_self,
                target_umo=target_umo,
            )

            # 如果大语言模型提取失败（返回空字典），则直接放弃配图
            if not visuals:
                logger.warning("[日常分享] 智能提取失败，已取消配图，仅发送文案")
                return None

            visuals = self._enforce_visual_mode(visuals, involves_self)

            # 日志记录提取结果
            env = visuals.get("environment", "无")
            subj = visuals.get("subject", "无")
            outfit = (
                str(visuals.get("outfit", "") or "").strip() or "无"
                if involves_self
                else "不适用"
            )
            scene = visuals.get("scene_type", "未知")
            temp = visuals.get("temperature_feel", "未知")
            weather = visuals.get("weather_condition") or visuals.get(
                "weather_vibe", "无"
            )
            logger.debug(
                f"[日常分享] 配图智能提取：主体: {subj} | 场景: {scene} | 环境: {env} | "
                f"天气: {weather} | 温感: {temp} | 穿搭: {outfit[:15]}..."
            )

        # 4. 组装最终提示词
        prompt = await self._assemble_final_prompt(
            content, share_type, involves_self, visuals, target_umo=target_umo
        )

        if not prompt:
            logger.warning("[日常分享] 提示词组装失败，取消配图")
            return None
        logger.debug(f"[日常分享] 最终配图提示词: {prompt[:100]}...")
        image_path = await call_default_daily_life_media_tool(
            self.context,
            media_kind="image",
            prompt=prompt,
            event=event,
            contains_character=involves_self,
            bridge=self.daily_life_bridge,
        )
        if not image_path:
            return None
        return GeneratedImage(
            path=str(image_path),
            description=prompt,
            contains_character=involves_self,
        )

    async def _assemble_final_prompt(
        self, content, share_type, involves_self, visuals, target_umo=None
    ):
        return await self.prompts._assemble_final_prompt(
            content, share_type, involves_self, visuals, target_umo
        )

    async def _append_self_visual_prompts(self, prompts, visuals, target_umo):
        return await self.prompts._append_self_visual_prompts(
            prompts, visuals, target_umo
        )

    @staticmethod
    def _format_current_appearance(visuals):
        return ImageVisualPromptService._format_current_appearance(visuals)

    @staticmethod
    def _append_subject_visual_prompts(prompts, visuals):
        return ImageVisualPromptService._append_subject_visual_prompts(prompts, visuals)

    def _append_environment_prompts(self, prompts, visuals):
        return self.prompts._append_environment_prompts(prompts, visuals)

    async def _get_appearance_keywords(self, target_umo=None):
        """获取人设外貌。"""
        return await self.persona._get_appearance_keywords(target_umo)

    async def _get_persona_figure_keywords(self, target_umo=None):
        return await self.persona._get_persona_figure_keywords(target_umo)

    async def _check_involves_self(self, content, share_type, target_umo=None):
        """检测内容是否涉及“自己”。"""
        return await self.judge._check_involves_self(content, share_type, target_umo)

    def _format_visual_extraction_frame(self, share_type=None, involves_self=False):
        return self.extract._format_visual_extraction_frame(share_type, involves_self)

    def _visual_extraction_system_prompt(self):
        return self.extract._visual_extraction_system_prompt()

    async def _agent_extract_visuals(
        self,
        content,
        life_context,
        share_type=None,
        involves_self=False,
        target_umo=None,
    ):
        """使用智能体一次性提取：主体、环境、光影、场景、天气温感、穿搭、动作。"""
        return await self.extract._agent_extract_visuals(
            content, life_context, share_type, involves_self, target_umo
        )

    @staticmethod
    def _has_visual_subject(visuals):
        return ImageVisualFrameService._has_visual_subject(visuals)

    def _resolve_visual_mode(self, visuals, contains_character):
        return self.frame._resolve_visual_mode(visuals, contains_character)

    def _enforce_visual_mode(self, visuals, contains_character):
        """固定人物、静物或风景模式，避免模型构图覆盖上游决策。"""
        return self.frame._enforce_visual_mode(visuals, contains_character)

    def _resolve_composition(self, visuals, involves_self):
        return self.frame._resolve_composition(visuals, involves_self)

    def _format_outfit_consistency_hint(self, visuals, frame_hint=""):
        return self.frame._format_outfit_consistency_hint(visuals, frame_hint)

    @staticmethod
    def _normalize_video_design_value(value, limit=None):
        return ImageVideoService._normalize_video_design_value(value, limit)

    @staticmethod
    def _normalize_video_dialogue(value):
        return ImageVideoService._normalize_video_dialogue(value)

    @staticmethod
    def _compose_video_sound(dialogue, ambience):
        return ImageVideoService._compose_video_sound(dialogue, ambience)

    async def _build_video_design_prompts(
        self, image_description, content="", target_umo=None
    ):
        """根据画面描述和文案一次性生成匹配的动态与声音提示词。"""
        return await self.video._build_video_design_prompts(
            image_description, content, target_umo
        )

    async def generate_video_from_image(
        self, image_path, content, image_description="", target_umo=None, event=None
    ):
        """图片转视频"""
        return await self.video.generate_video_from_image(
            image_path, content, image_description, target_umo, event
        )


__all__ = ["GeneratedImage", "ImageService"]

from datetime import datetime

from astrbot.api import logger

from ..config import DEFAULT_KNOWLEDGE_CATS, DEFAULT_REC_CATS, ShareType, TimePeriod
from ..database.keys import (
    QZONE_TARGET_ID,
    is_public_share_target,
    public_share_target_label,
)
from ..identity import build_content_system_prompt
from ..integrations import DailyLifeBridge
from .article import ContentNewsService
from .assist import ContentSupportService
from .knowledge import ContentKnowledgeService
from .recommendation import ContentRecommendationService
from .social import ContentSocialService
from .topic import ContentTopicService


class ContentService:
    """聚合独立内容组件的统一生成服务。"""

    def __init__(
        self,
        config: dict,
        llm_func,
        context,
        db_manager,
        news_service=None,
        daily_life_bridge=None,
    ):
        """
        初始化内容生成服务
        """
        self.config = config
        self.call_llm = llm_func
        self.context = context
        self.db = db_manager
        self.news_service = news_service
        self.daily_life_bridge = daily_life_bridge or DailyLifeBridge(context)
        self.support = ContentSupportService(self)

        self.content_lib_conf = self.config.get("content_library", {})
        raw_knowledge = self.content_lib_conf.get(
            "knowledge_cats", DEFAULT_KNOWLEDGE_CATS
        )
        if not raw_knowledge:
            raw_knowledge = DEFAULT_KNOWLEDGE_CATS
        self.knowledge_cats = self.parse_category_config(raw_knowledge)
        raw_rec = self.content_lib_conf.get("rec_cats", DEFAULT_REC_CATS)
        if not raw_rec:
            raw_rec = DEFAULT_REC_CATS
        self.rec_cats = self.parse_category_config(raw_rec)

        self.basic_conf = self.config.get("basic_conf", {})
        raw_dedup_days = self.basic_conf.get("data_retention_days", 60)
        try:
            self.dedup_days = int(raw_dedup_days)
        except Exception:
            self.dedup_days = 60

        self.news_conf = self.config.get("news_conf", {})
        self.context_conf = self.config.get("context_conf", {})
        self.qzone_conf = self.config.get("qzone_conf", {})

        self.topic = ContentTopicService(self)
        self.recommendation = ContentRecommendationService(self)
        self.knowledge = ContentKnowledgeService(self)
        self.news = ContentNewsService(self)
        self.social = ContentSocialService(self)

    def parse_category_config(self, categories):
        return self.support.parse_category_config(categories)

    async def get_persona_info(self, target_umo: str | None = None):
        return await self.support.get_persona_info(target_umo)

    async def get_qzone_chat_style_prompt(self, *, scene: str = "") -> str:
        return await self.daily_life_bridge.get_share_chat_style_prompt(scene=scene)

    async def generate(
        self,
        stype: ShareType,
        period: TimePeriod,
        target_id: str,
        is_group: bool,
        life_ctx: str,
        news_data: tuple[list, str] | None = None,
        nickname: str = "",
        recent_dynamics: str = "",  # 兼容旧调用；历史改由已确认发送记录按目标加载，此参数不进入上下文。
        structured_history: str = "",
        recent_post_contents: list[str] | None = None,
        share_materials: list[dict] | None = None,
    ) -> str | None:
        """统一生成入口"""
        # 获取人设信息
        persona_info = await self.get_persona_info(target_id)

        # 区分【亲昵称呼】和【用户昵称】：
        # - 亲昵称呼只来自人设配置，避免把本地昵称映射写成第三人称。
        # - 用户昵称参数仅用来判断日程/记忆里出现的人是否就是当前私聊对象。
        persona_user_name = persona_info.get("user_name", "").strip()
        detect_names = []
        for name in (nickname, persona_user_name):
            name = str(name or "").strip()
            if name and name not in detect_names:
                detect_names.append(name)
        detect_name = "、".join(detect_names)
        if is_group:
            call_name = ""
        else:
            call_name = persona_user_name

        now = datetime.now()
        date_str = now.strftime("%Y年%m月%d日")
        time_str = now.strftime("%H:%M")

        life_hint = life_ctx or ""
        chat_style = ""
        is_qzone_post = target_id == QZONE_TARGET_ID
        expression_scene = (
            "qzone_post"
            if is_qzone_post
            else ("share_group" if is_group else "share_private")
        )
        chat_style = await self.daily_life_bridge.get_share_chat_style_prompt(
            scene=expression_scene
        )
        if is_qzone_post:
            if not chat_style:
                chat_style = (
                    "【QQ 空间说说表达】\n"
                    "像平时说话一样随手发一条状态，意思说完就自然停住，"
                    "按语意自然换行，不固定字数、行数或标题模板。"
                )
        elif not chat_style:
            chat_style = (
                "【日常分享表达】\n"
                "像平时说话一样自然分享，意思说清楚就停，不凑字数、不补抒情或总结。"
                "问候心情围绕当下一点；新闻知识推荐保留必要事实和主体，不硬压成一句。"
            )

        ctx_data = {
            "qzone_chat_style_hint": chat_style if is_qzone_post else "",
            "share_chat_style_hint": chat_style if not is_qzone_post else "",
            "expression_scene": expression_scene,
            "share_type": stype.value,
            "target_id": target_id,
            "is_group": is_group,
            "is_qzone_post": is_qzone_post,
            "life_hint": life_hint,
            "structured_history_hint": self.support._build_structured_history_prompt(
                structured_history
            ),
            "system_prompt": build_content_system_prompt(
                persona_info.get("prompt", "")
            ),
            "output_format_hint": self.support._build_output_format_prompt(target_id),
            "public_target": is_public_share_target(target_id),
            "public_target_label": public_share_target_label(target_id),
            "period_label": self.support._get_period_label(period),
            "date_str": date_str,
            "time_str": time_str,
            "nickname": call_name,
            "detect_name": detect_name,
            "recent_post_contents": recent_post_contents or [],
            "share_materials": share_materials or [],
        }

        try:
            if stype == ShareType.GREETING:
                result = await self.social._gen_greeting(period, ctx_data)
            elif stype == ShareType.NEWS:
                result = await self.news._gen_news(news_data, ctx_data)
            elif stype == ShareType.MOOD:
                result = await self.social._gen_mood(period, ctx_data)
            elif stype == ShareType.KNOWLEDGE:
                result = await self.knowledge._gen_knowledge(ctx_data)
            elif stype == ShareType.RECOMMENDATION:
                result = await self.recommendation._gen_rec(ctx_data)
            else:
                result = await self.social._gen_greeting(period, ctx_data)
            if (
                result
                and not is_qzone_post
                and any(
                    "".join(result.split()) == "".join(text.split())
                    for text in ctx_data["recent_post_contents"]
                )
            ):
                logger.info(
                    "[内容服务] 分享正文与当前对象近期已发内容重复，跳过本次发送"
                )
                return None
            return result

        except Exception as e:
            logger.error(f"[内容服务] 生成内容出错: {e}")
            return None

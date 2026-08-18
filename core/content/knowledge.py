import random
import re

from astrbot.api import logger

from ..database.keys import is_public_share_target, public_share_target_label
from ..prompt import (
    build_common_content_rules,
    build_opening_integrity_rule,
)
from .contentbase import ContentComponent


class ContentKnowledgeService(ContentComponent):
    async def _gen_knowledge(self, ctx: dict):
        """生成知识分享。"""
        if not self.news_service:
            logger.warning(
                "[内容服务] 无法调用百度百科服务，无法查询相关资料，取消分享"
            )
            return None

        is_group = ctx["is_group"]
        is_qzone = is_public_share_target(ctx.get("target_id"))
        public_label = public_share_target_label(ctx.get("target_id"))
        call_name = ctx.get("nickname", "")
        detect_name = ctx.get("detect_name", "")

        # 0. 获取配置
        allow_detail = self.context_conf.get("group_share_schedule", False)
        # 随机选择大类和子类
        categories = [
            (name, tags)
            for name, tags in self.knowledge_cats.items()
            if isinstance(tags, (list, tuple)) and tags
        ]
        if not categories:
            logger.warning("[内容服务] 知识库未配置有效分类，取消知识分享")
            return None
        main_cat, tags = random.choice(categories)
        sub_cat = random.choice(tags)
        target_id = ctx["target_id"]

        logger.info(f"[内容服务] 知识方向: {main_cat} - {sub_cat}")

        # 使用智能发散选题
        target_keyword = await self._agent_brainstorm_topic(
            main_cat, sub_cat, target_id
        )
        if not target_keyword:
            logger.warning("[内容服务] 无法生成知识关键词，取消分享")
            return None

        baike_context = await self._fetch_content_reference(
            target_keyword,
            search_kind="knowledge",
            target_umo=target_id,
            heading="参考资料（请基于以下真实数据进行通俗化讲解，不要自行捏造）",
            baike_label="百度百科词条",
            web_label="全网检索",
        )
        if not baike_context:
            logger.warning(
                f"[内容服务] 未命中任何外部资料，取消知识分享: {target_keyword}"
            )
            return None
        logger.info(f"[内容服务] 知识资料获取成功: {target_keyword}")

        user_info_prompt = ""
        if not is_group and not is_qzone:
            user_info_prompt = self._build_user_prompt(
                call_name, detect_name, ctx.get("target_id", "")
            )

        common_rules = build_common_content_rules(
            is_group=is_group,
            is_qzone=is_qzone,
            date_text=ctx["date_str"],
            time_text=ctx["time_str"],
            period_label=ctx["period_label"],
            action="分享知识",
            allow_detail=allow_detail,
            public_label=public_label,
        )
        dynamics_prompt = self._build_recent_dynamics_prompt(ctx.get("recent_dynamics"))

        target_str = public_label if is_qzone else ("群聊" if is_group else "私聊")
        opening_guide = self._knowledge_opening_guide(is_qzone, is_group)
        opening_rule = build_opening_integrity_rule(
            f"{opening_guide}\n- 场景关联型：只有逻辑通顺时才结合当前状态。"
        )
        prompt = f"""
【当前时间】{ctx["date_str"]} {ctx["time_str"]} ({ctx["period_label"]})
你现在的任务是：向{target_str}分享下面的冷知识。

【核心任务】
1. 知识点关键词：【{target_keyword}】
2. 基于下面的资料进行通俗化讲解。

{baike_context}
{user_info_prompt}
{ctx["life_hint"]}
{ctx["structured_history_hint"]}
{dynamics_prompt}

{common_rules}
{ctx.get("output_format_hint", "")}
{opening_rule}

【要求】
1. 以你的人设性格说话，自然分享。
2. {"语气轻松简洁" if is_group else "可以详细展开，带点个人见解"}。
3. 可以加入你的个人感想或小评论
4. 用【】将核心关键词【{target_keyword}】括起来。
5. {"字数：100-150字" if is_group else "字数：100-200字"}。
6. 直接输出分享内容。
"""

        res = await self._call_llm(
            prompt=prompt,
            system_prompt=ctx["system_prompt"],
            target_umo=ctx.get("target_id"),
        )

        if res:
            try:
                matches = re.findall(r"【(.*?)】", res)
                keyword = matches[0] if matches else target_keyword or res[:10]
                await self.db.record_topic(target_id, "knowledge", keyword)
            except Exception as e:
                logger.debug(f"[内容服务] 记录知识主题失败: {e}")

            if self.content_lib_conf.get("show_knowledge_type_prefix", True):
                return f"知识类型: {main_cat} - {sub_cat}\n\n{res}"
            return res
        return None

    @staticmethod
    def _knowledge_opening_guide(is_qzone: bool, is_group: bool) -> str:
        if is_qzone:
            return '- 记录型："刚看到一个有趣的说法..." / "原来..." / "今天才知道..."'
        if is_group:
            return '- 群聊型："大家有没有想过..." / "分享个挺有意思的知识点..."'
        return '- 私聊型："你知道吗..." / "刚看到一个有趣的说法..."'

import asyncio
import random
import re

from astrbot.api import logger

from ..database.keys import QZONE_TARGET_ID
from ..prompt import (
    build_common_content_rules,
    build_opening_integrity_rule,
    build_scene_consistency_rule,
)


class ContentRecommendationMixin:
    async def _gen_rec(self, ctx: dict):
        """生成推荐分享。"""
        if not self.news_service:
            logger.warning("[内容服务] 无法调用百度百科服务，无法查询相关资料，取消分享")
            return None

        is_group = ctx['is_group']
        is_qzone = ctx.get('target_id') == QZONE_TARGET_ID
        call_name = ctx.get('nickname', '')
        detect_name = ctx.get('detect_name', '')

        # 0. 获取配置
        allow_detail = self.context_conf.get("group_share_schedule", False)
        enable_web_search = self.news_conf.get("enable_tavily_search", True)
        
        # 随机选择大类和子类
        rec_type = random.choice(list(self.rec_cats.keys()))
        sub_style = random.choice(self.rec_cats[rec_type])
        
        target_id = ctx['target_id'] 
        
        logger.info(f"[内容服务] 推荐方向: {rec_type} ({sub_style})")

        # 使用智能发散选题
        target_work = await self._agent_brainstorm_topic(rec_type, sub_style, target_id)
        if not target_work:
             logger.warning("[内容服务] 无法生成推荐作品名，取消分享")
             return None

        # 2. 并发查询百度百科和联网搜索
        baike_task = asyncio.create_task(self.news_service.get_baike_info(target_work))
        tavily_task = asyncio.create_task(self._fetch_web_search(target_work, "rec")) if enable_web_search else None
        
        info = await baike_task
        tavily_info = ""
        if tavily_task:
            _, tavily_info = await tavily_task

        if info or tavily_info:
            baike_context = f"\n\n【资料简介（真实数据，请参考它来推荐，不要自行捏造）】\n"
            if info:
                baike_context += f"百度百科简介：{info}\n"
            if tavily_info:
                baike_context += f"全网评价与亮点：{tavily_info}\n"
            logger.info(f"[内容服务] 推荐资料获取成功: {target_work} (百度百科命中: {'是' if info else '否'}, 联网检索命中: {'是' if tavily_info else '否'})")
        else:
            logger.warning(f"[内容服务] 未命中任何外部资料，取消推荐分享: {target_work}")
            return None

        user_info_prompt = ""
        if not is_group and not is_qzone:
            user_info_prompt = self._build_user_prompt(call_name, detect_name)

        common_rules = build_common_content_rules(
            is_group=is_group,
            is_qzone=is_qzone,
            date_text=ctx["date_str"],
            time_text=ctx["time_str"],
            period_label=ctx["period_label"],
            action="推荐",
            allow_detail=allow_detail,
        )
        dynamics_prompt = self._build_recent_dynamics_prompt(ctx.get('recent_dynamics'))

        target_str = "QQ空间" if is_qzone else ('群聊' if is_group else '私聊')
        if is_qzone:
            opening_guide = "表达自己最近喜欢、重温或发现这个作品的理由，不要写成“推荐给你/大家”的口吻。"
        elif is_group:
            opening_guide = "可以自然地推荐给群友，避免营销号式安利。"
        else:
            opening_guide = "可以面向当前私聊对象推荐，语气像认真分享给一个朋友。"
        opening_rule = build_opening_integrity_rule(
            f"- {opening_guide}\n- 可以用“最近发现了一个...”或“最近在重温...”这类自然开头。\n- 不要评价群聊气氛。"
        )
        scene_rule = build_scene_consistency_rule("推荐")

        prompt = f"""
【当前时间】{ctx['date_str']} {ctx['time_str']} ({ctx['period_label']})
你现在的任务是：向{target_str}推荐【{target_work}】。

【核心指令】
1. 必须基于下面的资料进行推荐，不要更换目标。

{baike_context}
{user_info_prompt}
{ctx.get('self_identity_hint', '')}
{ctx['life_hint']}
{ctx['chat_hint']}
{dynamics_prompt}

{common_rules}
{opening_rule}
{scene_rule}

【推荐文案要求】
1. 以你的人设性格说话，真实自然
2. 开头必须有明确的推荐表达
3. 真诚推荐，避免营销号式的夸张表达
4. 结合资料介绍它的亮点。
5. 务必用【】将推荐目标的名称【{target_work}】括起来。
6. {'字数：80-120字' if is_group else '字数：120-150字'}。
7. 直接输出推荐内容。
"""

        res = await self._call_llm(prompt=prompt, system_prompt=ctx['persona'], target_umo=ctx.get('target_id'))
        
        if res:
            try:
                matches = re.findall(r"【(.*?)】", res)
                keyword = matches[0] if matches else target_work or res[:10]
                await self.db.record_topic(target_id, "rec", keyword)
            except Exception as e:
                logger.debug(f"[内容服务] 记录推荐主题失败: {e}")
            if self.content_lib_conf.get("show_rec_type_prefix", True):
                return f"推荐类型: {rec_type} - {sub_style}\n\n{res}"
            return res
        return None

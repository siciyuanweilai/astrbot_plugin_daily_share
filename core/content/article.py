import asyncio
import random
from typing import List, Tuple

from astrbot.api import logger

from ..database.keys import QZONE_TARGET_ID
from ..config import NEWS_SOURCE_MAP
from ..prompt import build_common_content_rules, build_scene_consistency_rule


class ContentNewsMixin:
    async def _gen_news(self, news_data: Tuple[List, str], ctx: dict):
        """生成新闻分享，带基于联网搜索的自动核查功能。"""
        if not news_data:
            logger.warning("[内容服务] 未获取到新闻数据，取消分享")
            return None

        is_group = ctx['is_group']
        is_qzone = ctx.get('target_id') == QZONE_TARGET_ID
        call_name = ctx.get('nickname', '')
        detect_name = ctx.get('detect_name', '')

        # 0. 获取配置
        allow_detail = self.context_conf.get("group_share_schedule", False)
        enable_web_search = self.news_conf.get("enable_tavily_search", True)

        news_list, source_key = news_data
        source_config = NEWS_SOURCE_MAP.get(source_key, {"name": "热搜", "icon": "📰"})
        source_name = source_config["name"]
        
        items_limit = self.news_conf.get("news_items_count", 5)
        selected_to_search = news_list[:items_limit]

        def get_api_background(item: dict) -> str:
            title = str(item.get("title", "") or "").strip()
            desc = str(item.get("description", "") or "").strip()
            if not desc or desc == title or len(desc) < 20:
                return ""
            return desc

        # 优先使用新闻源接口自带摘要/正文；只有缺少背景时才调用联网搜索。
        search_results = [None] * len(selected_to_search)
        pending_tasks = []
        pending_indexes = []
        api_bg_count = 0
        for idx, item in enumerate(selected_to_search):
            title = item.get("title", "")
            api_bg = get_api_background(item)
            if api_bg:
                search_results[idx] = (title, api_bg)
                api_bg_count += 1
            elif enable_web_search:
                pending_indexes.append(idx)
                pending_tasks.append(self._fetch_web_search(title, "news"))
            else:
                search_results[idx] = (title, "")

        if pending_tasks:
            logger.info(
                f"[内容服务] {source_name} 有 {api_bg_count} 条使用接口摘要，"
                f"{len(pending_tasks)} 条补充联网检索..."
            )
            fetched_results = await asyncio.gather(*pending_tasks)
            for idx, result in zip(pending_indexes, fetched_results):
                search_results[idx] = result
        elif api_bg_count:
            logger.info(f"[内容服务] {source_name} 已使用接口自带摘要/正文，跳过联网检索。")
        else:
            logger.info(f"[内容服务] 联网搜索功能已关闭，且接口未提供可用摘要。")

        search_results = [
            result if result is not None else (item.get("title", ""), "")
            for item, result in zip(selected_to_search, search_results)
        ]
        
        raw_share_count = self.news_conf.get("news_share_count", "1-2")
        try:
            if isinstance(raw_share_count, int):
                share_count = raw_share_count
            elif isinstance(raw_share_count, str):
                if "-" in raw_share_count:
                    min_c, max_c = map(int, raw_share_count.split("-"))
                    share_count = random.randint(min_c, max_c)
                else:
                    share_count = int(raw_share_count)
            else:
                share_count = 2
        except (TypeError, ValueError):
            share_count = 2

        news_text = f"【{source_name}】\n\n"
        for idx, (item, (s_title, s_bg)) in enumerate(zip(selected_to_search, search_results), 1):
            hot = item.get("hot", "")
            title = item.get("title", "")
            hot_display = ""
            if hot:
                hot_str = str(hot)
                if hot_str.isdigit() and int(hot_str) > 10000:
                    hot_display = f" {int(hot_str) / 10000:.1f}万"
                else:
                    hot_display = f" {hot_str}"
            
            bg_str = (
                f"\n  -> [真实背景与人物]: {s_bg}"
                if s_bg
                else "\n  -> [真实背景]: 无，请仅就标题做字面简评，不要擅自编造。"
            )
            news_text += f"{idx}. 标题：【{title}】{hot_display}{bg_str}\n\n"
        
        user_info_prompt = ""
        if not is_group and not is_qzone:
            user_info_prompt = self._build_user_prompt(call_name, detect_name)

        common_rules = build_common_content_rules(
            is_group=is_group,
            is_qzone=is_qzone,
            date_text=ctx["date_str"],
            time_text=ctx["time_str"],
            period_label=ctx["period_label"],
            action="分享新闻",
            allow_detail=allow_detail,
        )
        scene_rule = build_scene_consistency_rule("分享新闻")
        dynamics_prompt = self._build_recent_dynamics_prompt(ctx.get('recent_dynamics'))

        target_str = "QQ空间" if is_qzone else ('群聊' if is_group else '私聊')

        prompt = f"""
【当前时间】{ctx['date_str']} {ctx['time_str']} ({ctx['period_label']})
你看到了今天的{source_name}，想选择{share_count}条和{target_str}分享。

{user_info_prompt}
{ctx.get('self_identity_hint', '')}
{ctx['life_hint']}
{ctx['chat_hint']}
{dynamics_prompt}
{source_name}（含 API 摘要/检索真相）：
{news_text}

{common_rules}

【新闻资料边界】
- 请先阅读新闻列表；如果条目附带 [真实背景与人物]，优先依据其中的人名、数据和事件信息。
- 背景没有明确给出的细节用概括表达，不要从记忆、关系档案或想象里补人物、地点和经过。

{scene_rule}

【开头方式】（必须自然提到平台"{source_name}"）
- "刚在{source_name}看到..."
- "翻到{source_name}的时候注意到..."
- "今天{source_name}这条..."
- 其他自然的方式
{'【组织方式】' if share_count > 1 else ''}
{f'''- 可以逐条分享：每条新闻+你的看法
- 也可以串联：找出多条新闻的共同点''' if share_count > 1 else ''}

要求：
1. 以你的人设性格说话，真实自然
2. 选择{share_count}条你最感兴趣的热搜
3. 观点真诚，结合新闻下方的真实背景表达看法，不要只复述标题。
4. 避免过度情绪化或标题党式表达
5. {'群聊中简洁有重点' if is_group else '私聊可以详细展开想法，并结合你当下的状态'}
6. 用【】标注热搜标题
7. {'字数：120-150字' if is_group else '字数：150-200字'}
8. 直接输出分享内容

直接输出："""

        res = await self._call_llm(prompt=prompt, system_prompt=ctx['persona'], timeout=60, target_umo=ctx.get('target_id'))
        
        if res:
            return f"{res}"
        return None

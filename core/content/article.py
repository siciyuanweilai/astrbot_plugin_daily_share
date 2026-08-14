import asyncio
import random
from collections.abc import Sequence
from typing import Any

from astrbot.api import logger

from ..config import NEWS_SOURCE_MAP
from ..database.keys import QZONE_TARGET_ID
from ..prompt import build_common_content_rules
from .contentbase import ContentComponent
from .evidence import strip_news_reference_links


class ContentNewsService(ContentComponent):
    @staticmethod
    def _news_api_background(item: dict) -> str:
        title = str(item.get("title", "") or "").strip()
        desc = str(item.get("description", "") or "").strip()
        if not desc or desc == title or len(desc) < 20:
            return ""
        return desc

    async def _collect_news_backgrounds(
        self,
        selected_items: Sequence[dict],
        *,
        source_name: str,
        enable_web_search: bool,
        target_umo: str,
    ) -> list[tuple[Any, str]]:
        """优先使用接口摘要；缺少摘要时再补联网检索。"""
        search_results: list[tuple[Any, str] | None] = [None] * len(selected_items)
        pending_tasks = []
        pending_indexes = []
        api_bg_count = 0

        for idx, item in enumerate(selected_items):
            title = item.get("title", "")
            api_bg = self._news_api_background(item)
            if api_bg:
                search_results[idx] = (title, api_bg)
                api_bg_count += 1
            elif enable_web_search:
                pending_indexes.append(idx)
                pending_tasks.append(
                    self.daily_life_bridge.search_evidence(
                        title,
                        category="news",
                        target_umo=target_umo,
                    )
                )
            else:
                search_results[idx] = (title, "")

        if pending_tasks:
            logger.info(
                f"[内容服务] {source_name} 有 {api_bg_count} 条使用接口摘要，"
                f"{len(pending_tasks)} 条补充联网检索..."
            )
            fetched_results = await asyncio.gather(*pending_tasks)
            for idx, payload in zip(pending_indexes, fetched_results):
                title = selected_items[idx].get("title", "")
                content = (
                    strip_news_reference_links(payload.get("content"))[:2000]
                    if payload.get("status") == "ok"
                    else ""
                )
                search_results[idx] = (title, content)
        elif api_bg_count:
            logger.info(
                f"[内容服务] {source_name} 已使用接口自带摘要/正文，跳过联网检索。"
            )
        else:
            logger.info("[内容服务] 联网搜索功能已关闭，且接口未提供可用摘要。")

        return [
            result if result is not None else (item.get("title", ""), "")
            for item, result in zip(selected_items, search_results)
        ]

    @staticmethod
    def _resolve_news_share_count(raw_share_count: Any) -> int:
        try:
            if isinstance(raw_share_count, int):
                return raw_share_count
            if isinstance(raw_share_count, str):
                if "-" in raw_share_count:
                    min_c, max_c = map(int, raw_share_count.split("-"))
                    return random.randint(min_c, max_c)
                return int(raw_share_count)
        except (TypeError, ValueError):
            pass
        return 2

    @staticmethod
    def _format_news_hot(hot: Any) -> str:
        if not hot:
            return ""
        hot_str = str(hot)
        if hot_str.isdigit() and int(hot_str) > 10000:
            return f" {int(hot_str) / 10000:.1f}万"
        return f" {hot_str}"

    def _build_news_source_text(
        self,
        source_name: str,
        selected_items: Sequence[dict],
        search_results: Sequence[tuple[Any, str]],
    ) -> str:
        lines = [f"【{source_name}】", ""]
        for idx, (item, (_s_title, background)) in enumerate(
            zip(selected_items, search_results), 1
        ):
            title = item.get("title", "")
            hot_display = self._format_news_hot(item.get("hot", ""))
            bg_str = (
                f"\n  -> [真实背景与人物]: {background}"
                if background
                else "\n  -> [真实背景]: 无，请仅就标题做字面简评，不要擅自编造。"
            )
            lines.append(f"{idx}. 标题：【{title}】{hot_display}{bg_str}")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _news_target_label(is_group: bool, is_qzone: bool) -> str:
        if is_qzone:
            return "QQ空间"
        return "群聊" if is_group else "私聊"

    def _build_news_prompt(
        self,
        *,
        ctx: dict,
        source_name: str,
        share_count: int,
        target_label: str,
        user_info_prompt: str,
        news_text: str,
        common_rules: str,
        dynamics_prompt: str,
        is_group: bool,
    ) -> str:
        organization_title = "【组织方式】" if share_count > 1 else ""
        organization_rules = (
            "- 可以逐条分享：每条新闻+你的看法\n- 也可以串联：找出多条新闻的共同点"
            if share_count > 1
            else ""
        )
        chat_detail_rule = (
            "群聊中简洁有重点"
            if is_group
            else "私聊可以详细展开想法，并结合你当下的状态"
        )
        length_rule = "字数：120-150字" if is_group else "字数：150-200字"

        return f"""
【当前时间】{ctx["date_str"]} {ctx["time_str"]} ({ctx["period_label"]})
你看到了今天的{source_name}，想选择{share_count}条和{target_label}分享。

{user_info_prompt}
{ctx["life_hint"]}
{ctx["structured_history_hint"]}
{dynamics_prompt}
{source_name}（含 API 摘要/检索真相）：
{news_text}

{common_rules}
{ctx.get("output_format_hint", "")}

【新闻资料边界】
- 请先阅读新闻列表；如果条目附带 [真实背景与人物]，优先依据其中的人名、数据和事件信息。
- 背景没有明确给出的细节用概括表达，不要从记忆、关系档案或想象里补人物、地点和经过。

【开头方式】（必须自然提到平台"{source_name}"）
- "刚在{source_name}看到..."
- "翻到{source_name}的时候注意到..."
- "今天{source_name}这条..."
- 其他自然的方式
{organization_title}
{organization_rules}

要求：
1. 以你的人设性格说话，真实自然
2. 选择{share_count}条你最感兴趣的热搜
3. 观点真诚，结合新闻下方的真实背景表达看法，不要只复述标题。
4. 避免过度情绪化或标题党式表达
5. {chat_detail_rule}
6. 用【】标注热搜标题
7. {length_rule}
8. 不要输出网址、Markdown 链接或检索引用编号；新闻链接仅在用户明确索要时由专用工具发送
9. 直接输出分享内容

直接输出："""

    async def _gen_news(self, news_data: tuple[list, str] | None, ctx: dict):
        """生成新闻分享，带基于联网搜索的自动核查功能。"""
        if not news_data:
            logger.warning("[内容服务] 未获取到新闻数据，取消分享")
            return None

        is_group = ctx["is_group"]
        is_qzone = ctx.get("target_id") == QZONE_TARGET_ID
        call_name = ctx.get("nickname", "")
        detect_name = ctx.get("detect_name", "")

        allow_detail = self.context_conf.get("group_share_schedule", False)
        enable_web_search = self.news_conf.get("enable_web_search", True)

        news_list, source_key = news_data
        source_config = NEWS_SOURCE_MAP.get(source_key, {"name": "热搜", "icon": "📰"})
        source_name = source_config["name"]

        items_limit = self.news_conf.get("news_items_count", 5)
        selected_to_search = news_list[:items_limit]

        search_results = await self._collect_news_backgrounds(
            selected_to_search,
            source_name=source_name,
            enable_web_search=enable_web_search,
            target_umo=ctx.get("target_id", ""),
        )
        share_count = self._resolve_news_share_count(
            self.news_conf.get("news_share_count", "1-2")
        )
        news_text = self._build_news_source_text(
            source_name, selected_to_search, search_results
        )

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
            action="分享新闻",
            allow_detail=allow_detail,
        )
        dynamics_prompt = self._build_recent_dynamics_prompt(ctx.get("recent_dynamics"))

        prompt = self._build_news_prompt(
            ctx=ctx,
            source_name=source_name,
            share_count=share_count,
            target_label=self._news_target_label(is_group, is_qzone),
            user_info_prompt=user_info_prompt,
            news_text=news_text,
            common_rules=common_rules,
            dynamics_prompt=dynamics_prompt,
            is_group=is_group,
        )

        res = await self._call_llm(
            prompt=prompt,
            system_prompt=ctx["system_prompt"],
            timeout=60,
            target_umo=ctx.get("target_id"),
        )

        if res:
            return strip_news_reference_links(res)
        return None

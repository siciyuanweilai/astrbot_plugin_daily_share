import aiohttp
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

from astrbot.api import logger

from ..config import TimePeriod
from ..prompt import build_private_target_prompt


class ContentSupportMixin:
    """内容生成支撑能力。"""

    async def _call_llm(self, *args, target_umo: str = None, **kwargs):
        if target_umo:
            kwargs["umo"] = target_umo
            try:
                return await self.call_llm(*args, **kwargs)
            except TypeError as e:
                if "umo" not in str(e):
                    raise
                kwargs.pop("umo", None)
        return await self.call_llm(*args, **kwargs)

    def _parse_category_config(self, data: Any) -> Dict[str, List[str]]:
        """解析内容库配置：WebUI 使用 List[str]，内置默认值使用 Dict[str, str]。"""
        result = {}
        if isinstance(data, dict):
            for name, tags_data in data.items():
                name = str(name or "").strip()
                tags = self._parse_category_tags(tags_data)
                if name and tags:
                    result[name] = tags
            return result

        if isinstance(data, list):
            for item in data:
                if isinstance(item, str):
                    item = item.replace("：", ":")
                    if ":" in item:
                        name, tags_str = item.split(":", 1)
                        name = name.strip()
                        tags = self._parse_category_tags(tags_str)
                        if name and tags:
                            result[name] = tags
        return result

    def _parse_category_tags(self, tags_data: Any) -> List[str]:
        if isinstance(tags_data, list):
            raw_tags = tags_data
        else:
            raw_tags = str(tags_data or "").replace("，", ",").split(",")
        return [str(tag).strip() for tag in raw_tags if str(tag).strip()]

    def _get_period_label(self, period: TimePeriod) -> str:
        labels = {
            TimePeriod.DAWN: "凌晨", 
            TimePeriod.MORNING: "早晨",
            TimePeriod.FORENOON: "上午",
            TimePeriod.NOON: "中午",
            TimePeriod.AFTERNOON: "下午", 
            TimePeriod.EVENING: "傍晚",
            TimePeriod.NIGHT: "夜晚",      
            TimePeriod.LATE_NIGHT: "深夜", 
        }
        return labels.get(period, "现在")

    async def _get_persona_info(self) -> dict:
        """获取人设详细信息（包括系统提示词和对用户的称呼）"""
        info = {"prompt": "", "bot_name": "", "user_name": ""}
        try:
            persona_id = self.llm_conf.get("persona_id", "")
            if persona_id:
                persona = await self.context.persona_manager.get_persona(persona_id)
                if persona:
                    info["prompt"] = getattr(persona, "system_prompt", "")
                    info["bot_name"] = getattr(persona, "bot_name", "")
                    info["user_name"] = getattr(persona, "user_name", "")
                    return info

            personality = await self.context.persona_manager.get_default_persona_v3()
            if personality:
                info["prompt"] = personality.get("prompt", "")
                info["bot_name"] = personality.get("bot_name", "")
                info["user_name"] = personality.get("user_name", "")
            return info
        except Exception as e:
            logger.error(f"[内容服务] 获取人设失败: {e}")
            return info

    # ==================== 生成逻辑 ====================

    def _build_user_prompt(self, call_name: str, detect_name: str = "") -> str:
        """构建当前私聊对象的通用关系提示。"""
        return build_private_target_prompt(call_name, detect_name)

    def _build_recent_dynamics_prompt(self, recent_dynamics: str) -> str:
        if not str(recent_dynamics or "").strip():
            return ""
        return (
            f"\n【你最近发过的动态回顾】\n{recent_dynamics}\n"
            "(注：请保持人设连贯，可以偶尔自然呼应之前的心情，但不要重复发过的内容)"
        )

    async def _fetch_web_search(self, keyword: str, search_type: str = "news") -> Tuple[str, str]:
        """调用 AstrBot 内置搜索引擎（支持 Tavily / Brave），支持多密钥轮询与失败重试。"""
        provider = "tavily"
        search_keys = []

        def add_keys(keys):
            if isinstance(keys, list):
                search_keys.extend(str(key).strip() for key in keys if str(key).strip())
            elif isinstance(keys, str) and keys.strip():
                search_keys.append(keys.strip())

        try:
            get_config = getattr(self.context, "get_config", None)
            config_data = get_config() if callable(get_config) else getattr(self.context, "_config", None)
            provider_settings = config_data.get("provider_settings", {}) if hasattr(config_data, "get") else {}
            provider = str(provider_settings.get("websearch_provider", provider)).lower()
            if provider == "brave":
                add_keys(provider_settings.get("websearch_brave_key", []))
            else:
                add_keys(provider_settings.get("websearch_tavily_key", []))
        except Exception as e:
            logger.debug(f"[内容服务] 从 AstrBot 配置读取联网搜索设置失败: {e}")

        # 去重并保持顺序
        search_keys = list(dict.fromkeys(search_keys))

        if not search_keys:
            return keyword, ""

        # 根据请求类型动态调整搜索词
        if search_type == "news":
            current_date = datetime.now().strftime("%Y年%m月%d日")
            search_query = f"{keyword} {current_date} 最新进展 事件核心内容 人物"
        elif search_type == "knowledge":
            search_query = f"什么是 {keyword} ？ 科普 原理 详细解释"
        elif search_type == "rec":
            search_query = f"{keyword} 作品简介 评价 核心亮点"
        else:
            search_query = keyword
            
        async with aiohttp.ClientSession() as session:
            for attempt, current_key in enumerate(search_keys):
                if provider == "brave":
                    url = "https://api.search.brave.com/res/v1/web/search"
                    headers = {
                        "Accept": "application/json",
                        "X-Subscription-Token": current_key
                    }
                    params = {
                        "q": search_query,
                        "count": "3" # 限制条数，加速处理
                    }
                    try:
                        async with session.get(url, headers=headers, params=params, timeout=10) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                web_data = data.get("web") or {}
                                results = web_data.get("results") or []
                                
                                if results:
                                    combined_content = ""
                                    for r in results:
                                        # 安全处理可能为空的描述字段
                                        desc = r.get("description")
                                        if desc:
                                            combined_content += str(desc) + " "
                                        
                                        # 安全处理可能为空的额外摘要字段
                                        extra = r.get("extra_snippets")
                                        if isinstance(extra, list):
                                            combined_content += " ".join(str(e) for e in extra if e) + " "
                                    
                                    clean_content = re.sub(r'\s+', ' ', combined_content).strip()
                                    return keyword, clean_content[:350]
                                    
                                return keyword, ""
                            else:
                                error_text = await resp.text()
                                logger.warning(f"[Brave 搜索] 第 {attempt+1} 个搜索密钥失败，即将尝试下一个。")
                                continue 
                    except Exception as e:
                        logger.warning(f"[Brave 搜索] 第 {attempt+1} 个搜索密钥请求异常: {e}，即将尝试下一个。")
                        continue
                else:
                    url = "https://api.tavily.com/search"
                    headers = {"Content-Type": "application/json"}
                    payload = {
                        "api_key": current_key,
                        "query": search_query,
                        "search_depth": "basic",
                        "include_answer": True, 
                        "max_results": 2
                    }

                    try:
                        async with session.post(url, headers=headers, json=payload, timeout=10) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                
                                # 1. 如果有官方生成的精炼回答，优先使用
                                answer = data.get("answer") or ""
                                answer = answer.strip()
                                if answer:
                                    return keyword, answer
                                    
                                # 2. 如果没有精炼回答，退而求其次拼接正文内容
                                results = data.get("results") or []
                                if results:
                                    combined_content = " ".join([str(r.get("content", "")) for r in results])
                                    clean_content = re.sub(r'\s+', ' ', combined_content).strip()
                                    return keyword, clean_content[:350]
                                
                                return keyword, ""
                                
                            else:
                                error_text = await resp.text()
                                logger.warning(f"[Tavily 搜索] 第 {attempt+1} 个搜索密钥失败，即将尝试下一个。")
                                continue 
                                
                    except Exception as e:
                        logger.warning(f"[Tavily 搜索] 第 {attempt+1} 个搜索密钥请求异常: {e}，即将尝试下一个。")
                        continue
        
        # 如果循环结束还没有返回，说明所有密钥都失败了
        provider_label = {"brave": "Brave 搜索", "tavily": "Tavily 搜索"}.get(provider, f"{provider} 搜索")
        logger.error(f"[{provider_label}异常] {keyword}: 所有配置的搜索密钥均已失效或超额。")
        return keyword, ""


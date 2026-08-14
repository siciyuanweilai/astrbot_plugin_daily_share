import asyncio
import json
from typing import TYPE_CHECKING, Any

import aiohttp

from astrbot.api import logger

from ..config import NEWS_SOURCE_MAP


class NewsApiService:
    """新闻外部接口请求。"""

    if TYPE_CHECKING:
        conf: dict

        async def http(self) -> aiohttp.ClientSession: ...

        def _loads_json_payload(self, text: str) -> Any: ...

        def _parse_news_payload(
            self, text: str, limit: int | None = None
        ) -> tuple[Any, list[dict] | None]: ...

    async def shorten_url(self, original_url: str) -> str | None:
        """使用柠柚短链接接口把原文链接转成短链。失败时返回空值。"""
        if not self.conf.get("enable_news_api", True):
            return None

        key = self.conf.get("nycnm_api_key", "").strip()
        original_url = str(original_url or "").strip()
        if not key or not original_url:
            return None

        params = {
            "url": original_url,
            "format": "json",
            "apikey": key,
        }
        try:
            session = await self.http()
            async with session.get(
                "https://api.nycnm.cn/api/v2/duan",
                params=params,
                timeout=10,
            ) as resp:
                if resp.status != 200:
                    logger.debug(f"[短链接] 生成失败，状态码: {resp.status}")
                    return None
                raw_text = await resp.text()
                data = await asyncio.to_thread(self._loads_json_payload, raw_text)

            if not isinstance(data, dict):
                return None

            raw_payload = data.get("data")
            payload = raw_payload if isinstance(raw_payload, dict) else {}
            short_url = str(payload.get("short_url") or "").strip()
            if not short_url:
                return None

            return short_url
        except asyncio.TimeoutError:
            logger.debug("[短链接] 生成超时")
        except Exception as e:
            logger.debug(f"[短链接] 生成失败: {e}")
        return None

    async def _fetch_news(
        self, source: str, key: str, limit: int | None = None
    ) -> list[dict] | None:
        """发送新闻接口请求。"""
        if source not in NEWS_SOURCE_MAP:
            return None

        source_name = NEWS_SOURCE_MAP[source]["name"]
        url = NEWS_SOURCE_MAP[source]["url"]
        extra_params = NEWS_SOURCE_MAP[source].get("extra_params", "")
        full_url = f"{url}?format=json&apikey={key}{extra_params}"

        timeout = self.conf.get("news_api_timeout", 30)

        logger.info(f"[新闻] 获取新闻: {source_name}")
        logger.debug(f"[新闻] 接口请求地址已生成，密钥参数已隐藏: {url}{extra_params}")

        try:
            session = await self.http()
            async with session.get(full_url, timeout=timeout) as resp:
                if resp.status != 200:
                    logger.warning(f"[新闻] 接口返回状态码: {resp.status}")
                    if resp.status in (401, 403):
                        logger.error("[新闻] 接口密钥无效或已过期！")
                    return None

                raw_text = await resp.text()
                data, parsed = await asyncio.to_thread(
                    self._parse_news_payload, raw_text, limit
                )

                if parsed:
                    logger.info(f"[新闻] 成功获取 {len(parsed)} 条{source_name}")
                    return parsed
                logger.warning("[新闻] 未能解析到新闻内容")
                logger.debug(f"[新闻] 原始数据: {str(data)[:300]}...")
                return None

        except asyncio.TimeoutError:
            logger.error(f"[新闻] 请求超时: {source_name}")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"[新闻] 网络请求失败: {e}")
            return None
        except Exception as e:
            logger.error(f"[新闻] 解析新闻失败: {e}")
            return None

    async def get_baike_info(self, keyword: str) -> str | None:
        """通过柠柚接口获取百科词条简介。"""
        if not self.conf.get("enable_news_api", True):
            return None
        key = self.conf.get("nycnm_api_key", "").strip()
        if not key:
            return None

        # 清理关键词
        keyword = (
            keyword.replace("《", "")
            .replace("》", "")
            .replace("【", "")
            .replace("】", "")
            .strip()
        )
        if not keyword:
            return None

        url = "https://api.nycnm.cn/api/v2/baike"
        params = {"word": keyword, "format": "json", "apikey": key}

        logger.debug(f"[百科] 查询: {keyword}")

        try:
            session = await self.http()
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status != 200:
                    return None

                try:
                    raw_text = await resp.text()
                    data = await asyncio.to_thread(self._loads_json_payload, raw_text)
                except Exception as e:
                    logger.debug(f"[百科] 结构化数据解析失败: {e}")
                    return None

                    # 解析接口返回结构
                return self._baike_response_text(data, keyword)

            return None
        except Exception as e:
            logger.warning(f"[百科] 查询失败: {e}")
            return None

    @staticmethod
    def _baike_response_text(data: dict, keyword: str) -> str | None:
        success = data.get("success")
        if success is False or (str(data.get("code")) != "200" and success is not True):
            return None
        info = data.get("data")
        if isinstance(info, str):
            return info
        if not isinstance(info, dict):
            return None
        parts = []
        if info.get("description"):
            parts.append(f"描述：{info['description']}")
        if info.get("abstract"):
            abstract = info["abstract"].replace("\n", " ").strip()
            parts.append(f"摘要：{abstract}")
        if not parts:
            return None
        return f"标题：【{info.get('title', keyword)}】 " + " | ".join(parts)

    async def get_ai_news_json(self) -> dict | None:
        """获取每日 AI 资讯结构化数据。"""
        key = self.conf.get("nycnm_api_key", "").strip()
        if not key:
            logger.error("[新闻] 未配置柠柚接口密钥")
            return None

        url = f"https://api.nycnm.cn/api/v2/aizixun?format=json&apikey={key}"
        try:
            session = await self.http()
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    raw_text = await resp.text()
                    data = await asyncio.to_thread(json.loads, raw_text)

                    if data and isinstance(data, dict):
                        if "news" in data and not data.get("news"):
                            return None

                        if "code" in data and str(data.get("code")) not in ["200", "1"]:
                            return None

                    return data
            return None
        except Exception as e:
            logger.warning(f"[新闻] 获取 AI 资讯失败: {e}")
            return None

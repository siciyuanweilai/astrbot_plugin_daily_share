import random

import aiohttp
from astrbot.api import logger

from ..config import NEWS_SOURCE_MAP
from .client import NewsApiService
from .decode import NewsParserService
from .sources import NewsSourceService


class NewsService:
    def __init__(self, config: dict):
        self.config = config
        self.conf = self.config.get("news_conf", {})
        self._session: aiohttp.ClientSession | None = None
        self.sources = NewsSourceService(self)
        self.parser = NewsParserService(self)
        self.api = NewsApiService(self)

    async def http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def get_hot_news(
        self,
        specific_source: str | None = None,
        limit: int | None = None,
        allow_fallback: bool = True,
    ) -> tuple | None:
        """获取热搜 (包含降级重试逻辑)"""
        # 检查开关和密钥
        if not self.conf.get("enable_news_api", True):
            return None

        key = self.conf.get("nycnm_api_key", "").strip()
        if not key:
            logger.error("[新闻] 未配置柠柚接口密钥！")
            return None

        # 尝试主要源
        if specific_source and specific_source in NEWS_SOURCE_MAP:
            pri_source = specific_source
        else:
            pri_source = self.select_news_source()

        res = await self._fetch_news(pri_source, key, limit=limit)
        if res:
            return (res, pri_source)

        if not allow_fallback:
            logger.warning(
                f"[新闻] 指定新闻源 {pri_source} 获取失败，已按要求跳过备用源"
            )
            return None

        logger.warning(f"[新闻] 主要源 {pri_source} 失败，尝试备用源...")

        mode = self.conf.get("news_random_mode", "config")

        # 确定备选池范围
        if mode in ["config", "time_based"]:
            configured = self.conf.get("news_random_sources", ["zhihu", "weibo"])
            pool = self._valid_sources(configured)
        else:
            # 从所有可用源中找
            pool = list(NEWS_SOURCE_MAP.keys())

        # 排除刚才失败的源
        fallback_pool = [s for s in pool if s != pri_source]

        if not fallback_pool:
            logger.warning("[新闻] 没有可用的备用源")
            return None

        back_source = random.choice(fallback_pool)
        logger.info(f"[新闻] 尝试备用源: {NEWS_SOURCE_MAP[back_source]['name']}")

        res = await self._fetch_news(back_source, key, limit=limit)
        if res:
            logger.info("[新闻] 备用源成功")
            return (res, back_source)

        logger.warning("[新闻] 所有新闻源均失败")
        return None

    ITEM_CONTAINER_KEYS = NewsParserService.ITEM_CONTAINER_KEYS

    NESTED_ITEM_CONTAINER_KEYS = NewsParserService.NESTED_ITEM_CONTAINER_KEYS

    TITLE_KEYS = NewsParserService.TITLE_KEYS

    HOT_KEYS = NewsParserService.HOT_KEYS

    URL_KEYS = NewsParserService.URL_KEYS

    DESCRIPTION_KEYS = NewsParserService.DESCRIPTION_KEYS

    @staticmethod
    def _valid_sources(value):
        return NewsSourceService._valid_sources(value)

    def _get_current_period(self):
        return self.sources._get_current_period()

    def select_news_source(self, excluded_source=None):
        """选择主新闻源"""
        return self.sources.select_news_source(excluded_source)

    def _select_by_time(self, excluded_source=None):
        """基于时间的智能选择"""
        return self.sources._select_by_time(excluded_source)

    def get_hot_news_image_url(self, source=None):
        """获取热搜图片链接"""
        return self.sources.get_hot_news_image_url(source)

    def get_60s_image_url(self):
        """获取每日 60 秒读世界图片链接"""
        return self.sources.get_60s_image_url()

    def get_ai_news_image_url(self):
        """获取每日 AI 资讯图片链接。"""
        return self.sources.get_ai_news_image_url()

    def _loads_json_payload(self, text):
        """从被状态文本或调试输出包裹的响应中提取新闻结构化数据。"""
        return self.parser._loads_json_payload(text)

    def _parse_news_payload(self, text, limit=None):
        """在线程中解析并规范化一次新闻响应。"""
        return self.parser._parse_news_payload(text, limit)

    @staticmethod
    def _is_tencent_style_dict(value):
        return NewsParserService._is_tencent_style_dict(value)

    def _has_parseable_news_items(self, data):
        return self.parser._has_parseable_news_items(data)

    def _extract_news_items(self, data):
        return self.parser._extract_news_items(data)

    @staticmethod
    def _first_non_empty(item, keys):
        return NewsParserService._first_non_empty(item, keys)

    def _parse_response(self, data, limit=None):
        """
        解析响应数据
        支持多层级结构化数据和多种上游字段名。
        支持腾讯新闻这种字典结构的列表 {"Top_1": {...}, "Top_2": {...}}
        """
        return self.parser._parse_response(data, limit)

    def _news_item_limit(self, limit):
        return self.parser._news_item_limit(limit)

    @staticmethod
    def _clean_news_text(value, max_len=800):
        return NewsParserService._clean_news_text(value, max_len)

    def _parse_news_item(self, item):
        return self.parser._parse_news_item(item)

    async def shorten_url(self, original_url):
        """使用柠柚短链接接口把原文链接转成短链。失败时返回空值。"""
        return await self.api.shorten_url(original_url)

    async def _fetch_news(self, source, key, limit=None):
        """发送新闻接口请求。"""
        return await self.api._fetch_news(source, key, limit)

    async def get_baike_info(self, keyword):
        """通过柠柚接口获取百科词条简介。"""
        return await self.api.get_baike_info(keyword)

    @staticmethod
    def _baike_response_text(data, keyword):
        return NewsApiService._baike_response_text(data, keyword)

    async def get_ai_news_json(self):
        """获取每日 AI 资讯结构化数据。"""
        return await self.api.get_ai_news_json()

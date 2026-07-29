from __future__ import annotations


class ContentComponent:
    """内容组件访问统一配置与协作组件的显式契约。"""

    def __init__(self, service):
        self.service = service

    @property
    def config(self):
        return self.service.config

    @property
    def call_llm(self):
        return self.service.call_llm

    @property
    def context(self):
        return self.service.context

    @property
    def db(self):
        return self.service.db

    @property
    def news_service(self):
        return self.service.news_service

    @property
    def daily_life_bridge(self):
        return self.service.daily_life_bridge

    @property
    def content_lib_conf(self):
        return self.service.content_lib_conf

    @property
    def knowledge_cats(self):
        return self.service.knowledge_cats

    @property
    def rec_cats(self):
        return self.service.rec_cats

    @property
    def dedup_days(self):
        return self.service.dedup_days

    @property
    def basic_conf(self):
        return self.service.basic_conf

    @property
    def news_conf(self):
        return self.service.news_conf

    @property
    def context_conf(self):
        return self.service.context_conf

    @property
    def qzone_conf(self):
        return self.service.qzone_conf

    async def _call_llm(self, *args, **kwargs):
        return await self.service.support._call_llm(*args, **kwargs)

    def _build_user_prompt(self, *args, **kwargs):
        return self.service.support._build_user_prompt(*args, **kwargs)

    def _build_recent_dynamics_prompt(self, *args, **kwargs):
        return self.service.support._build_recent_dynamics_prompt(*args, **kwargs)

    async def _agent_brainstorm_topic(self, *args, **kwargs):
        return await self.service.topic._agent_brainstorm_topic(*args, **kwargs)

    async def _fetch_content_reference(self, *args, **kwargs):
        return await self.service.recommendation._fetch_content_reference(
            *args, **kwargs
        )


__all__ = ["ContentComponent"]

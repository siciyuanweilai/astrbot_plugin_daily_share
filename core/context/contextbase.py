from __future__ import annotations


class ContextComponent:
    """上下文组件共享运行状态与协作服务的显式契约。"""

    def __init__(self, service):
        self.service = service

    @property
    def context(self):
        return self.service.context

    @property
    def life_conf(self):
        return self.service.life_conf

    @property
    def history_conf(self):
        return self.service.history_conf

    @property
    def memory_conf(self):
        return self.service.memory_conf

    @property
    def image_conf(self):
        return self.service.image_conf

    @property
    def tts_conf(self):
        return self.service.tts_conf

    def is_group_chat(self, target_umo: str) -> bool:
        return self.service.is_group_chat(target_umo)

    def parse_umo(self, target_umo: str):
        return self.service.parse_umo(target_umo)

    def is_onebot_platform(self, adapter_id: str) -> bool:
        return self.service.is_onebot_platform(adapter_id)

    def is_onebot_event(self, event) -> bool:
        return self.service.is_onebot_event(event)

    def is_weixin_platform(self, target_umo: str) -> bool:
        return self.service.is_weixin_platform(target_umo)

    def _get_history_max_count(self, *args, **kwargs):
        return self.service._get_history_max_count(*args, **kwargs)

    def get_onebot_bot(self, *args, **kwargs):
        return self.service.get_onebot_bot(*args, **kwargs)

    async def call_onebot_action(self, *args, **kwargs):
        return await self.service.call_onebot_action(*args, **kwargs)

    async def _conversation_history_list(self, conversation):
        return await self.service.memory._conversation_history_list(conversation)

    def _analyze_group_chat(self, *args, **kwargs):
        return self.service.analysis._analyze_group_chat(*args, **kwargs)

    def _normalize_conversation_history_item(self, *args, **kwargs):
        return self.service.normalize._normalize_conversation_history_item(
            *args, **kwargs
        )

    def _get_platform_history_user_ids(self, *args, **kwargs):
        return self.service.normalize._get_platform_history_user_ids(*args, **kwargs)

    def _normalize_platform_history_item(self, *args, **kwargs):
        return self.service.normalize._normalize_platform_history_item(*args, **kwargs)

    def _mark_daily_share_sources(self, *args, **kwargs):
        return self.service.normalize._mark_daily_share_sources(*args, **kwargs)

    def _extract_history_payload(self, *args, **kwargs):
        return self.service.normalize._extract_history_payload(*args, **kwargs)

    async def _get_conversation_history_data(self, *args, **kwargs):
        return await self.service.conversation._get_conversation_history_data(
            *args, **kwargs
        )

    async def _get_astrbot_saved_history_data(self, *args, **kwargs):
        return await self.service.platform_history._get_astrbot_saved_history_data(
            *args, **kwargs
        )

    def _compact_life_text(self, *args, **kwargs):
        return self.service.life_memory._compact_life_text(*args, **kwargs)

    def _build_people_identity_rule(self, *args, **kwargs):
        return self.service.life_memory._build_people_identity_rule(*args, **kwargs)

    def _format_relationships(self, *args, **kwargs):
        return self.service.life_memory._format_relationships(*args, **kwargs)

    def _format_chat_summaries(self, *args, **kwargs):
        return self.service.life_memory._format_chat_summaries(*args, **kwargs)

    def _format_places(self, *args, **kwargs):
        return self.service.life_memory._format_places(*args, **kwargs)

    def _format_events(self, *args, **kwargs):
        return self.service.life_memory._format_events(*args, **kwargs)

    def _format_commitments(self, *args, **kwargs):
        return self.service.life_memory._format_commitments(*args, **kwargs)

    def _parse_life_data(self, *args, **kwargs):
        return self.service.life_parse._parse_life_data(*args, **kwargs)


__all__ = ["ContextComponent"]

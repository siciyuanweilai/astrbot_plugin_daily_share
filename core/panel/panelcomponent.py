from __future__ import annotations


class RuntimeField:
    """显式声明组件需要从面板运行时读写的字段。"""

    def __init__(self, name: str) -> None:
        self.name = name

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        return getattr(instance.runtime, self.name)

    def __set__(self, instance, value) -> None:
        setattr(instance.runtime, self.name, value)


class PanelComponent:
    """只接受明确面板运行时的仪表盘组件基类。"""

    action_routes = RuntimeField("action_routes")
    activity = RuntimeField("activity")
    apply = RuntimeField("apply")
    config_routes = RuntimeField("config_routes")
    events = RuntimeField("events")
    fields = RuntimeField("fields")
    general_apply = RuntimeField("general_apply")
    jobs = RuntimeField("jobs")
    labels = RuntimeField("labels")
    media_files = RuntimeField("media_files")
    media_kind = RuntimeField("media_kind")
    media_page = RuntimeField("media_page")
    media_preview = RuntimeField("media_preview")
    meta = RuntimeField("meta")
    payload = RuntimeField("payload")
    query_routes = RuntimeField("query_routes")
    qzone_actions = RuntimeField("qzone_actions")
    qzone_apply = RuntimeField("qzone_apply")
    qzone_entry = RuntimeField("qzone_entry")
    qzone_feed = RuntimeField("qzone_feed")
    qzone_publish = RuntimeField("qzone_publish")
    qzone_relations = RuntimeField("qzone_relations")
    qzone_tools = RuntimeField("qzone_tools")
    qzone_upload = RuntimeField("qzone_upload")
    refresh = RuntimeField("refresh")
    retry_routes = RuntimeField("retry_routes")
    schedule_apply = RuntimeField("schedule_apply")
    sections = RuntimeField("sections")
    server = RuntimeField("server")
    status_routes = RuntimeField("status_routes")
    target_routes = RuntimeField("target_routes")
    targets = RuntimeField("targets")
    validation = RuntimeField("validation")

    plugin = RuntimeField("plugin")
    context = RuntimeField("context")
    config = RuntimeField("config")
    scheduler = RuntimeField("scheduler")
    db = RuntimeField("db")
    task_manager = RuntimeField("task_manager")
    command_handler = RuntimeField("command_handler")
    ctx_service = RuntimeField("ctx_service")
    news_service = RuntimeField("news_service")
    image_service = RuntimeField("image_service")
    llm_service = RuntimeField("llm_service")
    content_service = RuntimeField("content_service")
    qzone_service = RuntimeField("qzone_service")
    data_dir = RuntimeField("data_dir")
    page_preferences_file = RuntimeField("page_preferences_file")
    _lock = RuntimeField("_lock")
    _is_terminated = RuntimeField("_is_terminated")
    basic_conf = RuntimeField("basic_conf")
    image_conf = RuntimeField("image_conf")
    tts_conf = RuntimeField("tts_conf")
    qzone_conf = RuntimeField("qzone_conf")
    receiver_conf = RuntimeField("receiver_conf")
    extra_shares_conf = RuntimeField("extra_shares_conf")
    context_conf = RuntimeField("context_conf")
    news_conf = RuntimeField("news_conf")
    xiaohongshu_conf = RuntimeField("xiaohongshu_conf")
    contact_aliases = RuntimeField("contact_aliases")
    _page_action_seq = RuntimeField("_page_action_seq")
    _page_action_runs = RuntimeField("_page_action_runs")
    _page_config_schema_raw_cache = RuntimeField("_page_config_schema_raw_cache")
    _page_config_schema_meta_cache = RuntimeField("_page_config_schema_meta_cache")
    _page_target_label_cache_data = RuntimeField("_page_target_label_cache_data")
    _page_event_clients = RuntimeField("_page_event_clients")
    _page_event_seq = RuntimeField("_page_event_seq")

    def __init__(self, runtime) -> None:
        if runtime is None:
            raise TypeError("仪表盘组件必须绑定运行时")
        self.runtime = runtime

    def get_contact_alias(self, target_id: str) -> str:
        return self.runtime.get_contact_alias(target_id)

    def track_task(self, coro):
        return self.runtime.track_task(coro)

    def is_share_busy(
        self, target_uid: str | None = None, *, global_scope: bool = False
    ) -> bool:
        return self.runtime.is_share_busy(target_uid, global_scope=global_scope)

    async def save_config_file(self) -> None:
        await self.runtime.save_config_file()


__all__ = ["PanelComponent", "RuntimeField"]

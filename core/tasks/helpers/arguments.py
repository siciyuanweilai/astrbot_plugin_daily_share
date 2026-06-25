from astrbot.api.event import AstrMessageEvent

from ...config import NEWS_SOURCE_MAP
from ...constants import CMD_CN_MAP, SOURCE_CN_MAP
from ...toolkit import log_exception


class TaskHelperArgsMixin:
    """命令参数与事件目标解析。"""

    def _event_history_target(self, event: AstrMessageEvent) -> str:
        if not event:
            return ""
        try:
            sender_id = str(event.get_sender_id() or "").strip()
        except Exception as e:
            log_exception("[每日分享] 无法读取自然语言触发发送者标识", e, level="debug", with_traceback=False)
            sender_id = ""
        if sender_id and ":" in sender_id:
            return sender_id
        origin = str(getattr(event, "unified_msg_origin", "") or "").strip()
        return origin or sender_id

    def _map_share_type_arg(self, share_type_text: str):
        if share_type_text in CMD_CN_MAP:
            return CMD_CN_MAP[share_type_text]
        for name, stype in CMD_CN_MAP.items():
            if name in share_type_text:
                return stype
        return None

    def _map_news_source_arg(self, source: str):
        if not source:
            return None
        if source in SOURCE_CN_MAP:
            return SOURCE_CN_MAP[source]
        if source in NEWS_SOURCE_MAP:
            return source
        for name, key in SOURCE_CN_MAP.items():
            if name in source or source in name:
                return key
        return None

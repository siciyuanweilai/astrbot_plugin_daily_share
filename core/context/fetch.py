from __future__ import annotations

from .records import (
    ContextHistoryConversationFetchMixin,
    ContextHistoryFetchRouterMixin,
    ContextHistoryOnebotFetchMixin,
    ContextHistoryPlatformFetchMixin,
)


class ContextHistoryFetchMixin(
    ContextHistoryFetchRouterMixin,
    ContextHistoryOnebotFetchMixin,
    ContextHistoryPlatformFetchMixin,
    ContextHistoryConversationFetchMixin,
):
    """聊天历史读取能力聚合。"""


__all__ = ["ContextHistoryFetchMixin"]

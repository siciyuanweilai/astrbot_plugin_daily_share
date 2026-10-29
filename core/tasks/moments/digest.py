from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ...config import NEWS_SOURCE_MAP
from ...database.keys import HISTORY_SHARE_NEWS, QZONE_STATE_KEY, QZONE_TARGET_ID
from ..opportunity import opportunity_news

if TYPE_CHECKING:
    from . import TaskQzoneService


class TaskQzoneNewsService:
    """QQ 空间新闻数据加载。"""

    def __init__(self, owner: TaskQzoneService) -> None:
        self.owner = owner

    async def _load_qzone_news_data(
        self,
        *,
        news_source: str | None = None,
        event: AstrMessageEvent | None = None,
        history_source: str,
        progress_id: str,
    ) -> tuple[bool, tuple[list, str] | None]:
        selected = opportunity_news(QZONE_TARGET_ID)
        if selected:
            return True, selected
        state = await self.owner.db.get_share_state(QZONE_STATE_KEY, {})
        last_news_source = state.get("last_news_source")
        actual_source = news_source or self.owner.news_service.select_news_source(
            excluded_source=last_news_source,
        )

        news_data = await self.owner.news_service.get_hot_news(
            actual_source,
            limit=self.owner.services.snapshots.get_news_snapshot_limit(),
        )
        if news_data:
            await self.owner.db.update_share_state(
                QZONE_STATE_KEY, {"last_news_source": news_data[1]}
            )
            return True, news_data

        source_name = (
            NEWS_SOURCE_MAP.get(actual_source or "", {}).get("name") or "新闻源"
        )
        logger.warning(
            f"[日常分享] QQ 空间获取新闻失败: {source_name} ({actual_source})"
        )
        await self.owner.services.executor_helpers.records.record_share_failure(
            target_id=QZONE_TARGET_ID,
            share_type=HISTORY_SHARE_NEWS,
            message=f"获取新闻失败: {source_name}",
            error_reason=f"获取新闻失败: {source_name}",
            source_type=history_source,
        )
        if event:
            await self.owner.send_event(
                event,
                event.plain_result(
                    f"获取【{source_name}】新闻失败，QQ空间分享已取消。"
                ),
            )
        self.owner.services.progress.finish_share_progress(
            progress_id, success=False, message="获取新闻失败"
        )
        return False, None

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ...config import NEWS_SOURCE_MAP
from ...database.keys import HISTORY_SHARE_NEWS, QZONE_STATE_KEY, QZONE_TARGET_ID


class TaskQzoneNewsMixin:
    """QQ 空间新闻数据加载。"""

    async def _load_qzone_news_data(
        self,
        *,
        news_source: str = None,
        event: AstrMessageEvent = None,
        history_source: str,
        progress_id: str,
    ) -> tuple[bool, object]:
        state = await self.db.get_state(QZONE_STATE_KEY, {})
        last_news_source = state.get("last_news_source")
        actual_source = news_source or self.news_service.select_news_source(
            excluded_source=last_news_source,
        )

        news_data = await self.news_service.get_hot_news(
            actual_source,
            limit=self.get_news_snapshot_limit(),
        )
        if news_data:
            await self.db.update_state_dict(QZONE_STATE_KEY, {"last_news_source": news_data[1]})
            await self._cache_news_snapshot_for_targets(
                QZONE_TARGET_ID,
                snapshot_data=self._news_snapshot_payload(news_data[0], news_data[1]),
                event=event,
            )
            return True, news_data

        source_name = NEWS_SOURCE_MAP.get(actual_source or "", {}).get("name") or "新闻源"
        logger.warning(f"[每日分享] QQ 空间获取新闻失败: {source_name} ({actual_source})")
        await self._record_share_failure(
            target_id=QZONE_TARGET_ID,
            share_type=HISTORY_SHARE_NEWS,
            message=f"获取新闻失败: {source_name}",
            error_reason=f"获取新闻失败: {source_name}",
            source_type=history_source,
        )
        if event:
            await event.send(event.plain_result(f"获取【{source_name}】新闻失败，QQ空间分享已取消。"))
        self._finish_share_progress(progress_id, success=False, message="获取新闻失败")
        return False, None

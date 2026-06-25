from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ...config import NEWS_SOURCE_MAP, ShareType
from ...database.keys import target_state_key
from ...toolkit import format_exception


class TaskExecutorNewsMixin:
    """分享新闻数据与新闻配图。"""

    async def _load_execute_share_news(
        self,
        *,
        uid: str,
        stype: ShareType,
        news_source: str = None,
        event: AstrMessageEvent = None,
        history_source: str,
        progress_id: str,
    ) -> tuple[bool, object]:
        if stype != ShareType.NEWS:
            return True, None

        state = await self.db.get_state(target_state_key(uid), {})
        last_news_source = state.get("last_news_source")
        current_news_source = news_source or self.news_service.select_news_source(
            excluded_source=last_news_source,
        )
        news_data = await self.news_service.get_hot_news(current_news_source)
        if news_data:
            await self.db.update_state_dict(target_state_key(uid), {"last_news_source": news_data[1]})
            await self._cache_news_snapshot_for_targets(uid, news_data=news_data)
            return True, news_data

        source_name = NEWS_SOURCE_MAP.get(current_news_source or "", {}).get("name") or "新闻源"
        logger.warning(f"[每日分享] 获取新闻失败: {source_name} ({current_news_source})")
        await self._record_share_failure(
            target_id=uid,
            share_type=stype.value,
            message=f"获取新闻失败: {source_name}",
            error_reason=f"获取新闻失败: {source_name}",
            source_type=history_source,
        )
        if event:
            await event.send(event.plain_result(f"获取【{source_name}】新闻失败，分享已取消。"))
        self._finish_share_progress(progress_id, success=False, message="获取新闻失败")
        return False, None

    async def _maybe_attach_hot_news_image(self, *, uid: str, stype: ShareType) -> str | None:
        if stype != ShareType.NEWS or not self.image_conf.get("attach_hot_news_image", True):
            return None
        try:
            state = await self.db.get_state(target_state_key(uid), {})
            last_source = state.get("last_news_source")
            if not last_source:
                return None
            img_path, _ = self.news_service.get_hot_news_image_url(last_source)
            if img_path:
                await self._cache_news_snapshot_for_targets(
                    uid,
                    source_key=last_source,
                    image_url=img_path,
                )
            return img_path
        except Exception as e:
            logger.warning(f"[每日分享] 自动任务获取新闻图片失败: {format_exception(e)}")
            return None

from __future__ import annotations

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ....config import NEWS_SOURCE_MAP, ShareType
from ....toolkit import format_exception


class TaskCommandLocalNewsMixin:
    async def _load_command_news(
        self,
        *,
        event: AstrMessageEvent,
        target_umo: str,
        target_type_enum: ShareType,
        news_src_key: str,
        get_image: bool,
        need_image: bool,
    ) -> tuple[bool, object, str | None, str]:
        if target_type_enum != ShareType.NEWS:
            return True, None, None, news_src_key

        if not news_src_key:
            news_src_key = self.news_service.select_news_source()
        news_data = await self.news_service.get_hot_news(
            news_src_key,
            limit=self.get_news_snapshot_limit(),
        )
        if not news_data:
            source_name = NEWS_SOURCE_MAP.get(news_src_key or "", {}).get("name") or "新闻源"
            await event.send(event.plain_result(f"获取【{source_name}】新闻失败，分享已取消。"))
            return False, None, None, news_src_key

        news_src_key = news_data[1]
        snapshot_data = self._news_snapshot_payload(news_data[0], news_src_key)
        await self._cache_news_snapshot_for_targets(target_umo, snapshot_data=snapshot_data)

        img_path = None
        if get_image and not need_image and self.image_conf.get("attach_hot_news_image", True):
            try:
                img_path, _ = self.news_service.get_hot_news_image_url(news_src_key)
                if img_path:
                    await self._cache_news_snapshot_for_targets(
                        target_umo,
                        snapshot_data=snapshot_data,
                        image_url=img_path,
                    )
            except Exception as e:
                logger.warning(f"[每日分享] 主流程获取热搜图片失败: {format_exception(e)}")

        return True, news_data, img_path, news_src_key

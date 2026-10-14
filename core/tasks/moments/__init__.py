from ..continuation import preserve_share
from ..taskbase import TaskServiceBase
from .caption import TaskQzoneContentService
from .digest import TaskQzoneNewsService
from .illustration import TaskQzoneMediaService
from .pipeline import TaskQzoneFlowService
from .release import TaskQzonePublishService


class TaskQzoneService(TaskServiceBase):
    """QQ 空间独立分享流程。"""

    async def _load_qzone_news_data(
        self, *, news_source=None, event=None, history_source, progress_id
    ):
        return await self.news._load_qzone_news_data(
            news_source=news_source,
            event=event,
            history_source=history_source,
            progress_id=progress_id,
        )

    async def _generate_qzone_content(
        self, *, stype, period, post_ctx, news_data, progress_id, event=None
    ):
        return await self.content._generate_qzone_content(
            stype=stype,
            period=period,
            post_ctx=post_ctx,
            news_data=news_data,
            progress_id=progress_id,
            event=event,
        )

    async def _generate_qzone_image(
        self, *, stype, content, life_ctx, news_data, progress_id, event=None
    ):
        return await self.media._generate_qzone_image(
            stype=stype,
            content=content,
            life_ctx=life_ctx,
            news_data=news_data,
            progress_id=progress_id,
            event=event,
        )

    async def _prepare_qzone_publish_media(self, *, target_local_img=None):
        return await self.media._prepare_qzone_publish_media(
            target_local_img=target_local_img
        )

    async def _publish_qzone_best_effort(self, *, text, images):
        return await self.publisher._publish_qzone_best_effort(text=text, images=images)

    async def _publish_and_record_qzone_share(
        self,
        *,
        progress_id,
        stype,
        content,
        qzone_images,
        target_local_img=None,
        history_source,
        news_snapshot_data=None,
    ):
        return await self.publisher._publish_and_record_qzone_share(
            progress_id=progress_id,
            stype=stype,
            content=content,
            qzone_images=qzone_images,
            target_local_img=target_local_img,
            history_source=history_source,
            news_snapshot_data=news_snapshot_data,
        )

    async def _start_qzone_share_progress(self, *, force_type=None, history_source):
        return await self.flow._start_qzone_share_progress(
            force_type=force_type, history_source=history_source
        )

    async def _record_qzone_share_exception(
        self, *, error, stype, history_source, progress_id="", event=None
    ):
        return await self.flow._record_qzone_share_exception(
            error=error,
            stype=stype,
            history_source=history_source,
            progress_id=progress_id,
            event=event,
        )

    async def execute_qzone_share(
        self,
        force_type=None,
        news_source=None,
        event=None,
        source_type="",
        need_video=False,
    ):
        """完全独立的 QQ 空间分享主流程。"""
        return await self.flow.execute_qzone_share(
            force_type, news_source, event, source_type, need_video
        )

    @preserve_share("qzone")
    async def send_prepared_qzone_share(
        self,
        *,
        stype,
        content,
        life_ctx,
        news_data,
        progress_id,
        history_source,
        event=None,
    ):
        return await self.flow.send_prepared_qzone_share(
            stype=stype,
            content=content,
            life_ctx=life_ctx,
            news_data=news_data,
            progress_id=progress_id,
            history_source=history_source,
            event=event,
        )

    def __init__(self, runtime, config, state) -> None:
        super().__init__(runtime, config, state)
        self.news = TaskQzoneNewsService(self)
        self.content = TaskQzoneContentService(self)
        self.media = TaskQzoneMediaService(self)
        self.publisher = TaskQzonePublishService(self)
        self.flow = TaskQzoneFlowService(self)


__all__ = ["TaskQzoneService"]

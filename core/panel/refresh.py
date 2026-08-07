import copy

from astrbot.api import logger

from ..config import DEFAULT_KNOWLEDGE_CATS, DEFAULT_REC_CATS
from ..toolkit import format_exception
from .panelcomponent import PanelComponent


class DashboardConfigRefreshService(PanelComponent):
    """配置保存后刷新运行时引用和定时任务。"""

    def _refresh_config_refs(self) -> None:
        self.basic_conf = self.config.setdefault("basic_conf", {})
        self.image_conf = self.config.setdefault("image_conf", {})
        self.tts_conf = self.config.setdefault("tts_conf", {})
        self.qzone_conf = self.config.setdefault("qzone_conf", {})
        self.receiver_conf = self.config.setdefault("receiver", {})
        self.extra_shares_conf = self.config.setdefault("extra_shares", {})
        self.context_conf = self.config.setdefault("context_conf", {})
        self.news_conf = self.config.setdefault("news_conf", {})
        self.contact_aliases = self.config.get("contact_aliases", [])

        self.ctx_service.config = self.config
        self.ctx_service.life_conf = self.context_conf
        self.ctx_service.history_conf = self.context_conf
        self.ctx_service.memory_conf = self.context_conf
        self.ctx_service.image_conf = self.image_conf
        self.ctx_service.tts_conf = self.tts_conf

        self.news_service.config = self.config
        self.news_service.conf = self.news_conf

        self.image_service.config = self.config
        self.image_service.img_conf = self.image_conf
        self.llm_service.basic_conf = self.basic_conf

        self.content_service.config = self.config
        self.content_service.content_lib_conf = self.config.setdefault(
            "content_library", {}
        )
        raw_knowledge = self.content_service.content_lib_conf.get(
            "knowledge_cats", DEFAULT_KNOWLEDGE_CATS
        )
        raw_rec = self.content_service.content_lib_conf.get(
            "rec_cats", DEFAULT_REC_CATS
        )
        self.content_service.knowledge_cats = (
            self.content_service.parse_category_config(
                raw_knowledge or DEFAULT_KNOWLEDGE_CATS
            )
        )
        self.content_service.rec_cats = self.content_service.parse_category_config(
            raw_rec or DEFAULT_REC_CATS
        )
        self.content_service.basic_conf = self.basic_conf
        self.content_service.news_conf = self.news_conf
        self.content_service.context_conf = self.context_conf
        self.content_service.qzone_conf = self.qzone_conf
        try:
            self.content_service.dedup_days = int(
                self.basic_conf.get("data_retention_days", 60)
            )
        except Exception:
            self.content_service.dedup_days = 60

        self.task_manager.update_configs(
            basic=self.basic_conf,
            extra_shares=self.extra_shares_conf,
            qzone=self.qzone_conf,
            image=self.image_conf,
            tts=self.tts_conf,
            context=self.context_conf,
            receiver=self.receiver_conf,
        )

        self.command_handler.config = self.config
        self.command_handler.basic_conf = self.basic_conf
        self.command_handler.extra_shares_conf = self.extra_shares_conf
        self.command_handler.qzone_conf = self.qzone_conf
        self.qzone_service.qzone_conf = self.qzone_conf
        self.qzone_service.invalidate()

    async def _rebuild_scheduler_after_config(
        self, *, clear_pending_when_disabled: bool = False
    ) -> None:
        runtime = self.plugin.runtime_service
        runtime.set_runtime_state("initializing")
        try:
            self.task_manager.schedule.invalidate_builds()
            self.scheduler.remove_all_jobs()
            if self.config.get("enable_auto_share", False):
                self.task_manager.schedule.setup_tasks()
            else:
                if clear_pending_when_disabled:
                    await self.task_manager.schedule.clear_pending_delay_jobs()
            if self.scheduler.get_jobs() and not self.scheduler.running:
                self.scheduler.start()
        except BaseException as exc:
            self.plugin._is_initialized = False
            runtime.set_runtime_state("failed", str(exc))
            raise
        self.plugin._is_initialized = True
        runtime.set_runtime_state("ready")

    async def save_config_and_refresh_runtime(
        self,
        *,
        clear_pending_when_disabled: bool = False,
        previous_config: dict | None = None,
        precondition=None,
        mutation=None,
        rebuild_scheduler: bool = True,
    ):
        runtime = self.plugin.runtime_service
        async with runtime.config_transaction():
            if precondition is not None:
                precondition()
            backup = copy.deepcopy(
                previous_config if previous_config is not None else dict(self.config)
            )
            previous_enabled = bool(backup.get("enable_auto_share", False))
            try:
                result = mutation() if mutation is not None else None
                self.refresh._refresh_config_refs()
                await runtime.persist_config()
                if rebuild_scheduler:
                    await self.refresh._rebuild_scheduler_after_config(
                        clear_pending_when_disabled=(
                            clear_pending_when_disabled
                            or (
                                previous_enabled
                                and not self.config.get("enable_auto_share", False)
                            )
                        )
                    )
                return result
            except BaseException:
                self.config.clear()
                self.config.update(backup)
                self.refresh._refresh_config_refs()
                try:
                    await runtime.persist_config()
                except BaseException as file_rollback_error:
                    logger.error(
                        "[日常分享] 恢复旧配置文件失败: %s",
                        format_exception(file_rollback_error),
                    )
                if rebuild_scheduler:
                    try:
                        await self.refresh._rebuild_scheduler_after_config()
                    except BaseException as scheduler_rollback_error:
                        logger.error(
                            "[日常分享] 恢复旧定时任务失败: %s",
                            format_exception(scheduler_rollback_error),
                        )
                raise

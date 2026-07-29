import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from astrbot.api import logger

from ..toolkit import log_exception
from ..jsonio import write_json_atomic


class RuntimeService:
    """管理插件生命周期、后台任务、分享锁和配置持久化。"""

    def __init__(self, plugin) -> None:
        self.plugin = plugin
        self._lifecycle_lock = asyncio.Lock()
        self._config_transaction_lock = asyncio.Lock()

    def set_runtime_state(self, state: str, error: str = "") -> None:
        """更新插件运行状态和最近一次初始化错误。"""
        self.plugin._runtime_state = str(state or "created")
        self.plugin._runtime_error = str(error or "").strip()

    def runtime_status(self) -> dict:
        """返回供仪表盘和测试读取的生命周期快照。"""
        plugin = self.plugin
        return {
            "state": str(getattr(plugin, "_runtime_state", "created") or "created"),
            "error": str(getattr(plugin, "_runtime_error", "") or ""),
            "ready": bool(
                plugin._is_initialized
                and not plugin._is_terminated
                and getattr(plugin, "_runtime_state", "") == "ready"
            ),
        }

    def track_task(self, coro):
        plugin = self.plugin
        if plugin._is_terminated:
            coro.close()
            return None
        try:
            task = asyncio.create_task(coro)
        except RuntimeError as exc:
            coro.close()
            log_exception(
                "[日常分享] 创建后台任务失败",
                exc,
                level="warning",
                with_traceback=False,
            )
            return None
        plugin._bg_tasks.add(task)

        def cleanup(done_task) -> None:
            plugin._bg_tasks.discard(done_task)
            if done_task.cancelled():
                return
            try:
                error = done_task.exception()
            except asyncio.CancelledError:
                return
            if error:
                message = (
                    "[日常分享] 插件终止后的后台任务异常"
                    if plugin._is_terminated
                    else "[日常分享] 后台任务异常"
                )
                log_exception(message, error)

        task.add_done_callback(cleanup)
        return task

    async def cancel_background_tasks(self, *, timeout: float = 5.0) -> int:
        plugin = self.plugin
        completed = [task for task in plugin._bg_tasks if task and task.done()]
        for task in completed:
            plugin._bg_tasks.discard(task)
            if task.cancelled():
                continue
            try:
                task.exception()
            except asyncio.CancelledError:
                pass

        tasks = [task for task in plugin._bg_tasks if task and not task.done()]
        if not tasks:
            return 0
        for task in tasks:
            task.cancel()
        done, pending = await asyncio.wait(
            tasks, timeout=max(0.1, float(timeout or 5.0))
        )
        plugin._bg_tasks.difference_update(done)
        if pending:
            logger.warning(
                f"[日常分享] 后台任务取消超时，仍有 {len(pending)} 个任务未结束"
            )
        return len(pending)

    def get_share_lock(
        self, target_uid: str | None = None, *, global_scope: bool = False
    ) -> asyncio.Lock:
        plugin = self.plugin
        if global_scope or not target_uid:
            return plugin._lock
        key = str(target_uid or "").strip()
        lock = plugin._target_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            plugin._target_locks[key] = lock
        return lock

    def is_share_busy(
        self, target_uid: str | None = None, *, global_scope: bool = False
    ) -> bool:
        plugin = self.plugin
        if global_scope:
            return plugin._lock.locked() or any(
                lock.locked() for lock in plugin._target_locks.values()
            )
        if plugin._lock.locked():
            return True
        return self.get_share_lock(target_uid).locked()

    def release_idle_share_lock(self, target_uid: str | None = None) -> None:
        plugin = self.plugin
        key = str(target_uid or "").strip()
        lock = plugin._target_locks.get(key)
        if lock and not lock.locked():
            plugin._target_locks.pop(key, None)

    async def initialize(self) -> None:
        async with self._lifecycle_lock:
            await self._initialize_once()

    async def _initialize_once(self) -> None:
        plugin = self.plugin
        if plugin._is_initialized:
            return
        if plugin._is_terminated:
            raise RuntimeError("插件已经终止，不能重新初始化")

        self.set_runtime_state("initializing")
        try:
            await asyncio.to_thread(
                self._ensure_directories,
                plugin.data_dir,
                plugin.config_file.parent,
            )
            await plugin.db.initialize()
            await self._initialize_runtime()
        except BaseException as exc:
            plugin._is_initialized = False
            plugin._is_terminated = True
            self.set_runtime_state("failed", str(exc))
            await self._cleanup_failed_initialize()
            raise

        plugin._is_initialized = True
        self.set_runtime_state("ready")
        self.track_task(self._delayed_init_bots())

    async def terminate(self) -> None:
        async with self._lifecycle_lock:
            await self._terminate_once()

    async def _terminate_once(self) -> None:
        plugin = self.plugin
        if plugin._is_terminated:
            return
        self.set_runtime_state("terminating")
        plugin._is_terminated = True

        try:
            plugin.task_manager.schedule.invalidate_builds()
            plugin.scheduler.remove_all_jobs()
            if plugin.scheduler.running:
                plugin.scheduler.shutdown(wait=False)
                await asyncio.sleep(0)
        except Exception as exc:
            log_exception(
                "[日常分享] 停止调度器失败",
                exc,
                level="warning",
                with_traceback=False,
            )

        remaining_tasks = 0
        try:
            remaining_tasks = await self.cancel_background_tasks()
        except Exception as exc:
            log_exception(
                "[日常分享] 取消后台任务失败",
                exc,
                level="warning",
                with_traceback=False,
            )

        if remaining_tasks:
            logger.warning(
                f"[日常分享] 仍有 {remaining_tasks} 个后台任务未响应取消，"
                "插件将继续关闭数据库和网络服务"
            )

        for name, service in (
            ("新闻服务", plugin.news_service),
            ("QQ 空间服务", plugin.qzone_service),
            ("数据库", plugin.db),
        ):
            try:
                await service.close()
            except Exception as exc:
                log_exception(
                    f"[日常分享] 关闭{name}失败",
                    exc,
                    level="warning",
                    with_traceback=False,
                )

        plugin._is_initialized = False
        self.set_runtime_state("terminated")
        if remaining_tasks:
            logger.warning(
                f"[日常分享] 插件资源已关闭，但仍有 {remaining_tasks} 个后台任务未响应取消"
            )
        else:
            logger.info("[日常分享] 插件已停止，资源清理完成")

    async def save_config_file(self) -> None:
        async with self.config_transaction():
            await self.persist_config()

    @asynccontextmanager
    async def config_transaction(self):
        """串行化一次完整的配置修改、持久化和运行时刷新。"""
        async with self._config_transaction_lock:
            yield

    async def persist_config(self) -> None:
        """在配置事务内原子写入当前配置。"""
        try:
            await asyncio.to_thread(
                write_json_atomic,
                self.plugin.config_file,
                self.plugin.config,
            )
        except Exception as exc:
            log_exception("[日常分享] 保存配置失败", exc)
            raise

    async def _initialize_runtime(self) -> None:
        plugin = self.plugin
        try:
            await plugin.db.clean_expired_data(plugin.content_service.dedup_days)
        except Exception as exc:
            log_exception(
                "[日常分享] 启动时清理过期数据失败",
                exc,
                level="warning",
                with_traceback=False,
            )

        if plugin.config.get("enable_auto_share", False):
            has_targets = bool(
                plugin.receiver_conf.get("groups") or plugin.receiver_conf.get("users")
            )
            if not has_targets:
                logger.warning("[日常分享] 已启用自动分享，但没有配置接收对象")

        plugin.task_manager.schedule.setup_tasks()
        if not plugin._is_terminated and not plugin.scheduler.running:
            if plugin.scheduler.get_jobs():
                plugin.scheduler.start()

    async def _cleanup_failed_initialize(self) -> None:
        """清理初始化过程中已经创建的运行资源。"""
        plugin = self.plugin
        try:
            plugin.task_manager.schedule.invalidate_builds()
            plugin.scheduler.remove_all_jobs()
            if plugin.scheduler.running:
                plugin.scheduler.shutdown(wait=False)
        except Exception as exc:
            log_exception(
                "[日常分享] 初始化失败时清理调度器失败",
                exc,
                level="warning",
                with_traceback=False,
            )

        try:
            await self.cancel_background_tasks()
        except Exception as exc:
            log_exception(
                "[日常分享] 初始化失败时清理后台任务失败",
                exc,
                level="warning",
                with_traceback=False,
            )

        for name, service in (
            ("新闻服务", plugin.news_service),
            ("QQ 空间服务", plugin.qzone_service),
            ("数据库", plugin.db),
        ):
            try:
                await service.close()
            except Exception as exc:
                log_exception(
                    f"[日常分享] 初始化失败时关闭{name}失败",
                    exc,
                    level="warning",
                    with_traceback=False,
                )

    async def _delayed_init_bots(self) -> None:
        try:
            await asyncio.sleep(30)
            if not self.plugin._is_terminated:
                await self.plugin.ctx_service.init_bots()
        except asyncio.CancelledError:
            return
        except Exception as exc:
            log_exception("[日常分享] 初始化机器人缓存失败", exc)

    @staticmethod
    def _ensure_directories(data_dir: Path, config_dir: Path) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        config_dir.mkdir(parents=True, exist_ok=True)

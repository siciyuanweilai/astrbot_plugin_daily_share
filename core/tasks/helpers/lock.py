class TaskHelperLockMixin:
    """命令触发分享锁辅助。"""

    def _get_command_share_lock(self, target_uid: str = "", *, global_scope: bool = False):
        get_lock = getattr(self.plugin, "_get_share_lock", None)
        if callable(get_lock):
            return get_lock(target_uid, global_scope=global_scope)
        return self._lock

    def _is_command_share_busy(self, target_uid: str = "", *, global_scope: bool = False) -> bool:
        is_busy = getattr(self.plugin, "_is_share_busy", None)
        if callable(is_busy):
            return bool(is_busy(target_uid, global_scope=global_scope))
        return self._lock.locked()

    def _release_command_share_lock(self, target_uid: str = "") -> None:
        release = getattr(self.plugin, "_release_idle_share_lock", None)
        if callable(release):
            release(target_uid)

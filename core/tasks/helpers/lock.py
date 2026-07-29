from .arguments import TaskHelperArgsService


class TaskHelperLockService(TaskHelperArgsService):
    """命令触发分享锁辅助。"""

    def get_command_share_lock(
        self, target_uid: str = "", *, global_scope: bool = False
    ):
        return self.plugin.get_share_lock(target_uid, global_scope=global_scope)

    def is_command_share_busy(
        self, target_uid: str = "", *, global_scope: bool = False
    ) -> bool:
        return bool(self.plugin.is_share_busy(target_uid, global_scope=global_scope))

    def release_command_share_lock(self, target_uid: str = "") -> None:
        self.plugin.release_idle_share_lock(target_uid)

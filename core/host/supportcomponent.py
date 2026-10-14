from __future__ import annotations


class RuntimeField:
    """显式声明宿主组件需要从宿主运行时读写的字段。"""

    def __init__(self, name: str) -> None:
        self.name = name

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        return getattr(instance.runtime, self.name)

    def __set__(self, instance, value) -> None:
        setattr(instance.runtime, self.name, value)


class SupportComponent:
    """只接受明确宿主运行时的宿主组件基类。"""

    def __init__(self, runtime) -> None:
        if runtime is None:
            raise TypeError("宿主组件必须绑定运行时")
        self.runtime = runtime

    def track_task(self, coro):
        return self.runtime.track_task(coro)

    def get_share_lock(
        self, target_uid: str | None = None, *, global_scope: bool = False
    ):
        return self.runtime.get_share_lock(target_uid, global_scope=global_scope)

    def is_share_busy(
        self, target_uid: str | None = None, *, global_scope: bool = False
    ):
        return self.runtime.is_share_busy(target_uid, global_scope=global_scope)

    def release_idle_share_lock(self, target_uid: str | None = None):
        return self.runtime.release_idle_share_lock(target_uid)

    async def save_config_file(self) -> None:
        await self.runtime.save_config_file()

    async def save_config_and_refresh_runtime(self, **kwargs):
        return await self.runtime.save_config_and_refresh_runtime(**kwargs)

    def emit_dashboard_event(
        self, event_type: str = "status", data: dict | None = None
    ) -> None:
        self.runtime.emit_dashboard_event(event_type, data)

    async def send_event(self, event, chain) -> None:
        await self.runtime.send_event(event, chain)


__all__ = ["RuntimeField", "SupportComponent"]

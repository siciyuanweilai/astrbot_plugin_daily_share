from __future__ import annotations


class RuntimeField:
    """显式声明组件需要从面板运行时读写的字段。"""

    def __init__(self, name: str) -> None:
        self.name = name

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        return getattr(instance.runtime, self.name)

    def __set__(self, instance, value) -> None:
        setattr(instance.runtime, self.name, value)


class PanelComponent:
    """只接受明确面板运行时的仪表盘组件基类。"""

    def __init__(self, runtime) -> None:
        if runtime is None:
            raise TypeError("仪表盘组件必须绑定运行时")
        self.runtime = runtime

    def get_contact_alias(self, target_id: str) -> str:
        return self.runtime.get_contact_alias(target_id)

    def track_task(self, coro):
        return self.runtime.track_task(coro)

    def is_share_busy(
        self, target_uid: str | None = None, *, global_scope: bool = False
    ) -> bool:
        return self.runtime.is_share_busy(target_uid, global_scope=global_scope)

    async def save_config_file(self) -> None:
        await self.runtime.save_config_file()


__all__ = ["PanelComponent", "RuntimeField"]

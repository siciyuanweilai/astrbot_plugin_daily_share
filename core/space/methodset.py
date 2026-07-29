from __future__ import annotations

from typing import Any, TYPE_CHECKING


if TYPE_CHECKING:

    class QzoneMethodSet:
        """为分文件实现声明 QQ 空间聚合服务提供的方法集合。"""

        _session: Any
        _h2_session: Any
        _session_timeout_seconds: int | None
        _h2_timeout_seconds: int | None
        _ctx: Any
        _ctx_at: float

        def __getattribute__(self, name: str) -> Any: ...
else:

    class QzoneMethodSet:
        """运行时空基类；不提供动态属性路由。"""


__all__ = ["QzoneMethodSet"]

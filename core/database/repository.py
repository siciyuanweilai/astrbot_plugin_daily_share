from __future__ import annotations


class DatabaseRepository:
    """数据库仓储共享的最小连接与执行契约。"""

    def __init__(self, manager):
        self.manager = manager

    def _connection(self, *, write: bool = False, timeout: float | None = None):
        return self.manager._connection(write=write, timeout=timeout)

    def _fetch_one(self, sql: str, params=()):
        return self.manager._fetch_one(sql, params)

    def _fetch_all(self, sql: str, params=()):
        return self.manager._fetch_all(sql, params)

    def _execute_write(self, sql: str, params=()) -> int:
        return self.manager._execute_write(sql, params)

    async def _execute(self, func, *args, **kwargs):
        return await self.manager._execute(func, *args, **kwargs)

    async def _execute_context(self, func, *args, **kwargs):
        return await self.manager._execute_context(func, *args, **kwargs)


__all__ = ["DatabaseRepository"]

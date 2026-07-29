from datetime import datetime
import json
from typing import Any, Dict

from .repository import DatabaseRepository

from .dbschema import STATE_DOMAINS


class DatabaseStateService(DatabaseRepository):
    """在统一状态表中按领域读写运行状态。"""

    @staticmethod
    def _state_domain(domain: str) -> str:
        if domain not in STATE_DOMAINS:
            raise ValueError(f"未知状态领域: {domain}")
        return domain

    def _sync_get_domain_state(
        self, domain: str, key: str, default: Any | None = None
    ) -> Any:
        domain = self._state_domain(domain)
        with self._connection() as conn:
            row = conn.execute(
                "SELECT value FROM plugin_state WHERE domain = ? AND key = ?",
                (domain, key),
            ).fetchone()
        if row:
            try:
                return json.loads(row[0])
            except json.JSONDecodeError:
                return row[0]
        return default

    def _sync_set_domain_state(self, domain: str, key: str, value: Any) -> None:
        domain = self._state_domain(domain)
        with self._connection(write=True) as conn:
            conn.execute(
                """
                INSERT INTO plugin_state (domain, key, value, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(domain, key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (
                    domain,
                    key,
                    json.dumps(value, ensure_ascii=False),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )

    def _sync_update_domain_state(self, domain: str, key: str, updates: Dict) -> Dict:
        domain = self._state_domain(domain)
        with self._connection(write=True) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT value FROM plugin_state WHERE domain = ? AND key = ?",
                (domain, key),
            ).fetchone()
            current = {}
            if row:
                try:
                    current = json.loads(row[0])
                except (TypeError, json.JSONDecodeError):
                    current = {}
            if not isinstance(current, dict):
                current = {}
            current.update(updates)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                INSERT INTO plugin_state (domain, key, value, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(domain, key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (domain, key, json.dumps(current, ensure_ascii=False), now_str),
            )
            return current

    async def _get_domain_state(
        self, domain: str, key: str, default: Any | None = None
    ) -> Any:
        return await self._execute(self._sync_get_domain_state, domain, key, default)

    async def _set_domain_state(self, domain: str, key: str, value: Any) -> None:
        await self._execute(self._sync_set_domain_state, domain, key, value)

    async def _update_domain_state(self, domain: str, key: str, updates: Dict) -> Dict:
        return await self._execute(self._sync_update_domain_state, domain, key, updates)

    async def get_share_state(self, key: str, default: Any | None = None) -> Any:
        return await self._get_domain_state("share", key, default)

    async def set_share_state(self, key: str, value: Any) -> None:
        await self._set_domain_state("share", key, value)

    async def update_share_state(self, key: str, updates: Dict) -> Dict:
        return await self._update_domain_state("share", key, updates)

    async def get_qzone_state(self, key: str, default: Any | None = None) -> Any:
        return await self._get_domain_state("qzone", key, default)

    async def set_qzone_state(self, key: str, value: Any) -> None:
        await self._set_domain_state("qzone", key, value)

    async def update_qzone_state(self, key: str, updates: Dict) -> Dict:
        return await self._update_domain_state("qzone", key, updates)

    async def get_context_state(self, key: str, default: Any | None = None) -> Any:
        return await self._get_domain_state("context", key, default)

    async def set_context_state(self, key: str, value: Any) -> None:
        await self._set_domain_state("context", key, value)

    async def update_context_state(self, key: str, updates: Dict) -> Dict:
        return await self._update_domain_state("context", key, updates)

    async def get_cache_state(self, key: str, default: Any | None = None) -> Any:
        return await self._get_domain_state("cache", key, default)

    async def set_cache_state(self, key: str, value: Any) -> None:
        await self._set_domain_state("cache", key, value)

    async def update_cache_state(self, key: str, updates: Dict) -> Dict:
        return await self._update_domain_state("cache", key, updates)

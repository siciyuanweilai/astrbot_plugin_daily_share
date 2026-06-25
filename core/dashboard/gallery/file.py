from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from astrbot.api import logger


class DashboardMediaFileMixin:
    def _page_media_delete_roots(self) -> list[Path]:
        return [
            self.data_dir,
            self.data_dir.parent / "astrbot_plugin_daily_life" / "generated_media",
        ]

    def _page_daily_life_data_dir(self) -> Path:
        return self.data_dir.parent / "astrbot_plugin_daily_life"

    def _page_resolve_media_path(self, media_path: str) -> Optional[Path]:
        media_path = self._page_local_media_ref(media_path)
        if not media_path:
            return None

        candidates = [Path(media_path)]
        raw_path = Path(media_path)
        if not raw_path.is_absolute():
            candidates.extend(
                [
                    self.data_dir / raw_path,
                    self.data_dir / "Temp" / raw_path,
                    self._page_daily_life_data_dir() / raw_path,
                    self._page_daily_life_data_dir() / "generated_media" / raw_path,
                    Path.cwd() / raw_path,
                ]
            )

        for candidate in candidates:
            try:
                resolved = candidate.resolve(strict=False)
                if resolved.is_file():
                    return resolved
            except Exception:
                continue
        return None

    def _page_safe_media_delete_path(self, media_ref: str) -> Optional[Path]:
        path = self._page_resolve_media_path(media_ref)
        if not path:
            return None

        try:
            resolved = path.resolve(strict=False)
            for root in self._page_media_delete_roots():
                try:
                    resolved.relative_to(root.resolve(strict=False))
                    return resolved
                except ValueError:
                    continue
        except Exception:
            pass
        logger.debug(f"[每日分享] 跳过非托管媒体文件删除: {path}")
        return None

    def _page_local_media_refs(self, item: dict) -> list[str]:
        refs = []
        ref = self._page_local_media_ref(item.get("media_path", ""))
        if ref:
            refs.append(ref)
        return refs

    def _page_media_ref_aliases(self, path: Path, refs: set[str]) -> set[str]:
        aliases = {str(ref).strip() for ref in refs if str(ref or "").strip()}
        try:
            resolved = path.resolve(strict=False)
            aliases.add(str(resolved))
            aliases.add(resolved.as_posix())
            try:
                aliases.add(resolved.as_uri())
            except ValueError:
                pass
            for root in self._page_media_delete_roots():
                try:
                    relative = resolved.relative_to(root.resolve(strict=False))
                except ValueError:
                    continue
                aliases.add(str(relative))
                aliases.add(relative.as_posix())
                daily_life_root = self._page_daily_life_data_dir().resolve(strict=False)
                try:
                    daily_life_relative = resolved.relative_to(daily_life_root)
                    aliases.add(str(daily_life_relative))
                    aliases.add(daily_life_relative.as_posix())
                except ValueError:
                    pass
                if root == self.data_dir:
                    temp_root = (self.data_dir / "Temp").resolve(strict=False)
                    try:
                        temp_relative = resolved.relative_to(temp_root)
                    except ValueError:
                        continue
                    aliases.add(str(temp_relative))
                    aliases.add(temp_relative.as_posix())
        except Exception:
            pass
        return {alias for alias in aliases if alias}

    async def _page_count_media_file_refs(self, refs: set[str]) -> int:
        count_refs = getattr(self.db, "count_history_media_refs", None)
        if callable(count_refs):
            return await count_refs(sorted(refs))

        count_one = getattr(self.db, "count_history_media_path_refs", None)
        if not callable(count_one):
            return 0
        total = 0
        for ref in refs:
            total += int(await count_one(ref) or 0)
            if total > 0:
                break
        return total

    @staticmethod
    def _page_unlink_media_file(path: Path) -> int:
        size = path.stat().st_size
        path.unlink()
        return size

    async def _page_delete_local_media_files(self, items: list) -> dict:
        result = {
            "requested": True,
            "deleted": 0,
            "skipped": 0,
            "failed": 0,
            "bytes": 0,
        }
        candidates = {}
        for item in items:
            refs = self._page_local_media_refs(item)
            if not refs:
                continue
            path = None
            for ref in refs:
                path = self._page_safe_media_delete_path(ref)
                if path:
                    break
            if not path:
                result["skipped"] += 1
                continue
            key = str(path)
            candidate = candidates.setdefault(key, {"path": path, "refs": set()})
            candidate["refs"].update(refs)

        for candidate in candidates.values():
            path = candidate["path"]
            try:
                refs = self._page_media_ref_aliases(path, candidate["refs"])
                if await self._page_count_media_file_refs(refs) > 0:
                    result["skipped"] += 1
                    continue
                removed_bytes = await asyncio.to_thread(self._page_unlink_media_file, path)
                result["deleted"] += 1
                result["bytes"] += removed_bytes
            except FileNotFoundError:
                result["skipped"] += 1
            except Exception as exc:
                result["failed"] += 1
                logger.debug(f"[每日分享] 删除本地媒体文件失败: {path}, {exc}")
        return result

    @staticmethod
    def _page_media_file_version(path: Path, stat_result=None) -> str:
        stat_result = stat_result or path.stat()
        return f"{int(stat_result.st_mtime_ns)}-{int(stat_result.st_size)}"

    @staticmethod
    def _page_file_data_url(path: Path, mime: str) -> str:
        import base64

        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

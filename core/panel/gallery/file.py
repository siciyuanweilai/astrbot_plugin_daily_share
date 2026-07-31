from __future__ import annotations

import asyncio
from pathlib import Path

from astrbot.api import logger

from ..panelcomponent import PanelComponent


class DashboardMediaFileService(PanelComponent):
    def _page_resolve_media_path(self, media_path: str) -> Path | None:
        media_path = self.media_kind._page_local_media_ref(media_path)
        if not media_path:
            return None

        raw_path = Path(media_path)
        candidates = (
            [raw_path]
            if raw_path.is_absolute()
            else [self.data_dir / raw_path, self.data_dir / "Temp" / raw_path]
        )
        daily_life_data_dir = self.data_dir.parent / "astrbot_plugin_daily_life"
        allowed_roots = [
            (self.data_dir / "Temp").resolve(strict=False),
            (daily_life_data_dir / "generated" / "images").resolve(strict=False),
            (daily_life_data_dir / "generated" / "videos").resolve(strict=False),
        ]

        for candidate in candidates:
            try:
                resolved = candidate.resolve(strict=False)
                if not any(resolved.is_relative_to(root) for root in allowed_roots):
                    logger.debug(f"[日常分享] 跳过非托管媒体文件访问: {resolved}")
                    continue
                if resolved.is_file():
                    return resolved
            except Exception:
                continue
        return None

    def _page_local_media_refs(self, item: dict) -> list[str]:
        refs = []
        ref = self.media_kind._page_local_media_ref(item.get("media_path", ""))
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
            try:
                relative = resolved.relative_to(self.data_dir.resolve(strict=False))
                aliases.add(str(relative))
                aliases.add(relative.as_posix())
            except ValueError:
                pass
            temp_root = (self.data_dir / "Temp").resolve(strict=False)
            try:
                temp_relative = resolved.relative_to(temp_root)
                aliases.add(str(temp_relative))
                aliases.add(temp_relative.as_posix())
            except ValueError:
                pass
        except Exception:
            pass
        return {alias for alias in aliases if alias}

    async def _page_count_media_file_refs(self, refs: set[str]) -> int:
        return await self.db.count_history_media_refs(sorted(refs))

    def _page_unlink_media_file(self, path: Path) -> int:
        verified_path = self.media_files._page_resolve_media_path(str(path))
        if verified_path is None or verified_path != path.resolve(strict=False):
            raise PermissionError(f"拒绝删除非托管媒体文件: {path}")
        size = verified_path.stat().st_size
        verified_path.unlink()
        return size

    async def _page_delete_local_media_files(self, items: list) -> dict:
        result = {
            "requested": True,
            "deleted": 0,
            "skipped": 0,
            "failed": 0,
            "bytes": 0,
        }
        candidates: dict[str, tuple[Path, set[str]]] = {}
        for item in items:
            refs = self.media_files._page_local_media_refs(item)
            if not refs:
                continue
            path = None
            for ref in refs:
                path = await asyncio.to_thread(
                    self.media_files._page_resolve_media_path, ref
                )
                if path:
                    break
            if not path:
                result["skipped"] += 1
                continue
            key = str(path)
            candidate = candidates.setdefault(key, (path, set()))
            candidate[1].update(str(ref) for ref in refs)

        for candidate_path, stored_refs in candidates.values():
            try:
                aliases = await asyncio.to_thread(
                    self.media_files._page_media_ref_aliases,
                    candidate_path,
                    stored_refs,
                )
                if await self.media_files._page_count_media_file_refs(aliases) > 0:
                    result["skipped"] += 1
                    continue
                removed_bytes = await asyncio.to_thread(
                    self.media_files._page_unlink_media_file, candidate_path
                )
                result["deleted"] += 1
                result["bytes"] += removed_bytes
            except FileNotFoundError:
                result["skipped"] += 1
            except Exception as exc:
                result["failed"] += 1
                logger.debug(
                    f"[日常分享] 删除本地媒体文件失败: {candidate_path}, {exc}"
                )
        return result

    @staticmethod
    def _page_file_data_url(path: Path, mime: str) -> str:
        import base64

        parts = []
        remainder = b""
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(64 * 1024)
                if not chunk:
                    break
                chunk = remainder + chunk
                keep = len(chunk) % 3
                if keep:
                    remainder = chunk[-keep:]
                    chunk = chunk[:-keep]
                else:
                    remainder = b""
                if chunk:
                    parts.append(base64.b64encode(chunk).decode("ascii"))
        if remainder:
            parts.append(base64.b64encode(remainder).decode("ascii"))
        encoded = "".join(parts)
        return f"data:{mime};base64,{encoded}"

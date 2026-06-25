from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from astrbot.api import logger


class QzoneVideoMetaMixin:
    @staticmethod
    def _ffmpeg_path() -> str:
        return shutil.which("ffmpeg") or ""

    @classmethod
    def _ffprobe_path(cls) -> str:
        path = shutil.which("ffprobe")
        if path:
            return path
        ffmpeg = cls._ffmpeg_path()
        if not ffmpeg:
            return ""
        candidate = Path(ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
        return str(candidate) if candidate.is_file() else ""

    @staticmethod
    async def _run_media_probe(command: list[str], *, timeout: int = 10) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return -1, "", "timeout"
        return (
            int(proc.returncode or 0),
            stdout.decode("utf-8", "ignore"),
            stderr.decode("utf-8", "ignore"),
        )

    @staticmethod
    def _duration_ms_from_text(value: str) -> int:
        text = str(value or "").strip()
        if not text:
            return 0
        try:
            seconds = float(text)
            return int(seconds * 1000) if seconds > 0 else 0
        except (TypeError, ValueError):
            pass

        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
        if not match:
            return 0
        hours, minutes, seconds_text = match.groups()
        seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds_text)
        return int(seconds * 1000) if seconds > 0 else 0

    async def _probe_video_play_time(self, video_payload: dict[str, Any]) -> int:
        source = str(video_payload.get("source") or "").strip()
        if not source or source.startswith(("base64://", "data:", "http://", "https://")):
            return 0
        path = Path(source)
        if not path.is_file():
            return 0
        ffprobe = self._ffprobe_path()
        if ffprobe:
            code, stdout, stderr = await self._run_media_probe(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ]
            )
            play_time = self._duration_ms_from_text(stdout)
            if play_time > 0:
                return play_time
            error = (stderr or stdout).strip()
            if code == -1:
                logger.debug("[每日分享] ffprobe 读取 QQ 空间视频时长超时。")
            elif error:
                logger.debug(f"[每日分享] ffprobe 读取 QQ 空间视频时长失败: {error[:200]}")

        ffmpeg = self._ffmpeg_path()
        if not ffmpeg:
            return 0
        code, stdout, stderr = await self._run_media_probe(
            [ffmpeg, "-hide_banner", "-i", str(path)],
            timeout=10,
        )
        play_time = self._duration_ms_from_text(stderr or stdout)
        if play_time > 0:
            return play_time
        if code == -1:
            logger.debug("[每日分享] ffmpeg 读取 QQ 空间视频时长超时。")
        return 0

    async def _resolve_video_play_time(self, video: Any, video_payload: dict[str, Any]) -> int:
        play_time = self._video_play_time(video)
        if play_time <= 0:
            play_time = await self._probe_video_play_time(video_payload)
            if play_time > 0:
                logger.info(f"[每日分享] 已读取 QQ 空间视频时长: {play_time} 毫秒")
        if play_time > 600_000:
            raise RuntimeError(f"QQ 空间视频时长 {play_time // 1000} 秒，超过 10 分钟上限")
        return play_time

    async def _extract_video_cover_frame(self, video_payload: dict[str, Any]) -> str:
        source = str(video_payload.get("source") or "").strip()
        if not source or source.startswith(("http://", "https://")):
            return ""
        ffmpeg = self._ffmpeg_path()
        if not ffmpeg:
            return ""
        temp_video = None
        path = Path(source)
        data = video_payload.get("data")
        if isinstance(data, (bytes, bytearray, memoryview)):
            suffix = Path(str(video_payload.get("filename") or "")).suffix or ".mp4"
            temp_video = Path(tempfile.gettempdir()) / f"qzone_video_source_{int(time.time() * 1000)}_{os.getpid()}{suffix}"
            try:
                await asyncio.to_thread(temp_video.write_bytes, bytes(data))
            except Exception as exc:
                logger.debug(f"[每日分享] 写入 QQ 空间临时视频文件失败: {exc}")
                return ""
            path = temp_video
        elif not path.is_file():
            return ""
        output = Path(tempfile.gettempdir()) / f"qzone_video_cover_{int(time.time() * 1000)}_{os.getpid()}.jpg"
        try:
            proc = await asyncio.create_subprocess_exec(
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                "00:00:01",
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(output),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0 or not output.is_file() or output.stat().st_size <= 0:
                try:
                    output.unlink(missing_ok=True)
                except Exception:
                    pass
                error = stderr.decode("utf-8", "ignore").strip()
                if error:
                    logger.debug(f"[每日分享] ffmpeg 截取 QQ 空间视频封面失败: {error[:200]}")
                return ""
        finally:
            if temp_video:
                try:
                    temp_video.unlink(missing_ok=True)
                except Exception as cleanup_exc:
                    logger.debug(f"[每日分享] 清理 QQ 空间临时视频文件失败: {cleanup_exc}")
        logger.info("[每日分享] 已使用 ffmpeg 从视频截取 QQ 空间封面。")
        return str(output)

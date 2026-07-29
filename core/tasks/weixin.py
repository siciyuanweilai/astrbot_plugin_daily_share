import asyncio
import hashlib
from pathlib import Path

from astrbot.api import logger

from .taskbase import TaskServiceBase


class TaskDeliveryWeixinService(TaskServiceBase):
    """处理个人微信发送超时和图片压缩。"""

    def get_send_timeout_seconds(self) -> int:
        try:
            timeout_seconds = int(self.image_conf.get("weixin_api_timeout_seconds", 60))
        except (TypeError, ValueError):
            timeout_seconds = 60
        return max(15, min(timeout_seconds, 300))

    def _compress_image_for_weixin_sync(
        self,
        img_path: str,
        max_side: int | None = None,
        max_kb: int | None = None,
        force: bool = False,
    ) -> str:
        """创建适合个人微信发送的轻量压缩图片副本。"""
        source_path = Path(img_path) if img_path else None
        if source_path is None or not source_path.exists():
            return img_path
        try:
            from PIL import Image as PILImage
            from PIL import ImageOps
        except Exception as exc:
            logger.debug(f"[日常分享] 图片处理库不可用，跳过微信图片压缩: {exc}")
            return img_path

        max_side, target_bytes = self._weixin_image_limits(max_side, max_kb)
        raw_size = source_path.stat().st_size
        try:
            with PILImage.open(source_path) as source_image:
                image = ImageOps.exif_transpose(source_image)
                width, height = image.size
                if self._weixin_image_within_limits(
                    raw_size,
                    width,
                    height,
                    max_side=max_side,
                    target_bytes=target_bytes,
                    force=force,
                ):
                    return img_path

                image = self._weixin_rgb_image(image, PILImage)
                if max(width, height) > max_side:
                    image.thumbnail((max_side, max_side), PILImage.Resampling.LANCZOS)
                output_path = self._weixin_output_path(
                    source_path,
                    raw_size=raw_size,
                    max_side=max_side,
                    max_kb=target_bytes // 1024,
                    force=force,
                )
                self._weixin_encode_image(image, output_path, target_bytes)
                return self._weixin_keep_smaller_image(
                    output_path,
                    original_path=img_path,
                    raw_size=raw_size,
                    original_size=(width, height),
                    compressed_size=image.size,
                )
        except Exception as exc:
            logger.warning(f"[日常分享] 微信图片压缩失败，继续发送原图: {exc}")
            return img_path

    def _weixin_image_limits(
        self, max_side: int | None, max_kb: int | None
    ) -> tuple[int, int]:
        try:
            side = int(
                max_side
                if max_side is not None
                else self.image_conf.get("weixin_image_max_side", 4096)
            )
        except (TypeError, ValueError):
            side = 4096
        try:
            size_kb = int(
                max_kb
                if max_kb is not None
                else self.image_conf.get("weixin_image_max_size_kb", 10240)
            )
        except (TypeError, ValueError):
            size_kb = 10240
        return max(1600, min(side, 8192)), max(512, size_kb) * 1024

    @staticmethod
    def _weixin_image_within_limits(
        raw_size: int,
        width: int,
        height: int,
        *,
        max_side: int,
        target_bytes: int,
        force: bool,
    ) -> bool:
        return not force and raw_size <= target_bytes and max(width, height) <= max_side

    @staticmethod
    def _weixin_rgb_image(image, image_module):
        has_alpha = image.mode in ("RGBA", "LA") or (
            image.mode == "P" and "transparency" in image.info
        )
        if not has_alpha:
            return image.convert("RGB")
        rgba = image.convert("RGBA")
        background = image_module.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background

    def _weixin_output_path(
        self,
        source_path: Path,
        *,
        raw_size: int,
        max_side: int,
        max_kb: int,
        force: bool,
    ) -> Path:
        temp_dir = Path(self.plugin.data_dir) / "Temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        digest_source = (
            f"{source_path}:{raw_size}:{source_path.stat().st_mtime}:"
            f"{max_side}:{max_kb}:{force}"
        ).encode("utf-8", errors="ignore")
        digest = hashlib.md5(digest_source, usedforsecurity=False).hexdigest()[:12]
        return temp_dir / f"weixin_send_{digest}.jpg"

    @staticmethod
    def _weixin_encode_image(image, output_path: Path, target_bytes: int) -> None:
        for quality in (95, 93, 90, 88, 85, 82, 78, 74, 70):
            image.save(
                output_path,
                format="JPEG",
                quality=quality,
                optimize=True,
                progressive=False,
                subsampling=0 if quality >= 90 else -1,
            )
            if output_path.stat().st_size <= target_bytes:
                return

    def _weixin_keep_smaller_image(
        self,
        output_path: Path,
        *,
        original_path: str,
        raw_size: int,
        original_size: tuple[int, int],
        compressed_size: tuple[int, int],
    ) -> str:
        output_size = output_path.stat().st_size
        if output_size >= raw_size:
            output_path.unlink(missing_ok=True)
            return original_path

        logger.info(
            f"[日常分享] 已优化微信图片: {raw_size / 1024 / 1024:.2f} 兆字节 → "
            f"{output_size / 1024 / 1024:.2f} 兆字节，分辨率 "
            f"{original_size[0]}×{original_size[1]} → "
            f"{compressed_size[0]}×{compressed_size[1]}"
        )
        max_count = self.services.delivery_assets.get_weixin_temp_cleanup_max_count()
        if max_count > 0:
            self.services.delivery_assets.cleanup_weixin_temp_images_sync(max_count)
        return str(output_path)

    async def prepare_image_for_target(
        self, uid: str, img_path: str | None
    ) -> str | None:
        if not img_path:
            return img_path
        if self.ctx_service.is_weixin_platform(uid) and self.image_conf.get(
            "weixin_compress_images", True
        ):
            return await asyncio.to_thread(
                self._compress_image_for_weixin_sync, img_path
            )
        return img_path

    async def prepare_weixin_retry_image(self, img_path: str) -> str:
        if not img_path or img_path.startswith("http"):
            return img_path
        if not await asyncio.to_thread(Path(img_path).exists):
            return img_path
        if not self.image_conf.get("weixin_compress_images", True):
            return img_path

        max_side, target_bytes = self._weixin_image_limits(None, None)
        retry_side = min(max_side, 2048)
        retry_kb = min(target_bytes // 1024, 1024)
        return await asyncio.to_thread(
            self._compress_image_for_weixin_sync,
            img_path,
            max_side=retry_side,
            max_kb=retry_kb,
            force=True,
        )

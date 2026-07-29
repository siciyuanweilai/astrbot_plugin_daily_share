import asyncio

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain

from ..database.keys import (
    BRIEFING_TARGET_ID,
    HISTORY_SHARE_BRIEFING,
    QZONE_TARGET_ID,
    SOURCE_SCHEDULED,
)
from .taskbase import TaskServiceBase


class TaskBriefingService(TaskServiceBase):
    """60 秒读世界与 AI 资讯早报发送流程。"""

    async def send_command_briefing_image(
        self,
        event: AstrMessageEvent,
        *,
        url: str,
        to_qzone: bool,
        qzone_text: str,
        qzone_success_text: str,
        filename_label: str,
        local_history_text: str,
        local_fail_text: str,
        history_source: str,
    ) -> bool:
        target_id = (
            QZONE_TARGET_ID
            if to_qzone
            else self.services.executor_helpers.event_history_target(event)
        )
        target_label = (
            ""
            if to_qzone
            else await self.services.targets.get_target_display_name(
                target_id, event=event
            )
        )
        progress_id = self.services.progress.start_share_progress(
            source_type=history_source,
            target_id=target_id,
            target_label=target_label,
            share_type=HISTORY_SHARE_BRIEFING,
            enabled_steps=["image", "send"],
            message=f"准备发送 {filename_label}",
        )
        if to_qzone:
            try:
                self.services.progress.complete_share_progress_step(
                    progress_id, "image", "早报图片已获取"
                )
                logger.info("[日常分享] 正在登录 QQ 空间...")
                self.services.progress.update_share_progress(
                    progress_id, "send", message="正在登录 QQ 空间"
                )
                await self.plugin.publish_qzone(text=qzone_text, images=[url])
                await self.send_event(event, event.plain_result(qzone_success_text))
                await self.db.add_sent_history(
                    QZONE_TARGET_ID,
                    HISTORY_SHARE_BRIEFING,
                    qzone_text,
                    True,
                    source_type=history_source,
                    **self.services.executor_helpers.image_history_kwargs(url),
                )
                self.services.progress.finish_share_progress(
                    progress_id, success=True, message="早报分享完成"
                )
                return True
            except Exception as e:
                await self.send_event(
                    event, event.plain_result(f"QQ 空间分享失败: {e}")
                )
                self.services.progress.finish_share_progress(
                    progress_id, success=False, message="早报分享失败"
                )
                return False

        self.services.progress.update_share_progress(
            progress_id, "image", message="下载早报图片中"
        )
        filename = self.services.delivery_assets.build_news_image_filename(
            url, filename_label
        )
        local_path = await self.services.delivery_assets.download_image_to_local(
            url, filename
        )
        if not local_path:
            await self.send_event(event, event.plain_result(local_fail_text))
            self.services.progress.finish_share_progress(
                progress_id, success=False, message="早报图片下载失败"
            )
            return False
        self.services.progress.complete_share_progress_step(
            progress_id, "image", "早报图片已下载"
        )
        self.services.progress.update_share_progress(
            progress_id, "send", message="发送中"
        )
        await self.send_event(event, event.image_result(local_path))
        await self.db.add_sent_history(
            self.services.executor_helpers.event_history_target(event),
            HISTORY_SHARE_BRIEFING,
            local_history_text,
            True,
            source_type=history_source,
            **self.services.executor_helpers.image_history_kwargs(local_path),
        )
        self.services.progress.finish_share_progress(
            progress_id, success=True, message="早报分享完成"
        )
        return True

    async def _collect_briefing_images(self) -> list[tuple[str, str, str]]:
        images = []
        if self.extra_shares_conf.get("enable_60s_news", False):
            url = self.news_service.get_60s_image_url()
            if url:
                filename = self.services.delivery_assets.build_news_image_filename(
                    url, "每天60s读世界"
                )
                local_path = (
                    await self.services.delivery_assets.download_image_to_local(
                        url, filename
                    )
                )
                if local_path:
                    images.append(("每天60s读世界", url, local_path))

        if self.extra_shares_conf.get("enable_ai_news", False):
            ai_data = await self.news_service.get_ai_news_json()
            if not ai_data:
                logger.info(
                    "[日常分享] 获取智能资讯快报失败，今日暂无更新，跳过分享图片"
                )
                return images
            url = self.news_service.get_ai_news_image_url()
            if url:
                filename = self.services.delivery_assets.build_news_image_filename(
                    url, "AI资讯快报"
                )
                local_path = (
                    await self.services.delivery_assets.download_image_to_local(
                        url, filename
                    )
                )
                if local_path:
                    images.append(("AI资讯快报", url, local_path))
        return images

    async def _send_briefing_images_to_qzone(
        self,
        images: list[tuple[str, str, str]],
        *,
        progress_id: str,
        history_source: str,
    ) -> bool:
        sent_any = False
        for name, original_url, _local_path in images:
            title = "【每天60秒读懂世界】" if "60s" in name else "【AI资讯快报】"
            try:
                logger.info(f"[日常分享] 正在登录 QQ 空间，准备分享早报 {name}...")
                self.services.progress.update_share_progress(
                    progress_id, "send", message="正在登录 QQ 空间"
                )
                await self.plugin.publish_qzone(text=title, images=[original_url])
                await self.db.add_sent_history(
                    QZONE_TARGET_ID,
                    HISTORY_SHARE_BRIEFING,
                    f"{title}(定时自动)",
                    True,
                    source_type=history_source,
                    **self.services.executor_helpers.image_history_kwargs(original_url),
                )
                await asyncio.sleep(3)
                sent_any = True
                logger.info(f"[日常分享] 分享早报 {name} 到 QQ 空间成功！")
            except Exception as exc:
                logger.error(f"[日常分享] 分享早报 {name} 到 QQ 空间失败: {exc}")
                self.services.progress.fail_share_progress_step(
                    progress_id, "send", f"{name} 发送到 QQ 空间失败"
                )
                await self.db.add_sent_history(
                    QZONE_TARGET_ID,
                    HISTORY_SHARE_BRIEFING,
                    f"{title}(定时自动)失败",
                    False,
                    error_reason=str(exc),
                    source_type=history_source,
                    **self.services.executor_helpers.image_history_kwargs(original_url),
                )
        return sent_any

    async def _send_briefing_images_to_targets(
        self,
        images: list[tuple[str, str, str]],
        targets: list[str],
        *,
        progress_id: str,
        history_source: str,
    ) -> bool:
        sent_any = False
        total_targets = len(targets)
        for target_index, uid in enumerate(targets, 1):
            if self.plugin._is_terminated:
                break
            try:
                target_label = await self.services.targets.get_target_display_name(uid)
                for name, _original_url, local_path in images:
                    logger.info(f"[日常分享] 正在分享 {name} 到 {uid}")
                    self.services.progress.update_share_progress(
                        progress_id,
                        "send",
                        message=f"发送{name}中",
                        extra={
                            "target_id": uid,
                            "target_label": self.services.progress.progress_target_label(
                                uid, target_label
                            ),
                            "total_targets": total_targets,
                            "current_index": target_index,
                        },
                    )
                    await self.services.delivery.send_message_chain(
                        uid, MessageChain().file_image(local_path), None
                    )
                    await self.db.add_sent_history(
                        uid,
                        HISTORY_SHARE_BRIEFING,
                        f"【{name}】早报",
                        True,
                        source_type=history_source,
                        **self.services.executor_helpers.image_history_kwargs(
                            local_path
                        ),
                    )
                    sent_any = True
                    await asyncio.sleep(1)
                await asyncio.sleep(2)
            except Exception as exc:
                logger.error(f"[日常分享] 分享早报到 {uid} 失败: {exc}")
                self.services.progress.fail_share_progress_step(
                    progress_id, "send", "早报发送失败"
                )
                await self.db.add_sent_history(
                    uid,
                    HISTORY_SHARE_BRIEFING,
                    f"早报发送失败: {exc}",
                    False,
                    error_reason=str(exc),
                    source_type=history_source,
                )
        return sent_any

    async def execute_briefing_share(
        self, specific_target: str | None = None, source_type: str = SOURCE_SCHEDULED
    ) -> bool:
        """分享早报：依次发送开启的 60 秒读世界和 AI 资讯。"""
        if self.plugin._is_terminated:
            return False
        history_source = str(source_type or SOURCE_SCHEDULED).strip()

        logger.info("[日常分享] 开始分享早报任务")

        progress_target_label = (
            await self.services.targets.get_target_display_name(specific_target)
            if specific_target
            else ""
        )
        progress_id = self.services.progress.start_share_progress(
            source_type=history_source,
            target_id=specific_target or BRIEFING_TARGET_ID,
            target_label=progress_target_label,
            share_type=HISTORY_SHARE_BRIEFING,
            enabled_steps=["image", "send"],
            message="准备早报",
        )

        self.services.progress.update_share_progress(
            progress_id, "image", message="获取早报图片中"
        )
        images_to_send = await self._collect_briefing_images()

        if not images_to_send:
            logger.warning(
                "[日常分享] 早报任务触发，发现没有开启的早报发送或获取图片失败"
            )
            self.services.progress.finish_share_progress(
                progress_id, success=False, message="未获取到早报图片"
            )
            return False
        self.services.progress.complete_share_progress_step(
            progress_id, "image", "早报图片已获取"
        )

        qzone_sent_any = False
        if specific_target is None and self.extra_shares_conf.get(
            "sync_briefing_to_qzone", False
        ):
            logger.info("[日常分享] 分享早报到 QQ 空间已开启...")
            qzone_sent_any = await self._send_briefing_images_to_qzone(
                images_to_send,
                progress_id=progress_id,
                history_source=history_source,
            )

        if specific_target:
            targets = [specific_target]
        else:
            targets = self.services.targets.get_briefing_targets()
            logger.info(f"[日常分享] 早报将分享到 {len(targets)} 个目标会话")

        if not targets:
            logger.info("[日常分享] 未配置任何早报接收目标，已跳过分享。")
            if qzone_sent_any:
                self.services.progress.finish_share_progress(
                    progress_id, success=True, message="早报已分享到 QQ 空间"
                )
                return True
            self.services.progress.finish_share_progress(
                progress_id, success=False, message="未配置早报接收目标"
            )
            return False

        sent_any = await self._send_briefing_images_to_targets(
            images_to_send,
            targets,
            progress_id=progress_id,
            history_source=history_source,
        )
        self.services.progress.finish_share_progress(
            progress_id,
            success=sent_any or qzone_sent_any,
            message="早报分享完成" if sent_any or qzone_sent_any else "早报分享失败",
        )
        return sent_any or qzone_sent_any

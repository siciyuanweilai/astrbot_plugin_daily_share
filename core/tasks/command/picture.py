from __future__ import annotations

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ...config import ShareType
from ...database.keys import HISTORY_SHARE_NEWS, QZONE_TARGET_ID
from ...toolkit import format_exception, log_exception
from ..taskbase import TaskServiceBase


class TaskCommandImageService(TaskServiceBase):
    async def _send_command_news_long_image(
        self,
        *,
        event: AstrMessageEvent,
        progress_id: str,
        to_qzone: bool,
        news_src_key: str,
        history_source: str,
        finish_progress,
    ) -> bool:
        try:
            self.services.progress.update_share_progress(
                progress_id, "image", message="获取新闻长图中"
            )
            img_url = None
            src_name = ""
            actual_source_key = news_src_key
            if news_src_key:
                img_url, src_name = self.news_service.get_hot_news_image_url(
                    news_src_key
                )
            else:
                random_src = self.news_service.select_news_source()
                actual_source_key = random_src
                img_url, src_name = self.news_service.get_hot_news_image_url(random_src)

            if not img_url:
                self.services.progress.fail_share_progress_step(
                    progress_id, "image", "获取新闻长图失败"
                )
                finish_progress(False, "获取新闻长图失败")
                await self.send_event(event, event.plain_result("获取新闻图片失败。"))
                return False

            self.services.progress.complete_share_progress_step(
                progress_id, "image", "新闻长图已获取"
            )
            snapshot_data = await self.news_service.get_hot_news(
                actual_source_key,
                limit=self.services.snapshots.get_news_snapshot_limit(),
                allow_fallback=False,
            )
            snapshot_payload = (
                self.services.snapshots.news_snapshot_payload(
                    snapshot_data[0], snapshot_data[1]
                )
                if snapshot_data
                else None
            )
            if not snapshot_payload:
                self.services.progress.fail_share_progress_step(
                    progress_id, "image", "获取新闻列表失败"
                )
                finish_progress(False, "获取新闻列表失败")
                await self.send_event(
                    event, event.plain_result("获取新闻列表失败，长图分享已取消。")
                )
                return False

            if to_qzone:
                try:
                    logger.info("[日常分享] 正在登录 QQ 空间...")
                    self.services.progress.update_share_progress(
                        progress_id, "send", message="正在登录 QQ 空间"
                    )
                    await self.plugin.publish_qzone(
                        text=f"【{src_name}】", images=[img_url]
                    )
                    await self.send_event(
                        event,
                        event.plain_result(f"[{src_name}] 图片已成功分享到 QQ 空间！"),
                    )
                    await self.services.executor_helpers.record_share_history(
                        target_id=QZONE_TARGET_ID,
                        share_type=HISTORY_SHARE_NEWS,
                        content=f"【{src_name}】长图（自然语言触发）",
                        success=True,
                        source_type=history_source,
                        image_ref=img_url,
                        news_snapshot_data=snapshot_payload,
                        news_image_url=img_url,
                    )
                    finish_progress(True, "分享完成")
                    return True
                except Exception as e:
                    finish_progress(False, "发送失败")
                    await self.send_event(
                        event,
                        event.plain_result(f"QQ 空间分享失败: {format_exception(e)}"),
                    )
                    return False

            filename = self.services.delivery_assets.build_news_image_filename(
                img_url, src_name
            )
            local_path = await self.services.delivery_assets.download_image_to_local(
                img_url, filename
            )
            if local_path:
                self.services.progress.update_share_progress(
                    progress_id, "send", message="发送中"
                )
                await self.send_event(event, event.image_result(local_path))
                await self.services.executor_helpers.record_share_history(
                    target_id=self.services.executor_helpers.event_history_target(
                        event
                    ),
                    share_type="news",
                    content=f"{src_name} 热搜长图（自然语言触发）",
                    success=True,
                    source_type=history_source,
                    image_ref=local_path,
                    news_snapshot_data=snapshot_payload,
                    news_image_url=local_path,
                )
                finish_progress(True, "分享完成")
                return True

            self.services.progress.fail_share_progress_step(
                progress_id, "image", "新闻长图下载失败"
            )
            finish_progress(False, "新闻长图下载失败")
            await self.send_event(
                event, event.plain_result(f"获取 [{src_name}] 图片下载失败。")
            )
            return False
        except Exception as e:
            log_exception("[日常分享] 获取新闻图片失败", e, with_traceback=False)
            finish_progress(False, "获取新闻长图失败")
            await self.send_event(event, event.plain_result("获取新闻图片失败。"))
            return False

    async def _try_send_command_briefing(
        self,
        *,
        event: AstrMessageEvent,
        st_clean: str,
        to_qzone: bool,
        history_source: str,
    ) -> bool | None:
        if any(k in st_clean for k in ["60s", "六十秒", "读世界"]):
            url = self.news_service.get_60s_image_url()
            if not url:
                await self.send_event(
                    event,
                    event.plain_result("获取每天60s读世界失败，请检查接口密钥配置。"),
                )
                return False
            return await self.services.briefing.send_command_briefing_image(
                event,
                url=url,
                to_qzone=to_qzone,
                qzone_text="【每天60秒读懂世界】",
                qzone_success_text="每天60s读世界已成功分享到 QQ 空间！",
                filename_label="每天60s读世界",
                local_history_text="60s 新闻（自然语言触发）",
                local_fail_text="60s 新闻图片下载失败。",
                history_source=history_source,
            )

        if (
            any(k in st_clean for k in ["ai资讯", "ai新闻", "ai日报"])
            or st_clean == "ai"
        ):
            ai_data = await self.news_service.get_ai_news_json()
            if not ai_data:
                await self.send_event(
                    event,
                    event.plain_result("获取 AI 资讯快报失败，今日暂无更新。"),
                )
                return False
            url = self.news_service.get_ai_news_image_url()
            if not url:
                await self.send_event(
                    event,
                    event.plain_result(
                        "获取 AI 资讯快报图片失败，请检查接口密钥配置。"
                    ),
                )
                return False
            return await self.services.briefing.send_command_briefing_image(
                event,
                url=url,
                to_qzone=to_qzone,
                qzone_text="【AI资讯快报】",
                qzone_success_text="AI 资讯快报已成功分享到 QQ 空间！",
                filename_label="AI资讯快报",
                local_history_text="AI 资讯（自然语言触发）",
                local_fail_text="AI 资讯快报图片下载失败。",
                history_source=history_source,
            )

        return None

    async def _try_send_command_news_image(
        self,
        *,
        event: AstrMessageEvent,
        target_type_enum: ShareType,
        get_image: bool,
        need_image: bool,
        need_voice: bool,
        need_video: bool,
        to_qzone: bool,
        progress_id: str,
        news_src_key: str,
        history_source: str,
        finish_progress,
    ) -> bool | None:
        if target_type_enum != ShareType.NEWS:
            return None
        if not (get_image and not need_image and not need_voice and not need_video):
            return None
        return await self._send_command_news_long_image(
            event=event,
            progress_id=progress_id,
            to_qzone=to_qzone,
            news_src_key=news_src_key,
            history_source=history_source,
            finish_progress=finish_progress,
        )

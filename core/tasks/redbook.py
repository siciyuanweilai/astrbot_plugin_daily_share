from __future__ import annotations

import json

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..config import NEWS_SOURCE_MAP, ShareType
from ..constants import normalize_share_type_sequence, share_type_label
from ..database.keys import (
    HISTORY_SHARE_XIAOHONGSHU,
    SOURCE_COMMAND,
    SOURCE_SCHEDULED,
    XIAOHONGSHU_STATE_KEY,
    XIAOHONGSHU_TARGET_ID,
)
from ..image import GeneratedImage
from ..toolkit import format_exception, log_exception
from ..xhs import XiaohongshuPublishError
from .taskbase import TaskServiceBase


class TaskXiaohongshuService(TaskServiceBase):
    """小红书独立内容生成、媒体准备和发布流程。"""

    def _configured(self) -> bool:
        return bool(str(self.xiaohongshu_conf.get("server_url", "") or "").strip())

    def _default_tags(self) -> list[str]:
        tags = []
        for item in self.xiaohongshu_conf.get("default_tags", []) or []:
            tag = str(item or "").strip().lstrip("#").strip()
            if tag and tag not in tags:
                tags.append(tag[:40])
        return tags[:10]

    async def _metadata(self, content: str, stype: ShareType) -> tuple[str, list[str]]:
        tags = self._default_tags()
        smart_tags_enabled = bool(self.xiaohongshu_conf.get("enable_smart_tags", True))
        smart_count = max(
            1,
            min(int(self.xiaohongshu_conf.get("smart_tag_count", 3) or 3), 8),
        )
        tag_requirement = (
            f"同时生成 {smart_count} 个贴切、自然的话题标签。"
            if smart_tags_enabled
            else "tags 必须返回空数组。"
        )
        prompt = f"""
你是小红书笔记编辑。请根据分享类型和正文，为这篇笔记生成标题和话题标签。

分享类型：{stype.value}
正文：
{str(content or "")[:4000]}

要求：
1. 标题必须概括正文的核心内容，不要直接照抄正文首句。
2. 使用自然中文，不夸张、不营销、不使用标题党。
3. 标题不超过 20 个字符，不要井号、引号、Markdown、序号或解释。
4. {tag_requirement} 标签不要井号、解释、泛化词、重复或营销词。
5. 只返回 JSON 对象，例如：{{"title":"傍晚散步时的小发现","tags":["散步日常","傍晚时光"]}}。
"""
        try:
            result = await self.plugin.call_llm(
                prompt=prompt,
                system_prompt="你只负责生成小红书标题和标签，必须严格返回 JSON 对象。",
                timeout=15,
                max_retries=1,
                umo=XIAOHONGSHU_TARGET_ID,
            )
            raw = str(result or "").strip()
            raw = (
                raw.removeprefix("```json")
                .removeprefix("```")
                .removesuffix("```")
                .strip()
            )
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("小红书元数据返回格式不是对象")
            title = " ".join(str(parsed.get("title", "") or "").splitlines()).strip()
            if not title:
                raise ValueError("智能标题为空")
        except Exception as exc:
            logger.debug(f"[日常分享] 小红书智能标题生成失败，已停止发布: {exc}")
            raise XiaohongshuPublishError("小红书智能标题生成失败，已停止发布") from exc

        if smart_tags_enabled:
            parsed_tags = parsed.get("tags", [])
            if isinstance(parsed_tags, list):
                added = 0
                for item in parsed_tags:
                    tag = str(item or "").strip().lstrip("#").strip()
                    if not tag or tag in tags:
                        continue
                    tags.append(tag[:40])
                    added += 1
                    if len(tags) >= 10 or added >= smart_count:
                        break
            else:
                logger.debug("[日常分享] 小红书智能标签格式无效，继续使用默认标签")
        return title[:20].strip(), tags[:10]

    async def _load_news(
        self,
        *,
        news_source: str | None,
        history_source: str,
        progress_id: str,
    ) -> tuple[list, str] | None:
        state = await self.db.get_share_state(XIAOHONGSHU_STATE_KEY, {})
        source = news_source or self.news_service.select_news_source(
            excluded_source=state.get("last_news_source")
        )
        news_data = await self.news_service.get_hot_news(
            source,
            limit=self.services.snapshots.get_news_snapshot_limit(),
        )
        if news_data:
            await self.db.update_share_state(
                XIAOHONGSHU_STATE_KEY, {"last_news_source": news_data[1]}
            )
            return news_data

        source_name = NEWS_SOURCE_MAP.get(source or "", {}).get("name") or "新闻源"
        message = f"获取新闻失败: {source_name}"
        await self.services.executor_helpers.record_share_failure(
            target_id=XIAOHONGSHU_TARGET_ID,
            share_type=HISTORY_SHARE_XIAOHONGSHU,
            message=message,
            error_reason=message,
            source_type=history_source,
        )
        self.services.progress.finish_share_progress(
            progress_id, success=False, message="获取新闻失败"
        )
        return None

    async def _generate_image(
        self,
        *,
        stype: ShareType,
        content: str,
        life_ctx,
        progress_id: str,
        event: AstrMessageEvent | None,
    ) -> tuple[str | None, str]:
        image_description = ""
        image_enabled_types = normalize_share_type_sequence(
            self.xiaohongshu_conf.get(
                "image_enabled_types", ["问候", "心情", "知识", "推荐"]
            )
        )
        if not self.image_conf.get("enable_ai_image", False):
            self.services.progress.skip_share_progress_step(
                progress_id, "image", "全局配图未开启"
            )
            return None, image_description
        if not self.xiaohongshu_conf.get("enable_image", True):
            self.services.progress.skip_share_progress_step(
                progress_id, "image", "小红书配图未开启"
            )
            return None, image_description
        if stype.value not in image_enabled_types:
            self.services.progress.skip_share_progress_step(
                progress_id, "image", "当前类型未开启配图"
            )
            return None, image_description

        self.services.progress.update_share_progress(
            progress_id, "image", message="小红书配图生成中"
        )
        try:
            generated = await self.image_service.generate_image(
                content,
                stype,
                life_ctx,
                target_umo=XIAOHONGSHU_TARGET_ID,
                event=event,
            )
        except Exception as exc:
            log_exception("[日常分享] 小红书配图生成失败", exc, with_traceback=False)
            self.services.progress.fail_share_progress_step(
                progress_id, "image", "配图生成失败"
            )
            return None, image_description

        if isinstance(generated, GeneratedImage):
            image_description = generated.description
            image_path = generated.path
        else:
            image_path = str(generated or "").strip()
        if image_path:
            self.services.progress.complete_share_progress_step(
                progress_id, "image", "配图已生成"
            )
            return image_path, image_description

        self.services.progress.fail_share_progress_step(
            progress_id, "image", "配图生成失败"
        )
        return None, image_description

    async def _generate_video(
        self,
        *,
        enabled: bool,
        image_path: str | None,
        content: str,
        image_description: str,
        progress_id: str,
        event: AstrMessageEvent | None,
    ) -> str | None:
        if not enabled:
            self.services.progress.skip_share_progress_step(
                progress_id, "video", "小红书视频未开启"
            )
            return None
        if not image_path:
            self.services.progress.skip_share_progress_step(
                progress_id, "video", "未生成首帧图片"
            )
            return None
        self.services.progress.update_share_progress(
            progress_id, "video", message="小红书视频生成中"
        )
        try:
            video_path = await self.image_service.generate_video_from_image(
                image_path,
                content,
                image_description,
                target_umo=XIAOHONGSHU_TARGET_ID,
                event=event,
            )
        except Exception as exc:
            log_exception(
                "[日常分享] 小红书视频生成失败，改发图文", exc, with_traceback=False
            )
            self.services.progress.fail_share_progress_step(
                progress_id, "video", "视频生成失败，改发图文"
            )
            return None
        if video_path:
            self.services.progress.complete_share_progress_step(
                progress_id, "video", "视频已生成"
            )
            return str(video_path)
        self.services.progress.fail_share_progress_step(
            progress_id, "video", "视频生成失败"
        )
        return None

    async def _record_failure(
        self,
        *,
        stype: ShareType,
        content: str,
        history_source: str,
        error: Exception,
        image_path: str | None,
        video_path: str | None,
    ) -> None:
        await self.services.executor_helpers.record_share_history(
            target_id=XIAOHONGSHU_TARGET_ID,
            share_type=stype.value,
            content=content or "小红书发布失败",
            success=False,
            source_type=history_source,
            error_reason=format_exception(error),
            image_ref=image_path,
            video_ref=video_path,
        )

    async def execute_xiaohongshu_share(
        self,
        force_type: ShareType | None = None,
        news_source: str | None = None,
        event: AstrMessageEvent | None = None,
        source_type: str = "",
    ) -> bool:
        """生成一条独立小红书内容，并交给配置的发布服务。"""
        if self.plugin._is_terminated or not self._configured():
            return False

        history_source = str(
            source_type or (SOURCE_COMMAND if event else SOURCE_SCHEDULED)
        ).strip()
        stype = ShareType.GREETING
        content = ""
        image_path = None
        video_path = None
        progress_id = ""
        try:
            period = self.services.executor_helpers.get_curr_period()
            stype = (
                force_type
                or await self.services.type_selector.decide_type_with_state(
                    period,
                    target_id=XIAOHONGSHU_TARGET_ID,
                    specific_type=self.xiaohongshu_conf.get("share_type", "自动"),
                )
            )
            logger.info(
                f"[日常分享] 小红书时段: {period.value}, 类型: {share_type_label(stype)}"
            )
            progress_id = self.services.progress.start_share_progress(
                source_type=history_source,
                target_id=XIAOHONGSHU_TARGET_ID,
                share_type=stype,
                enabled_steps=["content", "image", "video", "send"],
                message="准备发布到小红书",
            )
            life_ctx = await self.ctx_service.get_life_context(XIAOHONGSHU_TARGET_ID)
            news_data = None
            if stype == ShareType.NEWS:
                news_data = await self._load_news(
                    news_source=news_source,
                    history_source=history_source,
                    progress_id=progress_id,
                )
                if news_data is None:
                    return False

            self.services.progress.update_share_progress(
                progress_id, "content", message="小红书文案生成中"
            )
            life_prompt = self.ctx_service.format_life_context(
                life_ctx, stype, False, None
            )
            content = await self.content_service.generate(
                stype,
                period,
                XIAOHONGSHU_TARGET_ID,
                False,
                life_prompt,
                news_data,
                nickname="",
                recent_dynamics=await self.services.executor_helpers.format_recent_dynamics(
                    XIAOHONGSHU_TARGET_ID
                ),
                structured_history="",
            )
            content = str(content or "").strip()
            if not content:
                raise XiaohongshuPublishError("小红书文案生成失败")
            self.services.progress.complete_share_progress_step(
                progress_id, "content", "文案已生成"
            )

            image_path, image_description = await self._generate_image(
                stype=stype,
                content=content,
                life_ctx=life_ctx,
                progress_id=progress_id,
                event=event,
            )
            if self.xiaohongshu_conf.get("require_image", True) and not image_path:
                raise XiaohongshuPublishError("小红书发布需要有效配图")
            video_path = await self._generate_video(
                enabled=bool(self.xiaohongshu_conf.get("enable_video", False)),
                image_path=image_path,
                content=content,
                image_description=image_description,
                progress_id=progress_id,
                event=event,
            )

            self.services.progress.update_share_progress(
                progress_id, "send", message="正在发布到小红书"
            )
            client = self.plugin.xiaohongshu_client
            title, tags = await self._metadata(content, stype)
            publish_args = {
                "title": title,
                "content": content,
                "tags": tags,
                "visibility": self.xiaohongshu_conf.get("visibility", "公开可见"),
            }
            if video_path:
                await client.publish_video(video=video_path, **publish_args)
            else:
                await client.publish(
                    images=[image_path] if image_path else [], **publish_args
                )

            media_kind = "视频" if video_path else "图文"
            logger.info(
                f"[日常分享] 小红书发布成功: 类型={media_kind}, "
                f"标题={publish_args['title']!r}, "
                f"可见范围={publish_args['visibility']}"
            )
            await self.services.executor_helpers.record_share_history(
                target_id=XIAOHONGSHU_TARGET_ID,
                share_type=stype.value,
                content=content,
                success=True,
                source_type=history_source,
                image_ref=image_path,
                video_ref=video_path,
                degradation_reason=self.services.progress.share_progress_degradation_reason(
                    progress_id
                ),
            )
            self.services.progress.finish_share_progress(
                progress_id, success=True, message="小红书发布完成"
            )
            if event:
                try:
                    await self.services.executor_helpers.sync_qzone_result_to_event(
                        event,
                        content,
                        image_path,
                        video_path,
                    )
                except Exception as sync_error:
                    log_exception(
                        "[日常分享] 同步小红书发布结果到会话失败",
                        sync_error,
                        with_traceback=False,
                    )
            return True
        except Exception as exc:
            log_exception("[日常分享] 小红书发布失败", exc, with_traceback=False)
            try:
                await self._record_failure(
                    stype=stype,
                    content=content,
                    history_source=history_source,
                    error=exc,
                    image_path=image_path,
                    video_path=video_path,
                )
            except Exception as record_error:
                log_exception(
                    "[日常分享] 记录小红书失败历史失败",
                    record_error,
                    level="debug",
                    with_traceback=False,
                )
            self.services.progress.finish_share_progress(
                progress_id, success=False, message="小红书发布失败"
            )
            if event:
                await self.send_event(
                    event,
                    event.plain_result(f"小红书发布失败: {format_exception(exc)}"),
                )
            return False


__all__ = ["TaskXiaohongshuService"]

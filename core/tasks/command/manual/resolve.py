from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from ....config import ShareType


class TaskCommandLocalResolveMixin:
    async def _resolve_command_share_type(
        self,
        *,
        event: AstrMessageEvent,
        share_type_text: str,
        st_clean: str,
    ) -> tuple[bool, ShareType | None]:
        if st_clean in ("自动", "auto", ""):
            return True, None
        target_type_enum = self._map_share_type_arg(share_type_text)
        if target_type_enum:
            return True, target_type_enum
        await event.send(
            event.plain_result(
                f"不支持的分享类型：{share_type_text}。支持：自动、问候、新闻、心情、知识、推荐、60s 新闻、AI 资讯。"
            )
        )
        return False, None

    async def _prepare_command_local_target(
        self,
        *,
        event: AstrMessageEvent,
        target_type_enum: ShareType | None,
        history_source: str,
    ) -> tuple[str, str, str, ShareType, str]:
        uid = event.get_sender_id()
        target_umo = event.unified_msg_origin if ":" not in str(uid) else uid
        period = self.get_curr_period()
        if target_type_enum is None:
            target_type_enum = await self.decide_type_with_state(
                period,
                target_id=target_umo,
                specific_type="auto",
            )
        target_is_group = self.ctx_service._is_group_chat(target_umo)
        progress_target_label = await self._get_target_display_name(
            target_umo,
            event=event,
            is_group=target_is_group,
        )
        progress_id = self._start_share_progress(
            source_type=history_source,
            target_id=target_umo,
            target_label=progress_target_label,
            share_type=target_type_enum,
            enabled_steps=["content", "image", "video", "audio", "send"],
            message="准备自然语言分享",
        )
        return uid, target_umo, period, target_type_enum, progress_id

    async def _run_command_qzone_share(
        self,
        *,
        event: AstrMessageEvent,
        target_type_enum: ShareType | None,
        news_src_key: str,
        history_source: str,
        need_video: bool,
    ) -> bool:
        return bool(
            await self.execute_qzone_share(
                force_type=target_type_enum,
                news_source=news_src_key,
                event=event,
                source_type=history_source,
                need_video=need_video,
            )
        )

    async def _command_content_nickname(self, target_umo: str, event: AstrMessageEvent) -> tuple[bool, str]:
        is_group = self.ctx_service._is_group_chat(target_umo)
        nickname = self._get_contact_alias(target_umo, event=event)
        if not is_group:
            nickname = nickname or await self._get_onebot_nickname(target_umo, event=event)
            nickname = nickname or self._clean_nickname_candidate(
                event.get_sender_name(),
                target_umo,
                event=event,
            )
        return is_group, nickname

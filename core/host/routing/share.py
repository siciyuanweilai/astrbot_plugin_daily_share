from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from ...config import ShareType
from ..supportcomponent import SupportComponent


class PluginShareMainRouteService(SupportComponent):
    _XIAOHONGSHU_TARGETS = frozenset({"小红书", "xiaohongshu", "xhs"})

    @classmethod
    def _is_xiaohongshu_target(cls, value: str | None) -> bool:
        return str(value or "").strip().lower() in cls._XIAOHONGSHU_TARGETS

    async def _handle_xiaohongshu_command(
        self, event: AstrMessageEvent, parts: list[str]
    ):
        if not self.permissions._is_admin_event(event):
            yield event.plain_result("权限不足：发布到小红书仅管理员可用。")
            return
        if not str(self.plugin.xiaohongshu_conf.get("server_url", "") or "").strip():
            yield event.plain_result("请先在设置页填写小红书发布服务地址。")
            return

        type_token = str(parts[1] or "").strip()
        force_type = (
            None
            if type_token.lower() in {"自动", "auto"}
            else self.manual._resolve_manual_share_type(type_token)
        )
        if force_type is None and type_token.lower() not in {"自动", "auto"}:
            yield event.plain_result(
                "小红书分享类型无效：自动、问候、新闻、心情、知识、推荐。"
            )
            return
        news_source = (
            self.manual._parse_manual_news_source(parts, start_index=3)
            if force_type == ShareType.NEWS
            else None
        )

        async def run_publish():
            await self.task_manager.xiaohongshu_share.execute_xiaohongshu_share(
                force_type=force_type,
                news_source=news_source,
                event=event,
            )

        started = await self.jobs._start_manual_share_task(
            event,
            specific_target=None,
            global_scope=True,
            task_factory=run_publish,
        )
        if not started:
            yield event.plain_result("小红书发布任务正在进行，请稍后再试。")
            return
        yield event.plain_result("正在生成并发布到小红书，请稍候...")

    async def handle_share_command(self, event: AstrMessageEvent):
        raw_parts = event.message_str.strip().split()
        if len(raw_parts) > 2 and self._is_xiaohongshu_target(raw_parts[2]):
            async for result in self._handle_xiaohongshu_command(event, raw_parts):
                yield result
            return
        if len(raw_parts) > 1 and self._is_xiaohongshu_target(raw_parts[1]):
            yield event.plain_result(
                "小红书指令格式已更新，请使用：/分享 [类型] 小红书"
            )
            return
        parts, arg, is_broadcast, is_qzone_target = (
            self.manual._parse_share_command_parts(event)
        )
        self.permissions._remember_event_adapter(event)

        if len(parts) == 1:
            yield event.plain_result(
                "指令格式错误，请指定参数。\n示例：/分享 新闻\n可加后缀：广播、空间"
            )
            return

        allowed, denial = await self.manual._check_share_command_permission(
            event,
            arg=arg,
            is_broadcast=is_broadcast,
            is_qzone_target=is_qzone_target,
        )
        if not allowed:
            yield denial
            return

        current_uid = event.unified_msg_origin
        specific_target, share_global_scope = self.manual._manual_share_scope(
            current_uid,
            is_broadcast=is_broadcast,
            is_qzone_target=is_qzone_target,
        )

        if arg in {"60s", "ai"}:
            async for result in self.briefing_route._handle_manual_briefing_command(
                event,
                arg=arg,
                is_broadcast=is_broadcast,
                is_qzone_target=is_qzone_target,
                specific_target=specific_target,
                share_global_scope=share_global_scope,
            ):
                yield result
            return

        is_config_command, command_iter = await self.manual._route_share_config_command(
            event, arg, parts
        )
        if is_config_command:
            async for result in command_iter:
                yield result
            return

        if arg in ["自动", "auto"]:
            async for result in self.typed_route._handle_manual_auto_share_command(
                event,
                parts=parts,
                is_broadcast=is_broadcast,
                is_qzone_target=is_qzone_target,
                specific_target=specific_target,
                share_global_scope=share_global_scope,
            ):
                yield result
            return

        async for result in self.typed_route._dispatch_manual_typed_command(
            event,
            arg=arg,
            parts=parts,
            current_uid=current_uid,
            is_broadcast=is_broadcast,
            is_qzone_target=is_qzone_target,
            specific_target=specific_target,
            share_global_scope=share_global_scope,
        ):
            yield result

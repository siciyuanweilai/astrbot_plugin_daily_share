from __future__ import annotations

from ..supportcomponent import SupportComponent

from astrbot.api.event import AstrMessageEvent


class PluginShareMainRouteService(SupportComponent):
    async def handle_share_command(self, event: AstrMessageEvent):
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

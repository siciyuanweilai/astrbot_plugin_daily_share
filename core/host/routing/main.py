from __future__ import annotations

from astrbot.api.event import AstrMessageEvent


class PluginShareMainRouteMixin:
    async def _handle_share_main_impl(self, event: AstrMessageEvent):
        parts, arg, is_broadcast, is_qzone_target = self._parse_share_command_parts(event)
        self._remember_event_adapter(event)

        if len(parts) == 1:
            yield event.plain_result("指令格式错误，请指定参数。\n示例：/分享 新闻\n可加后缀：广播、空间")
            return

        allowed, denial = await self._check_share_command_permission(
            event,
            arg=arg,
            is_broadcast=is_broadcast,
            is_qzone_target=is_qzone_target,
        )
        if not allowed:
            yield denial
            return

        current_uid = event.unified_msg_origin
        specific_target, share_global_scope = self._manual_share_scope(
            current_uid,
            is_broadcast=is_broadcast,
            is_qzone_target=is_qzone_target,
        )

        if arg in {"60s", "ai"}:
            async for result in self._handle_manual_briefing_command(
                event,
                arg=arg,
                is_broadcast=is_broadcast,
                is_qzone_target=is_qzone_target,
                specific_target=specific_target,
                share_global_scope=share_global_scope,
            ):
                yield result
            return

        is_config_command, command_iter = await self._route_share_config_command(event, arg, parts)
        if is_config_command:
            async for result in command_iter:
                yield result
            return

        if arg in ["自动", "auto"]:
            async for result in self._handle_manual_auto_share_command(
                event,
                parts=parts,
                is_broadcast=is_broadcast,
                is_qzone_target=is_qzone_target,
                specific_target=specific_target,
                share_global_scope=share_global_scope,
            ):
                yield result
            return

        async for result in self._dispatch_manual_typed_command(
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

from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from ..config import NEWS_SOURCE_MAP, ShareType
from ..constants import CMD_CN_MAP, SOURCE_CN_MAP


class PluginManualShareMixin:
    @staticmethod
    def _manual_share_target_desc(*, is_broadcast: bool, is_qzone_target: bool) -> str:
        if is_qzone_target:
            return "QQ空间"
        return "配置的所有群聊和私聊" if is_broadcast else "当前会话"

    def _manual_share_scope(self, current_uid: str, *, is_broadcast: bool, is_qzone_target: bool) -> tuple[str | None, bool]:
        return (None if is_broadcast else current_uid), bool(is_broadcast or is_qzone_target)

    async def _check_share_command_permission(
        self,
        event: AstrMessageEvent,
        *,
        arg: str,
        is_broadcast: bool,
        is_qzone_target: bool,
    ) -> tuple[bool, object | None]:
        is_admin = self._is_admin_event(event)
        is_configured_receiver = self._is_configured_receiver_event(event)
        admin_only_args = {"开启", "关闭", "早报空间", "添加当前", "昵称"}

        if arg in admin_only_args or is_broadcast or is_qzone_target:
            if not is_admin:
                return False, event.plain_result("权限不足：该操作会修改全局配置、广播或发布QQ空间，仅管理员可用。")
        elif not (is_admin or is_configured_receiver):
            return False, self._plain_permission_denied(event)
        return True, None

    async def _route_share_config_command(self, event: AstrMessageEvent, arg: str, parts: list[str]):
        routes = {
            "早报空间": lambda: self.command_handler.cmd_briefing_qzone_sync(event, parts),
            "昵称": lambda: self.command_handler.cmd_contact_alias(event, parts),
            "添加当前": lambda: self.command_handler.cmd_add_current(event, parts),
            "状态": lambda: self.command_handler.cmd_status(event),
            "开启": lambda: self.command_handler.cmd_enable(event),
            "关闭": lambda: self.command_handler.cmd_disable(event),
            "重置序列": lambda: self.command_handler.cmd_reset_seq(event),
            "查看序列": lambda: self.command_handler.cmd_view_seq(event),
            "帮助": lambda: self.command_handler.cmd_help(event),
            "指定序列": lambda: self.command_handler.cmd_set_seq(event, parts),
        }
        factory = routes.get(arg)
        if not factory:
            return False, None
        return True, factory()

    def _parse_manual_news_source(self, parts: list[str]) -> str | None:
        for part in parts[2:]:
            if part in ["图片", "广播", "空间"]:
                continue
            if part in SOURCE_CN_MAP:
                return SOURCE_CN_MAP[part]
            if part in NEWS_SOURCE_MAP:
                return part
        return None

    def _resolve_manual_share_type(self, arg: str) -> ShareType | None:
        if arg in CMD_CN_MAP:
            return CMD_CN_MAP[arg]
        try:
            return ShareType(arg)
        except ValueError:
            return None

    def _parse_share_command_parts(self, event: AstrMessageEvent) -> tuple[list[str], str, bool, bool]:
        parts = event.message_str.strip().split()
        arg = parts[1].lower() if len(parts) > 1 else ""
        return parts, arg, "广播" in parts, "空间" in parts

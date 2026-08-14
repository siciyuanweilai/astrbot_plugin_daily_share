from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from .supportcomponent import SupportComponent


class PluginPermissionService(SupportComponent):
    """处理工具事件解析和插件权限判断。"""

    def _remember_event_adapter(self, event: AstrMessageEvent) -> None:
        if event is None:
            return
        try:
            origin = str(event.unified_msg_origin or "").strip()
            if not origin:
                return
            adapter_id = origin.split(":", 1)[0].strip()
            if not adapter_id:
                return
            self._cached_adapter_id = adapter_id
            is_weixin = self.ctx_service.is_weixin_event(
                event
            ) and self.ctx_service.is_weixin_platform(origin)
            if is_weixin:
                self._cached_weixin_adapter_id = adapter_id
            elif str(event.get_sender_id() or "").strip().isdigit():
                self._cached_qq_adapter_id = adapter_id
        except Exception as exc:
            logger.debug(f"[日常分享] 记录事件平台失败: {exc}")

    def _is_admin_event(self, event: AstrMessageEvent) -> bool:
        if event is None:
            return False
        try:
            return bool(event.is_admin())
        except Exception as exc:
            logger.debug(f"[日常分享] 读取事件管理员状态失败: {exc}")
            return False

    def _event_sender_id(self, event: AstrMessageEvent) -> str:
        if event is None:
            return ""
        try:
            sender_id = str(event.get_sender_id() or "").strip()
            if sender_id.isdigit():
                return sender_id
            _, real_id = self.ctx_service.parse_umo(event.unified_msg_origin)
            real_id = str(real_id or "").strip()
            return real_id if real_id.isdigit() else ""
        except Exception as exc:
            logger.debug(f"[日常分享] 读取事件发送者失败: {exc}")
            return ""

    def target_entry_matches(
        self, entry, origin: str, real_id: str, extra_candidates=None
    ) -> bool:
        """按完整统一消息来源标识判断配置目标是否匹配当前会话。"""
        value = str(entry).strip().replace("，", ":")
        origin = str(origin or "").strip()
        if not value or not origin:
            return False
        if value == origin:
            return True
        parsed = self.task_manager.targets.parse_targets_config([value])
        return origin in parsed

    def _parsed_target_matches(self, target_id: str, candidates: set[str]) -> bool:
        return target_id in candidates

    def _is_configured_receiver_event(self, event: AstrMessageEvent) -> bool:
        if event is None:
            return False
        try:
            origin = str(event.unified_msg_origin or "").strip()
            if not origin:
                return False
            is_group = self.ctx_service.is_group_chat(origin)
            if self.ctx_service.is_weixin_event(
                event
            ) and self.ctx_service.is_weixin_platform(origin):
                is_group = False
            receiver_key = "groups" if is_group else "users"
            receiver_map = self.task_manager.targets.parse_targets_config(
                self.receiver_conf.get(receiver_key, []), expected_group=is_group
            )
            if origin in receiver_map:
                return True
            extra_key = "briefing_groups" if is_group else "briefing_users"
            extra_map = self.task_manager.targets.parse_targets_config(
                self.extra_shares_conf.get(extra_key, []), expected_group=is_group
            )
            return origin in extra_map
        except Exception as exc:
            logger.warning(f"[日常分享] 接收对象权限判断失败: {exc}")
            return False

    def _entries_match_receiver(self, entries, candidates: list[str]) -> bool:
        origin, real_id, sender_id = candidates
        values = entries.keys() if isinstance(entries, dict) else entries
        return any(
            self.permissions.target_entry_matches(
                entry,
                origin,
                real_id,
                [sender_id],
            )
            for entry in values
        )

    def _plain_permission_denied(self, event: AstrMessageEvent, reason: str = ""):
        if event is None:
            raise RuntimeError("无法解析当前消息事件")
        suffix = f"\n{reason}" if reason else ""
        return event.plain_result(
            "权限不足：当前会话不在接收对象配置中。"
            "请先把当前会话加入群聊、私聊或早报接收目标。"
            f"{suffix}"
        )

    @staticmethod
    def _has_reply_component(event: AstrMessageEvent) -> bool:
        return any(
            component.__class__.__name__ == "Reply"
            for component in event.get_messages()
        )

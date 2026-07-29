from astrbot.api.event import AstrMessageEvent

from ...platform import (
    ONEBOT_PLATFORM_TYPES,
    WEIXIN_PLATFORM_TYPE,
    PlatformBinding,
    get_platform_bindings,
    parse_platform_session,
)
from .names import TaskTargetIdentityService


class TaskTargetPlatformService(TaskTargetIdentityService):
    def get_target_platform_bindings(self) -> list[PlatformBinding]:
        """返回主动发送平台的完整能力记录，包含重复标识诊断。"""
        try:
            return get_platform_bindings(self.plugin.context)
        except Exception:
            return []

    def get_target_platform_candidates(self, *, expected_group: bool) -> list[str]:
        """返回当前支持主动发送的目标平台实例标识。"""
        return [
            binding.route_id
            for binding in self.get_target_platform_bindings()
            if binding.supports_proactive
            and not binding.conflicted
            and (not expected_group or binding.supports_group)
        ]

    @staticmethod
    def _narrow_target_platform_bindings(
        bindings: list[PlatformBinding],
        *,
        session_id: str,
        expected_group: bool,
    ) -> list[PlatformBinding]:
        compatible = [
            binding
            for binding in bindings
            if binding.supports_proactive
            and (not expected_group or binding.supports_group)
        ]
        probe = str(session_id or "").strip().lower()
        if probe.endswith(("@im.wechat", "@chatroom")):
            weixin = [
                binding
                for binding in compatible
                if binding.platform_type == WEIXIN_PLATFORM_TYPE
            ]
            if weixin:
                return weixin
        if probe.isdigit():
            onebot = [
                binding
                for binding in compatible
                if binding.platform_type in ONEBOT_PLATFORM_TYPES
            ]
            if onebot:
                return onebot
        return compatible

    def select_target_platform_binding(
        self,
        *,
        session_id: str,
        expected_group: bool,
        route_id: str = "",
    ) -> PlatformBinding:
        """按内部路由、消息类型和目标标识选择唯一平台实例。"""
        bindings = self.get_target_platform_bindings()
        selected = str(route_id or "").strip()
        exact_route = [binding for binding in bindings if binding.route_id == selected]
        if exact_route:
            matches = exact_route
        elif selected:
            matches = [
                binding for binding in bindings if binding.platform_id == selected
            ]
        else:
            matches = bindings

        matches = self._narrow_target_platform_bindings(
            matches,
            session_id=session_id,
            expected_group=expected_group,
        )
        if not matches:
            if not selected:
                raise ValueError("当前没有可绑定的机器人实例")
            identity = selected or "当前配置"
            raise ValueError(f"机器人实例当前不可用: {identity}")
        if len(matches) > 1:
            if any(binding.conflicted for binding in matches):
                identity = matches[0].platform_id or selected
                raise ValueError(
                    f"机器人实例 ID 冲突：“{identity}”在同一平台类型中重复，"
                    "请在平台配置中使用不同的 ID"
                )
            raise ValueError("检测到多个机器人实例，请选择要发送的机器人")

        binding = matches[0]
        if binding.conflicted:
            raise ValueError(
                f"机器人实例 ID 冲突：“{binding.platform_id}”在同一平台类型中重复，"
                "请在平台配置中使用不同的 ID"
            )
        if expected_group and not binding.supports_group:
            raise ValueError(
                f"{binding.platform_type or binding.platform_id} 仅支持私聊目标"
            )
        return binding

    def ensure_target_platform_routable(
        self,
        target_umo: str,
        *,
        expected_group: bool | None = None,
    ) -> PlatformBinding:
        """确保统一消息来源标识能唯一映射到具备对应发送能力的平台实例。"""
        session = parse_platform_session(target_umo)
        if not session:
            raise ValueError("目标必须是完整的会话标识")
        if expected_group is not None and session.is_group != expected_group:
            expected = "群聊" if expected_group else "私聊"
            raise ValueError(f"目标消息类型必须是{expected}")

        return self.select_target_platform_binding(
            session_id=session.session_id,
            expected_group=session.is_group,
            route_id=session.platform_id,
        )

    def _select_platform_instance_for_target(self, target_umo: str):
        """只按统一消息来源标识中的平台实例标识精确选择平台。"""
        session = parse_platform_session(target_umo)
        if not session:
            return None
        try:
            return self.ensure_target_platform_routable(target_umo).instance
        except ValueError as exc:
            if "当前不可用" in str(exc):
                return None
            raise

    def event_matches_target(self, event: AstrMessageEvent, target_umo: str) -> bool:
        """仅在事件与发送目标是同一个完整统一消息来源标识时复用事件发送。"""
        if not event:
            return False
        origin = str(getattr(event, "unified_msg_origin", "") or "")
        return bool(origin and origin == str(target_umo or "").strip())

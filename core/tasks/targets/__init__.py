from ..taskbase import TaskServiceBase
from .adapterio import TaskTargetPlatformService
from .names import TaskTargetIdentityService
from .rule import TaskTargetConfigService


class TaskTargetService(TaskServiceBase):
    """目标解析、平台选择和显示名辅助能力聚合。"""

    def get_contact_alias(self, target_uid, event=None):
        return self.identity.get_contact_alias(target_uid, event)

    def clean_nickname_candidate(self, nickname, target_uid, event=None):
        return self.identity.clean_nickname_candidate(nickname, target_uid, event)

    async def get_target_display_name(self, target_uid, event=None, is_group=None):
        """获取任务进度里展示用的目标名称。"""
        return await self.identity.get_target_display_name(target_uid, event, is_group)

    async def get_onebot_nickname(self, target_uid, event=None):
        return await self.identity.get_onebot_nickname(target_uid, event)

    async def _get_onebot_group_name(self, target_uid, event=None):
        return await self.identity._get_onebot_group_name(target_uid, event)

    def get_target_platform_bindings(self):
        """返回主动发送平台的完整能力记录，包含重复标识诊断。"""
        return self.platform.get_target_platform_bindings()

    def get_target_platform_candidates(self, *, expected_group):
        """返回当前支持主动发送的目标平台实例标识。"""
        return self.platform.get_target_platform_candidates(
            expected_group=expected_group
        )

    @staticmethod
    def _narrow_target_platform_bindings(bindings, *, session_id, expected_group):
        return TaskTargetPlatformService._narrow_target_platform_bindings(
            bindings, session_id=session_id, expected_group=expected_group
        )

    def select_target_platform_binding(
        self, *, session_id, expected_group, route_id=""
    ):
        """按内部路由、消息类型和目标标识选择唯一平台实例。"""
        return self.platform.select_target_platform_binding(
            session_id=session_id, expected_group=expected_group, route_id=route_id
        )

    def ensure_target_platform_routable(self, target_umo, *, expected_group=None):
        """确保统一消息来源标识能唯一映射到具备对应发送能力的平台实例。"""
        return self.platform.ensure_target_platform_routable(
            target_umo, expected_group=expected_group
        )

    def _select_platform_instance_for_target(self, target_umo):
        """只按统一消息来源标识中的平台实例标识精确选择平台。"""
        return self.platform._select_platform_instance_for_target(target_umo)

    def event_matches_target(self, event, target_umo):
        """仅在事件与发送目标是同一个完整统一消息来源标识时复用事件发送。"""
        return self.platform.event_matches_target(event, target_umo)

    def is_full_umo(self, value):
        """判断是否为框架运行时使用的统一消息来源标识。"""
        return self.rules.is_full_umo(value)

    def normalize_target_umo(self, value, *, expected_group=None):
        """校验并规范化目标统一消息来源标识。"""
        return self.rules.normalize_target_umo(value, expected_group=expected_group)

    def resolve_target_input(
        self, value, *, expected_group, adapter_id="", original_umo=""
    ):
        """把面板中的会话标识和平台选择解析为完整统一消息来源标识。"""
        return self.rules.resolve_target_input(
            value,
            expected_group=expected_group,
            adapter_id=adapter_id,
            original_umo=original_umo,
        )

    def looks_like_share_sequence(self, value):
        """判断字符串是否像分享类型序列。"""
        return self.rules.looks_like_share_sequence(value)

    def normalize_share_sequence(self, value):
        """把配置中的分享类型序列统一保存为中文值。"""
        return self.rules.normalize_share_sequence(value)

    def looks_like_cron(self, value):
        """判断字符串是否像定时表达式、预设名或 HH:MM 时间。"""
        return self.rules.looks_like_cron(value)

    def normalize_cron_value(self, value):
        """把更友好的 HH:MM 时间转换成定时表达式，其他定时表达式/预设保持原样。"""
        return self.rules.normalize_cron_value(value)

    def get_target_conf(self, target_umo, is_group, r_groups, r_users):
        """按完整统一消息来源标识查找目标的独立配置。"""
        return self.rules.get_target_conf(target_umo, is_group, r_groups, r_users)

    def is_unsupported_weixin_group_target(self, target_umo, is_group):
        """个人微信适配器基于 openclaw-weixin，只支持一对一私聊。"""
        return self.rules.is_unsupported_weixin_group_target(target_umo, is_group)

    def parse_targets_config(self, conf_list, *, expected_group=None):
        """解析完整统一消息来源标识、独立定时和类型序列。"""
        return self.rules.parse_targets_config(conf_list, expected_group=expected_group)

    def _parse_target_config_item(self, item, *, expected_group=None):
        return self.rules._parse_target_config_item(item, expected_group=expected_group)

    def _target_id_and_cron(self, parts):
        return self.rules._target_id_and_cron(parts)

    def get_broadcast_targets(self, exclude_custom_cron=False, target_scope="all"):
        """辅助方法：获取需要广播的目标列表。exclude_custom_cron 启用时会跳过有独立时间的群"""
        return self.rules.get_broadcast_targets(exclude_custom_cron, target_scope)

    def _broadcast_target_entries(self, entries, is_group, exclude_custom_cron):
        return self.rules._broadcast_target_entries(
            entries, is_group, exclude_custom_cron
        )

    def get_briefing_targets(self):
        """获取早报的独立广播目标，不填则不发"""
        return self.rules.get_briefing_targets()

    def __init__(self, runtime, config, state) -> None:
        super().__init__(runtime, config, state)
        self.identity = TaskTargetIdentityService(self)
        self.platform = TaskTargetPlatformService(self)
        self.rules = TaskTargetConfigService(self)

from .basic import CommandBasicService
from .commandbase import CommandServiceBase
from .receiver import CommandTargetsService
from .sequence import CommandSequenceService


class CommandHandler(CommandServiceBase):
    def __init__(self, plugin):
        super().__init__(plugin)
        self.basic = CommandBasicService(self)
        self.targets = CommandTargetsService(self)
        self.sequence = CommandSequenceService(self)

    async def cmd_enable(self, event):
        """启用插件"""
        async for result in self.basic.cmd_enable(event):
            yield result

    async def cmd_disable(self, event):
        """禁用插件"""
        async for result in self.basic.cmd_disable(event):
            yield result

    async def cmd_status(self, event):
        """查看详细状态"""
        async for result in self.basic.cmd_status(event):
            yield result

    async def cmd_briefing_qzone_sync(self, event, parts):
        """开启/关闭分享早报到 QQ 空间。"""
        async for result in self.basic.cmd_briefing_qzone_sync(event, parts):
            yield result

    async def cmd_help(self, event):
        async for result in self.basic.cmd_help(event):
            yield result

    def _get_sendable_current_target(self, event, target_uid):
        """配置中保存框架事件提供的完整统一消息来源标识。"""
        return self.targets._get_sendable_current_target(event, target_uid)

    def _find_matching_target_index(self, target_list, origin, real_id, candidates):
        return self.targets._find_matching_target_index(
            target_list, origin, real_id, candidates
        )

    async def cmd_contact_alias(self, event, parts):
        """设置当前会话的本地昵称映射。"""
        async for result in self.targets.cmd_contact_alias(event, parts):
            yield result

    async def cmd_add_current(self, event, parts):
        """把当前会话加入接收对象配置。"""
        async for result in self.targets.cmd_add_current(event, parts):
            yield result

    def _current_share_sequence(self, parts):
        return self.targets._current_share_sequence(parts)

    async def _add_current_briefing(self, target_uid, sendable_target_uid, is_group):
        return await self.targets._add_current_briefing(
            target_uid, sendable_target_uid, is_group
        )

    async def _add_current_receiver(
        self, target_uid, sendable_target_uid, is_group, seq
    ):
        return await self.targets._add_current_receiver(
            target_uid, sendable_target_uid, is_group, seq
        )

    def _upsert_current_target(
        self, target_list, target_uid, new_entry, is_group, *, seq=None, briefing=False
    ):
        return self.targets._upsert_current_target(
            target_list, target_uid, new_entry, is_group, seq=seq, briefing=briefing
        )

    async def cmd_reset_seq(self, event):
        """重置序列（支持分离当前会话和 QQ 空间）"""
        async for result in self.sequence.cmd_reset_seq(event):
            yield result

    async def cmd_view_seq(self, event):
        """查看序列详情"""
        async for result in self.sequence.cmd_view_seq(event):
            yield result

    async def cmd_set_seq(self, event, parts):
        """指定序列子命令"""
        async for result in self.sequence.cmd_set_seq(event, parts):
            yield result

from .newsitem import TaskExecutorNewsService
from ...platform import parse_platform_session


class TaskExecutorTargetService(TaskExecutorNewsService):
    """分享目标解析。"""

    def resolve_execute_share_targets(
        self,
        specific_target: str | None = None,
        target_scope: str = "all",
        *,
        exclude_custom_cron: bool = True,
    ) -> list[str]:
        if specific_target:
            return [specific_target]
        return self.services.targets.get_broadcast_targets(
            exclude_custom_cron=exclude_custom_cron,
            target_scope=target_scope,
        )

    @staticmethod
    def _target_looks_group(target_umo: str) -> bool:
        session = parse_platform_session(target_umo)
        return bool(session and session.is_group)

    def _target_share_type_config(
        self, target_umo: str, is_group: bool, r_groups: dict, r_users: dict
    ):
        target_specific_type = self.basic_conf.get("share_type", "自动")
        conf = self.services.targets.get_target_conf(
            target_umo, is_group, r_groups, r_users
        )
        if conf is None:
            return target_specific_type
        st = conf.get("seq") if isinstance(conf, dict) else conf
        return st if st is not None else target_specific_type

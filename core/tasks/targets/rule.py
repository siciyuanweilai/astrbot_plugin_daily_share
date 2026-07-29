from astrbot.api import logger

from .adapterio import TaskTargetPlatformService

from ...config import CRON_TEMPLATES
from ...constants import canonical_share_type_sequence, normalize_share_type_sequence
from ...platform import parse_platform_session


class TaskTargetConfigService(TaskTargetPlatformService):
    def is_full_umo(self, value: str) -> bool:
        """判断是否为框架运行时使用的统一消息来源标识。"""
        return parse_platform_session(value) is not None

    def normalize_target_umo(
        self, value: str, *, expected_group: bool | None = None
    ) -> str:
        """校验并规范化目标统一消息来源标识。"""
        session = parse_platform_session(value)
        if not session:
            raise ValueError("目标必须是 /sid 输出的完整会话标识")
        if expected_group is not None and session.is_group != expected_group:
            expected = "GroupMessage" if expected_group else "FriendMessage"
            raise ValueError(f"目标消息类型必须是 {expected}")
        return str(session)

    def resolve_target_input(
        self,
        value: str,
        *,
        expected_group: bool,
        adapter_id: str = "",
        original_umo: str = "",
    ) -> str:
        """把面板中的会话标识和平台选择解析为完整统一消息来源标识。"""
        raw = str(value or "").strip()
        selected = str(adapter_id or "").strip()
        original = str(original_umo or "").strip()
        if not raw:
            raise ValueError("QQ 号或群号不能为空")

        parsed = parse_platform_session(raw)
        if parsed:
            target = self.normalize_target_umo(raw, expected_group=expected_group)
            binding = self.ensure_target_platform_routable(
                (
                    f"{selected}:{parsed.message_type}:{parsed.session_id}"
                    if selected
                    else target
                ),
                expected_group=expected_group,
            )
            if selected and parsed.platform_id not in {
                binding.platform_id,
                binding.route_id,
            }:
                raise ValueError("选择的机器人实例与会话标识不一致")
            return f"{binding.platform_id}:{parsed.message_type}:{parsed.session_id}"

        if ":" in selected:
            raise ValueError("机器人实例 ID 不能包含冒号")

        if selected:
            try:
                binding = self.select_target_platform_binding(
                    session_id=raw,
                    expected_group=expected_group,
                    route_id=selected,
                )
            except ValueError:
                original_session = parse_platform_session(original)
                if (
                    original_session
                    and original_session.platform_id == selected
                    and original_session.session_id == raw
                    and original_session.is_group == expected_group
                ):
                    return str(original_session)
                raise
        else:
            binding = self.select_target_platform_binding(
                session_id=raw,
                expected_group=expected_group,
            )
        message_type = "GroupMessage" if expected_group else "FriendMessage"
        return f"{binding.platform_id}:{message_type}:{raw}"

    def looks_like_share_sequence(self, value: str) -> bool:
        """判断字符串是否像分享类型序列。"""
        if not value:
            return False
        parts = [p.strip() for p in value.replace("，", ",").split(",") if p.strip()]
        normalized = normalize_share_type_sequence(value, allow_auto=True)
        return bool(parts) and len(parts) == len(normalized)

    def normalize_share_sequence(self, value: str) -> str:
        """把配置中的分享类型序列统一保存为中文值。"""
        return ",".join(canonical_share_type_sequence(value, allow_auto=True))

    def looks_like_cron(self, value: str) -> bool:
        """判断字符串是否像定时表达式、预设名或 HH:MM 时间。"""
        if not value:
            return False
        if self.services.schedule.clock_time_to_cron(value):
            return True
        return (
            value in CRON_TEMPLATES
            or self.services.schedule.parse_cron_to_kwargs(
                CRON_TEMPLATES.get(value, value)
            )
            is not None
        )

    def normalize_cron_value(self, value: str) -> str:
        """把更友好的 HH:MM 时间转换成定时表达式，其他定时表达式/预设保持原样。"""
        raw = str(value or "").strip()
        return self.services.schedule.clock_time_to_cron(raw) or raw

    def get_target_conf(
        self, target_umo: str, is_group: bool, r_groups: dict, r_users: dict
    ):
        """按完整统一消息来源标识查找目标的独立配置。"""
        conf_map = r_groups if is_group else r_users
        return conf_map.get(target_umo)

    def is_unsupported_weixin_group_target(
        self, target_umo: str, is_group: bool
    ) -> bool:
        """个人微信适配器基于 openclaw-weixin，只支持一对一私聊。"""
        return bool(is_group and self.ctx_service.is_weixin_platform(target_umo))

    def parse_targets_config(self, conf_list, *, expected_group: bool | None = None):
        """解析完整统一消息来源标识、独立定时和类型序列。"""
        if isinstance(conf_list, dict):
            return conf_list
        res = {}
        if isinstance(conf_list, list):
            for item in conf_list:
                parsed = self._parse_target_config_item(
                    item, expected_group=expected_group
                )
                if parsed:
                    target_id, target_conf = parsed
                    res[target_id] = target_conf
        return res

    def _parse_target_config_item(self, item, *, expected_group: bool | None = None):
        text = str(item).strip().replace("：", ":")
        if not text:
            return None
        parts = [part.strip() for part in text.split(":")]
        has_config_suffix = len(parts) > 3 and self.looks_like_share_sequence(parts[-1])
        if not has_config_suffix and self.is_full_umo(text):
            try:
                target_umo = self.normalize_target_umo(
                    text, expected_group=expected_group
                )
            except ValueError as exc:
                logger.warning(f"[日常分享] 目标配置无效，已跳过: {text}。{exc}")
                return None
            return target_umo, {"cron": None, "seq": None}
        if len(parts) == 1:
            logger.warning(
                f"[日常分享] 目标配置无效，已跳过: {text}。"
                "请填写 /sid 输出的完整会话标识"
            )
            return None
        if not self.looks_like_share_sequence(parts[-1]):
            logger.warning(
                f"[日常分享] 目标配置类型序列无效，已跳过: {text}。"
                "请使用中文类型：问候、新闻、心情、知识、推荐。"
            )
            return None
        target_id, cron_str = self._target_id_and_cron(parts)
        if not target_id:
            return None
        try:
            target_umo = self.normalize_target_umo(
                target_id, expected_group=expected_group
            )
        except ValueError as exc:
            logger.warning(f"[日常分享] 目标配置无效，已跳过: {text}。{exc}")
            return None
        return target_umo, {
            "cron": cron_str,
            "seq": self.normalize_share_sequence(parts[-1]),
        }

    def _target_id_and_cron(self, parts: list[str]) -> tuple[str, str | None]:
        clock_time = f"{parts[-3]}:{parts[-2]}" if len(parts) >= 4 else ""
        if clock_time and self.services.schedule.clock_time_to_cron(clock_time):
            return ":".join(parts[:-3]).strip(), self.normalize_cron_value(clock_time)
        if len(parts) >= 3 and self.looks_like_cron(parts[-2]):
            return ":".join(parts[:-2]).strip(), self.normalize_cron_value(parts[-2])
        return ":".join(parts[:-1]).strip(), None

    def get_broadcast_targets(
        self, exclude_custom_cron=False, target_scope: str = "all"
    ):
        """辅助方法：获取需要广播的目标列表。exclude_custom_cron 启用时会跳过有独立时间的群"""
        scope = str(target_scope or "all").strip().lower()
        include_groups = scope in {"all", "groups", "group"}
        include_users = scope in {"all", "users", "user", "private"}

        r_groups = self.parse_targets_config(
            self.receiver_conf.get("groups", []), expected_group=True
        )
        r_users = self.parse_targets_config(
            self.receiver_conf.get("users", []), expected_group=False
        )
        targets = []
        if include_groups:
            targets.extend(
                self._broadcast_target_entries(r_groups, True, exclude_custom_cron)
            )
        if include_users:
            targets.extend(
                self._broadcast_target_entries(r_users, False, exclude_custom_cron)
            )
        return targets

    def _broadcast_target_entries(
        self, entries: dict, is_group: bool, exclude_custom_cron: bool
    ) -> list[str]:
        targets = []
        for target_id, conf in entries.items():
            if not target_id or (
                exclude_custom_cron and isinstance(conf, dict) and conf.get("cron")
            ):
                continue
            if self.is_unsupported_weixin_group_target(target_id, is_group):
                logger.warning(
                    f"[日常分享] 个人微信平台不支持群聊，已跳过广播目标: {target_id}"
                )
                continue
            targets.append(target_id)
        return targets

    def get_briefing_targets(self):
        """获取早报的独立广播目标，不填则不发"""
        targets = []
        b_groups = self.parse_targets_config(
            self.extra_shares_conf.get("briefing_groups", []), expected_group=True
        )
        b_users = self.parse_targets_config(
            self.extra_shares_conf.get("briefing_users", []), expected_group=False
        )
        for target_umo in b_groups:
            if self.is_unsupported_weixin_group_target(target_umo, True):
                logger.warning(
                    f"[日常分享] 个人微信平台不支持群聊，已跳过早报群聊目标: {target_umo}"
                )
                continue
            targets.append(target_umo)
        targets.extend(b_users)

        return targets

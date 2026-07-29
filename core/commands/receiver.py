from astrbot.api.event import AstrMessageEvent

from .basic import CommandBasicService


class CommandTargetsService(CommandBasicService):
    def _get_sendable_current_target(
        self, event: AstrMessageEvent, target_uid: str
    ) -> str:
        """配置中保存框架事件提供的完整统一消息来源标识。"""
        return str(target_uid or "").strip()

    def _find_matching_target_index(
        self, target_list: list, origin: str, real_id: str, candidates: list
    ) -> int:
        for idx, item in enumerate(target_list):
            if self.plugin.target_entry_matches(item, origin, real_id, candidates):
                return idx
        return -1

    async def cmd_contact_alias(self, event: AstrMessageEvent, parts: list):
        """设置当前会话的本地昵称映射。"""
        target_uid = str(event.unified_msg_origin or "").strip()
        sendable_target_uid = self._get_sendable_current_target(event, target_uid)

        if len(parts) <= 2 or parts[2] in {"查看", "show", "list"}:
            alias = self.plugin.get_contact_alias(target_uid, event=event)
            if alias:
                yield event.plain_result(
                    f"当前会话昵称映射：{sendable_target_uid} -> {alias}"
                )
            else:
                yield event.plain_result(
                    "当前会话暂未设置昵称映射。\n设置示例：/分享 昵称 测试昵称"
                )
            return

        if parts[2] in {"删除", "清除", "移除", "delete", "remove"}:
            removed = await self.plugin.save_config_and_refresh_runtime(
                mutation=lambda: self.plugin.remove_contact_alias(
                    target_uid, event=event
                ),
                rebuild_scheduler=False,
            )
            if removed:
                yield event.plain_result("已删除当前会话昵称映射。")
            else:
                yield event.plain_result("当前会话没有可删除的昵称映射。")
            return

        alias = " ".join(parts[2:]).strip()
        if not alias:
            yield event.plain_result("昵称不能为空。示例：/分享 昵称 测试昵称")
            return

        save_key = await self.plugin.save_config_and_refresh_runtime(
            mutation=lambda: self.plugin.set_contact_alias(
                sendable_target_uid, alias, event=event
            ),
            rebuild_scheduler=False,
        )
        if not save_key:
            yield event.plain_result("设置失败：无法获取当前会话标识。")
            return

        yield event.plain_result(f"已设置当前会话昵称映射：{save_key} -> {alias}")

    async def cmd_add_current(self, event: AstrMessageEvent, parts: list):
        """把当前会话加入接收对象配置。"""
        target_uid = str(event.unified_msg_origin or "").strip()
        if not target_uid:
            yield event.plain_result("添加失败：无法获取当前会话标识。")
            return

        sendable_target_uid = self._get_sendable_current_target(event, target_uid)
        mode = parts[2].strip().lower() if len(parts) > 2 else ""
        is_briefing_mode = mode in {"早报", "briefing", "brief", "60s", "ai"}
        is_group = self.plugin.ctx_service.is_group_chat(target_uid)
        if self.plugin.ctx_service.is_weixin_platform(target_uid):
            is_group = False

        if is_briefing_mode:
            if len(parts) > 3:
                yield event.plain_result(
                    "早报接收对象不需要类型序列。示例：/分享 添加当前 早报"
                )
                return
            msg = await self._add_current_briefing(
                target_uid, sendable_target_uid, is_group
            )
            yield event.plain_result(msg)
            return

        seq = self._current_share_sequence(parts)
        if seq is False:
            yield event.plain_result(
                "类型序列格式不正确。示例：/分享 添加当前 心情,新闻\n添加早报示例：/分享 添加当前 早报"
            )
            return

        msg = await self._add_current_receiver(
            target_uid, sendable_target_uid, is_group, seq
        )
        yield event.plain_result(msg)

    def _current_share_sequence(self, parts: list):
        if len(parts) <= 2:
            return None
        candidate = parts[2].strip().replace("，", ",")
        targets = self.plugin.task_manager.targets
        if not targets.looks_like_share_sequence(candidate):
            return False
        return targets.normalize_share_sequence(candidate)

    async def _add_current_briefing(
        self, target_uid: str, sendable_target_uid: str, is_group: bool
    ) -> str:
        def add_target() -> str:
            extra_conf = self.config.setdefault("extra_shares", {})
            groups = extra_conf.setdefault("briefing_groups", [])
            users = extra_conf.setdefault("briefing_users", [])
            target_list = groups if is_group else users
            return self._upsert_current_target(
                target_list,
                target_uid,
                sendable_target_uid,
                is_group,
                briefing=True,
            )

        return await self.plugin.save_config_and_refresh_runtime(mutation=add_target)

    async def _add_current_receiver(
        self, target_uid: str, sendable_target_uid: str, is_group: bool, seq
    ) -> str:
        def add_target() -> str:
            receiver_conf = self.config.setdefault("receiver", {})
            groups = receiver_conf.setdefault("groups", [])
            users = receiver_conf.setdefault("users", [])
            target_list = groups if is_group else users
            new_entry = f"{sendable_target_uid}:{seq}" if seq else sendable_target_uid
            return self._upsert_current_target(
                target_list, target_uid, new_entry, is_group, seq=seq
            )

        return await self.plugin.save_config_and_refresh_runtime(mutation=add_target)

    def _upsert_current_target(
        self,
        target_list: list,
        target_uid: str,
        new_entry: str,
        is_group: bool,
        *,
        seq=None,
        briefing: bool = False,
    ) -> str:
        _, real_id = self.plugin.ctx_service.parse_umo(target_uid)
        sendable_id = target_uid
        _, sendable_real_id = self.plugin.ctx_service.parse_umo(sendable_id)
        index = self._find_matching_target_index(
            target_list, target_uid, real_id, [sendable_id, sendable_real_id]
        )
        label = "早报接收对象" if briefing else "接收对象"
        if index < 0:
            target_list.append(new_entry)
            message = f"已添加当前{'群聊' if is_group else '私聊'}到{label}。"
            return message + (f"\n分享类型序列：{seq}" if seq else "")
        current = str(target_list[index]).strip().replace("：", ":")
        if current == new_entry and not seq:
            return f"当前会话已经在{label}配置中。"
        target_list[index] = new_entry
        if briefing:
            return f"当前会话已在早报接收对象中，已更新为简写标识：{new_entry}"
        suffix = f"并设置分享类型序列为：{seq}" if seq else f"：{new_entry}"
        return f"当前会话已在接收对象中，已更新为简写标识{suffix}"

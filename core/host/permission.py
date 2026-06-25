from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent


class PluginPermissionMixin:
    def _resolve_message_event(self, event_or_context):
        """从 AstrBot 消息事件或工具运行上下文中取出消息事件。"""
        current = event_or_context
        seen = set()
        for _ in range(4):
            if current is None:
                return None

            marker = id(current)
            if marker in seen:
                return None
            seen.add(marker)

            if hasattr(current, "unified_msg_origin"):
                return current

            context = getattr(current, "context", None)
            nested_event = getattr(context, "event", None)
            if nested_event is not None:
                return nested_event

            direct_event = getattr(current, "event", None)
            if direct_event is not None:
                return direct_event

            if context is None or context is current:
                return None
            current = context

        return None

    def _remember_event_adapter(self, event: AstrMessageEvent):
        """记录最近见过的平台标识，供纯标识配置选择 QQ 或微信适配器。"""
        try:
            event = self._resolve_message_event(event)
            if event is None:
                return

            origin = str(getattr(event, "unified_msg_origin", "") or "").strip()
            if not origin:
                return

            adapter_id = origin.split(":", 1)[0].strip()
            if adapter_id:
                self._cached_adapter_id = adapter_id
                if (
                    self.ctx_service._is_weixin_oc_event(event)
                    and self.ctx_service._is_weixin_platform(origin)
                ):
                    self._cached_weixin_adapter_id = adapter_id
                else:
                    try:
                        sender_id = str(event.get_sender_id() or "").strip()
                    except Exception:
                        sender_id = ""
                    if sender_id.isdigit():
                        self._cached_qq_adapter_id = adapter_id
        except Exception as e:
            logger.debug(f"[每日分享] 记录事件平台失败: {e}")

    def _is_admin_event(self, event: AstrMessageEvent) -> bool:
        """按 AstrBot 当前事件角色判断插件内部权限。"""
        try:
            event = self._resolve_message_event(event)
            if event is None:
                return False

            try:
                if hasattr(event, "is_admin") and event.is_admin():
                    return True
            except Exception as e:
                logger.debug(f"[每日分享] 管理员检查读取事件角色失败: {e}")

            return str(getattr(event, "role", "") or "").strip().lower() == "admin"
        except Exception as e:
            logger.debug(f"[每日分享] 管理员检查失败: {e}")
            return False

    def _target_entry_matches(self, entry, origin: str, real_id: str, extra_candidates=None) -> bool:
        s = str(entry).strip().replace("：", ":")
        if not s:
            return False

        candidates = {str(c).strip() for c in [origin, real_id] + list(extra_candidates or []) if str(c or "").strip()}
        if s in candidates:
            return True

        parsed = self.task_manager._parse_targets_config([s])
        for target_id in parsed.keys():
            if target_id in candidates:
                return True
            _, target_real_id = self.ctx_service._parse_umo(target_id)
            if target_real_id and target_real_id in candidates:
                return True
        return False

    def _is_configured_receiver_event(self, event: AstrMessageEvent) -> bool:
        """当前会话在接收对象配置中时，允许使用手动分享类命令。"""
        try:
            event = self._resolve_message_event(event)
            if event is None:
                return False

            origin = str(getattr(event, "unified_msg_origin", "") or "").strip()
            if not origin:
                return False

            is_group = self.ctx_service._is_group_chat(origin)
            if (
                self.ctx_service._is_weixin_oc_event(event)
                and self.ctx_service._is_weixin_platform(origin)
            ):
                is_group = False
            _, real_id = self.ctx_service._parse_umo(origin)
            try:
                sender_id = str(event.get_sender_id() or "").strip()
            except Exception:
                sender_id = ""
            receiver_map = self.task_manager._parse_targets_config(
                self.receiver_conf.get("groups" if is_group else "users", [])
            )
            if (
                origin in receiver_map
                or (real_id and real_id in receiver_map)
                or (sender_id and sender_id in receiver_map)
            ):
                return True
            for entry in receiver_map.keys():
                if self._target_entry_matches(entry, origin, real_id, [sender_id]):
                    return True

            extra_key = "briefing_groups" if is_group else "briefing_users"
            for entry in self.extra_shares_conf.get(extra_key, []):
                if self._target_entry_matches(entry, origin, real_id, [sender_id]):
                    return True

            return False
        except Exception as e:
            logger.warning(f"[每日分享] 接收对象权限判断失败: {e}")
            return False

    def _plain_permission_denied(self, event: AstrMessageEvent, reason: str = ""):
        event = self._resolve_message_event(event) or event
        suffix = f"\n{reason}" if reason else ""
        return event.plain_result(
            "权限不足：当前会话不在接收对象配置中。"
            "请先把当前会话加入群聊、私聊或早报接收目标。"
            f"{suffix}"
        )

    def _has_reply_component(self, event: AstrMessageEvent) -> bool:
        try:
            messages = event.get_messages()
        except Exception:
            messages = getattr(getattr(event, "message_obj", None), "message", []) or []
        for comp in messages or []:
            if comp.__class__.__name__ == "Reply":
                return True
            if str(getattr(comp, "type", "")).lower().endswith("reply"):
                return True
        return False

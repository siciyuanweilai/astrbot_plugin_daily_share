from .shared import (
    DAILY_SHARE_INTERNAL_TRIGGER,
    DAILY_SHARE_MEMORY_PROMPT,
    logger,
)


class ContextMemoryMixin:
    def _clean_share_text_for_memory(self, content: str) -> str:
        return str(content or "").strip()

    def _build_share_memory_text(self, content: str, image_desc: str = None) -> str:
        full_text = self._clean_share_text_for_memory(content)

        if image_desc:
            tag = f"[配图: {image_desc}]" if self.image_conf.get("record_image_description", True) else "[已发送配图]"
            full_text += f"\n{tag}"
        elif image_desc is not None:
            full_text += "\n[已发送配图]"

        return full_text.strip()

    def _build_daily_life_memos_meta(self, target_umo: str) -> dict:
        target = str(target_umo or "").strip()
        adapter_id, real_id = self._parse_umo(target)
        is_group = self._is_group_chat(target)
        meta = {
            "session_id": target or real_id or "daily_share",
            "platform": adapter_id or "",
            "is_group": "true" if is_group else "false",
        }
        if is_group:
            meta["group_id"] = real_id or target
        else:
            meta["sender_profile_id"] = real_id or target
        return meta

    async def record_bot_reply_to_history(self, target_umo: str, content: str, image_desc: str = None):
        """
        将机器人主动发送的消息写入 AstrBot 框架的对话历史中。
        """
        if not target_umo: return

        clean_content = self._clean_share_text_for_memory(content)
        final_content = clean_content
        if image_desc:
            final_content += f"\n\n[发送了一张配图: {image_desc}]"

        try:
            conv_manager = getattr(self.context, "conversation_manager", None)
            if not conv_manager or not hasattr(conv_manager, "add_message_pair"):
                logger.warning("[上下文] 当前 AstrBot 版本过低，不支持追加对话消息，无法写入消息历史。")
                return
            
            # 获取或创建会话标识。
            conversation_id = await conv_manager.get_curr_conversation_id(target_umo)
            if not conversation_id:
                conversation_id = await conv_manager.new_conversation(target_umo)
            
            # 使用内部标记保留成对历史，同时避免把主动分享误识别为用户真实发言。
            user_msg = {
                "role": "user",
                "content": [{"type": "text", "text": DAILY_SHARE_INTERNAL_TRIGGER}],
            }
            assistant_msg = {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": final_content,
                    }
                ],
            }
            
            await conv_manager.add_message_pair(
                cid=conversation_id,
                user_message=user_msg,
                assistant_message=assistant_msg,
            )
            logger.debug(f"[上下文] 已写入历史: {target_umo}")
            
        except Exception as e:
            logger.warning(f"[上下文] 写入对话历史失败: {e}")

    async def record_to_memos(self, target_umo: str, content: str, image_desc: str = None):
        if not self.memory_conf.get("record_share_to_memory", True): return
        plugin = self._get_life_plugin()
        runtime = getattr(plugin, "runtime", None)
        schedule = getattr(runtime, "schedule_memos_selected_items", None)
        if not callable(schedule):
            logger.debug("[上下文] daily_life MemOS 未就绪，跳过分享长期记忆。")
            return

        full_text = self._build_share_memory_text(content, image_desc)
        if not full_text:
            return

        try:
            scheduled = schedule(
                self._build_daily_life_memos_meta(target_umo),
                [full_text],
                reason=DAILY_SHARE_MEMORY_PROMPT,
                user_message=DAILY_SHARE_MEMORY_PROMPT,
                marker=full_text,
            )
            if scheduled:
                logger.debug(f"[上下文] 已交给 daily_life 同步 MemOS: {target_umo}")
        except Exception as e:
            logger.warning(f"[上下文] 记录到 daily_life MemOS 失败: {e}")

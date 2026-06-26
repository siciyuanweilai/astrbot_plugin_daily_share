import json

from .shared import (
    DAILY_SHARE_MEMORY_PROMPT,
    DAILY_SHARE_SOURCE,
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

    def _conversation_history_list(self, conversation) -> list:
        raw = getattr(conversation, "history", []) if conversation else []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw or "[]")
            except json.JSONDecodeError:
                return []
        return list(raw) if isinstance(raw, list) else []

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
        if not target_umo:
            return

        final_parts = []
        clean_content = self._clean_share_text_for_memory(content)
        if clean_content:
            final_parts.append(clean_content)
        if image_desc:
            final_parts.append(f"[发送了一张配图: {image_desc}]")

        final_content = "\n\n".join(final_parts).strip()
        if not final_content:
            return

        try:
            conv_manager = getattr(self.context, "conversation_manager", None)
            get_curr = getattr(conv_manager, "get_curr_conversation_id", None)
            get_conversation = getattr(conv_manager, "get_conversation", None)
            update_conversation = getattr(conv_manager, "update_conversation", None)
            if not (conv_manager and callable(get_curr) and callable(get_conversation) and callable(update_conversation)):
                logger.warning("[上下文] 当前 AstrBot 版本不支持直接更新对话历史，无法写入分享历史。")
                return

            conversation_id = await get_curr(target_umo)
            if not conversation_id:
                new_conversation = getattr(conv_manager, "new_conversation", None)
                if not callable(new_conversation):
                    return
                conversation_id = await new_conversation(target_umo)

            conversation = await get_conversation(target_umo, conversation_id)
            history = self._conversation_history_list(conversation)
            history.append(
                {
                    "role": "assistant",
                    "content": final_content,
                    "source": DAILY_SHARE_SOURCE,
                }
            )

            await update_conversation(target_umo, conversation_id, history=history)
            logger.debug(f"[上下文] 已写入分享历史: {target_umo}")

        except Exception as e:
            logger.warning(f"[上下文] 写入对话历史失败: {e}")

    async def record_to_memos(self, target_umo: str, content: str, image_desc: str = None):
        if not self.memory_conf.get("record_share_to_memory", True):
            return
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

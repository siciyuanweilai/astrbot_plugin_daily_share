from __future__ import annotations

from ..shared import Any, Dict, List, asyncio, datetime, logger, time


class ContextHistoryOnebotFetchMixin:
    """从 OneBot 主动接口读取聊天历史。"""

    async def _fetch_deep_history(self, bot, target_id: int, is_group: bool, hours: int = 24, max_count: int = 100) -> List[Dict]:
        """深度回溯获取更早的聊天历史记录。"""
        all_messages = []
        seen_ids = set()
        per_page = min(max_count + 20, 100)
        cursor_seq = 0
        try:
            effective_hours = max(1, min(int(hours), 168))
        except Exception:
            effective_hours = 24
        cutoff_time = time.time() - (effective_hours * 3600)
        max_rounds = 20

        action = "get_group_msg_history" if is_group else "get_friend_msg_history"
        id_key = "group_id" if is_group else "user_id"

        for round_idx in range(max_rounds):
            if len(all_messages) >= max_count:
                break

            try:
                if round_idx > 0:
                    await asyncio.sleep(0.5)

                params = {id_key: target_id, "count": per_page}
                if cursor_seq > 0:
                    params["message_seq"] = cursor_seq

                resp = await self._bot_call_action(bot, action, **params)
                if isinstance(resp, dict):
                    batch_msgs = resp.get("messages", [])
                elif isinstance(resp, list):
                    batch_msgs = resp
                else:
                    break
                if not batch_msgs:
                    break

                batch_seqs = []
                added_count = 0
                for msg in batch_msgs:
                    seq = msg.get("message_seq") or msg.get("message_id")
                    if seq is not None:
                        try:
                            batch_seqs.append(int(seq))
                        except (TypeError, ValueError):
                            logger.debug(f"[每日分享] 跳过无法解析的消息序号: {seq}")

                    mid = msg.get("message_id")
                    if mid is None:
                        mid = f"{msg.get('time')}-{msg.get('sender',{}).get('user_id')}"
                    mid_str = str(mid)

                    if mid_str not in seen_ids:
                        seen_ids.add(mid_str)
                        msg_time = int(msg.get("time", 0))
                        if msg_time >= cutoff_time:
                            all_messages.append(msg)
                            added_count += 1

                if not batch_seqs:
                    break

                min_seq_in_batch = min(batch_seqs)
                if added_count == 0 and round_idx > 0:
                    break
                if cursor_seq != 0 and min_seq_in_batch >= cursor_seq:
                    break
                cursor_seq = min_seq_in_batch

            except Exception as e:
                err_str = str(e)
                if "不存在" in err_str or getattr(e, "retcode", 0) == 1200:
                    logger.debug(f"[每日分享] 历史记录翻到底了: {err_str}")
                else:
                    logger.warning(f"[每日分享] 获取历史中断: {e}")
                break

        all_messages.sort(key=lambda x: x.get("time", 0))
        return all_messages[-max_count:]

    async def _fetch_onebot_raw_history(self, bot, real_id: str, is_group: bool, *, enable_deep: bool, history_hours: int, max_count: int) -> list:
        if enable_deep:
            raw_msgs = await self._fetch_deep_history(
                bot,
                int(real_id),
                is_group=is_group,
                hours=history_hours,
                max_count=max_count,
            )
            logger.info(f"[每日分享] 聊天历史记录获取成功: {len(raw_msgs)} 条")
            return raw_msgs

        action = "get_group_msg_history" if is_group else "get_friend_msg_history"
        key = "group_id" if is_group else "user_id"
        result = await self._bot_call_action(bot, action, **{key: int(real_id), "count": max_count})
        return result.get("messages", []) if isinstance(result, dict) else (result or [])

    async def _onebot_login_uin(self, bot) -> str:
        try:
            login_info = await self._bot_call_action(bot, "get_login_info")
            if login_info and isinstance(login_info, dict):
                return str(login_info.get("user_id", ""))
        except Exception as e:
            logger.debug(f"[每日分享] 获取登录信息失败: {e}")
        return ""

    def _normalize_onebot_history_messages(self, raw_msgs: list, bot_qq: str) -> list[dict[str, str]]:
        messages = []
        for msg in raw_msgs:
            sender_data = msg.get("sender", {})
            msg_uid = str(sender_data.get("user_id", ""))

            raw_content = ""
            if "message" in msg and isinstance(msg["message"], list):
                raw_content = "".join(
                    seg["data"]["text"] for seg in msg["message"] if seg["type"] == "text"
                ).strip()
            elif "raw_message" in msg:
                raw_content = str(msg["raw_message"])
            if not raw_content:
                continue

            role = "assistant" if (bot_qq and msg_uid == bot_qq) else "user"
            ts = msg.get("time")
            try:
                ts_str = datetime.datetime.fromtimestamp(ts).isoformat() if isinstance(ts, (int, float)) else ""
            except Exception:
                ts_str = ""
            messages.append({"role": role, "content": raw_content, "timestamp": ts_str, "user_id": msg_uid})
        return messages

    async def _get_onebot_history_data(self, target_umo: str, real_id: str, is_group: bool, bot) -> Dict[str, Any]:
        enable_deep = self.history_conf.get("enable_deep_history", True)
        history_hours = min(int(self.history_conf.get("deep_history_hours", 24)), 168)
        max_count = int(
            self.history_conf.get("deep_history_max_count", 80)
            if is_group
            else self.history_conf.get("private_history_count", 20)
        )

        try:
            logger.info(f"[每日分享] 正在获取 {real_id} 的聊天历史记录 (模式: {'群聊' if is_group else '私聊'}, 目标: {max_count}条)...")
            try:
                raw_msgs = await self._fetch_onebot_raw_history(
                    bot,
                    real_id,
                    is_group,
                    enable_deep=enable_deep,
                    history_hours=history_hours,
                    max_count=max_count,
                )
            except Exception as e:
                logger.warning(f"[每日分享] 获取聊天历史记录失败: {e}")
                return await self._get_astrbot_saved_history_data(target_umo, is_group)

            messages = self._normalize_onebot_history_messages(raw_msgs, await self._onebot_login_uin(bot))
            if not messages:
                return {}

            result = {"messages": messages, "is_group": is_group}
            if is_group:
                result["group_info"] = self._analyze_group_chat(messages)
            return result
        except Exception as e:
            logger.warning(f"[每日分享] 接口获取历史出错: {e}")
            return await self._get_astrbot_saved_history_data(target_umo, is_group)

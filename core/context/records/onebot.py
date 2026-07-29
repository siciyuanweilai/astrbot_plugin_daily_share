from __future__ import annotations

from ..contextbase import ContextComponent

from ..shared import Any, Dict, List, asyncio, datetime, logger, time


class ContextHistoryOnebotFetchService(ContextComponent):
    """从 OneBot 主动接口读取聊天历史。"""

    async def _fetch_deep_history(
        self, bot, target_id: int, is_group: bool, hours: int = 24, max_count: int = 100
    ) -> List[Dict]:
        """深度回溯获取更早的聊天历史记录。"""
        all_messages: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        per_page = min(max_count + 20, 100)
        cursor_seq = 0
        effective_hours = self._history_effective_hours(hours)
        cutoff_time = time.time() - (effective_hours * 3600)
        action = "get_group_msg_history" if is_group else "get_friend_msg_history"
        id_key = "group_id" if is_group else "user_id"

        for round_idx in range(20):
            if len(all_messages) >= max_count:
                break
            try:
                if round_idx > 0:
                    await asyncio.sleep(0.5)
                params = {id_key: target_id, "count": per_page}
                if cursor_seq > 0:
                    params["message_seq"] = cursor_seq
                resp = await self.call_onebot_action(bot, action, **params)
                batch_msgs = self._history_page_messages(resp)
                if not batch_msgs:
                    break
                batch_seqs, added_count = self._merge_history_batch(
                    batch_msgs,
                    all_messages=all_messages,
                    seen_ids=seen_ids,
                    cutoff_time=cutoff_time,
                )
                if self._history_page_should_stop(
                    batch_seqs,
                    added_count=added_count,
                    round_idx=round_idx,
                    cursor_seq=cursor_seq,
                ):
                    break
                cursor_seq = min(batch_seqs)

            except Exception as e:
                err_str = str(e)
                if "不存在" in err_str or getattr(e, "retcode", 0) == 1200:
                    logger.debug(f"[日常分享] 历史记录翻到底了: {err_str}")
                else:
                    logger.warning(f"[日常分享] 获取历史中断: {e}")
                break

        all_messages.sort(key=lambda x: x.get("time", 0))
        return all_messages[-max_count:]

    @staticmethod
    def _history_page_should_stop(
        sequences: list[int], *, added_count: int, round_idx: int, cursor_seq: int
    ) -> bool:
        if not sequences:
            return True
        if added_count == 0 and round_idx > 0:
            return True
        return bool(cursor_seq and min(sequences) >= cursor_seq)

    @staticmethod
    def _history_effective_hours(hours: int) -> int:
        try:
            return max(1, min(int(hours), 168))
        except (TypeError, ValueError):
            return 24

    @staticmethod
    def _history_page_messages(response) -> list[dict]:
        if isinstance(response, dict):
            return response.get("messages", []) or []
        return response if isinstance(response, list) else []

    @staticmethod
    def _merge_history_batch(
        messages: list[dict],
        *,
        all_messages: list[dict],
        seen_ids: set[str],
        cutoff_time: float,
    ) -> tuple[list[int], int]:
        sequences: list[int] = []
        added_count = 0
        for message in messages:
            sequence = message.get("message_seq") or message.get("message_id")
            if sequence is not None:
                try:
                    sequences.append(int(sequence))
                except (TypeError, ValueError):
                    logger.debug(f"[日常分享] 跳过无法解析的消息序号: {sequence}")

            message_id = message.get("message_id")
            if message_id is None:
                sender_id = (message.get("sender") or {}).get("user_id")
                message_id = f"{message.get('time')}-{sender_id}"
            message_key = str(message_id)
            if message_key in seen_ids:
                continue
            seen_ids.add(message_key)
            if int(message.get("time", 0)) >= cutoff_time:
                all_messages.append(message)
                added_count += 1
        return sequences, added_count

    async def _fetch_onebot_raw_history(
        self,
        bot,
        real_id: str,
        is_group: bool,
        *,
        enable_deep: bool,
        history_hours: int,
        max_count: int,
    ) -> list:
        if enable_deep:
            raw_msgs = await self._fetch_deep_history(
                bot,
                int(real_id),
                is_group=is_group,
                hours=history_hours,
                max_count=max_count,
            )
            logger.info(f"[日常分享] 聊天历史记录获取成功: {len(raw_msgs)} 条")
            return raw_msgs

        action = "get_group_msg_history" if is_group else "get_friend_msg_history"
        key = "group_id" if is_group else "user_id"
        result = await self.call_onebot_action(
            bot, action, **{key: int(real_id), "count": max_count}
        )
        return (
            result.get("messages", []) if isinstance(result, dict) else (result or [])
        )

    async def _onebot_login_uin(self, bot) -> str:
        try:
            login_info = await self.call_onebot_action(bot, "get_login_info")
            if login_info and isinstance(login_info, dict):
                return str(login_info.get("user_id", ""))
        except Exception as e:
            logger.debug(f"[日常分享] 获取登录信息失败: {e}")
        return ""

    def _normalize_onebot_history_messages(
        self, raw_msgs: list, bot_qq: str
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for msg in raw_msgs:
            sender_data = msg.get("sender", {}) or {}
            msg_uid = str(sender_data.get("user_id", "") or "").strip()

            payload = self._extract_history_payload(
                msg.get("message") or msg.get("raw_message") or msg.get("message", [])
            )
            raw_content = str(payload.get("content") or "").strip()
            if not raw_content:
                continue

            role = "assistant" if (bot_qq and msg_uid == bot_qq) else "user"
            ts = msg.get("time")
            try:
                ts_str = (
                    datetime.datetime.fromtimestamp(ts).isoformat()
                    if isinstance(ts, (int, float))
                    else ""
                )
            except Exception:
                ts_str = ""

            sender_name = str(
                sender_data.get("nickname")
                or sender_data.get("card")
                or sender_data.get("name")
                or ""
            ).strip()
            messages.append(
                {
                    "role": role,
                    "content": raw_content,
                    "timestamp": ts_str,
                    "user_id": msg_uid,
                    "name": sender_name,
                    "source": "chat",
                    "message_id": str(
                        msg.get("message_id")
                        or msg.get("message_seq")
                        or payload.get("message_id")
                        or ""
                    ).strip(),
                    "media": str(payload.get("media") or "").strip(),
                    "reply_to_id": str(payload.get("reply_to_id") or "").strip(),
                    "reply_to_name": str(payload.get("reply_to_name") or "").strip(),
                    "reply_to_content": str(
                        payload.get("reply_to_content") or ""
                    ).strip(),
                    "at_targets": list(payload.get("at_targets") or []),
                }
            )
        return messages

    async def _get_onebot_history_data(
        self, target_umo: str, real_id: str, is_group: bool, bot
    ) -> Dict[str, Any]:
        enable_deep = self.history_conf.get("enable_deep_history", True)
        history_hours = min(int(self.history_conf.get("deep_history_hours", 24)), 168)
        max_count = int(
            self.history_conf.get("deep_history_max_count", 80)
            if is_group
            else self.history_conf.get("private_history_count", 20)
        )

        try:
            logger.info(
                f"[日常分享] 正在获取 {real_id} 的聊天历史记录 (模式: {'群聊' if is_group else '私聊'}, 目标: {max_count}条)..."
            )
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
                logger.warning(f"[日常分享] 获取聊天历史记录失败: {e}")
                return await self._get_astrbot_saved_history_data(target_umo, is_group)

            messages = self._normalize_onebot_history_messages(
                raw_msgs, await self._onebot_login_uin(bot)
            )
            if not messages:
                return {}

            result = {"messages": messages, "is_group": is_group}
            if is_group:
                result["group_info"] = self._analyze_group_chat(messages)
            return result
        except Exception as e:
            logger.warning(f"[日常分享] 接口获取历史出错: {e}")
            return await self._get_astrbot_saved_history_data(target_umo, is_group)

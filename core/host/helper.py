import re
import time

from astrbot.api import logger

from ..config import NEWS_SOURCE_MAP
from ..constants import SOURCE_CN_MAP
from .supportcomponent import SupportComponent


class PluginToolContextService(SupportComponent):
    _NEWS_LINK_CONTEXT_MARKER = "# 每日分享新闻缓存上下文"
    _QZONE_CONTEXT_MARKER = "# 每日分享 QQ 空间上下文"
    _QZONE_CONTEXT_TTL_SECONDS = 1800

    def _strip_news_link_reference_tail(self, text: str) -> str:
        """移除 news_link 自然回复末尾由模型补出的参考链接列表。"""
        if not text:
            return text

        match = re.search(
            r"\n\s*(?:#{1,6}\s*)?(?:参考链接|参考来源|参考资料|引用来源|References?)\s*[:：]?\s*\n",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return text

        tail = text[match.end() :]
        if not re.search(r"https?://", tail, flags=re.IGNORECASE):
            return text

        return text[: match.start()].rstrip()

    def _extract_news_link_urls(self, text: str) -> list[str]:
        """提取工具结果中已生成的链接，用于防止最终回复漏掉链接。"""
        urls = []
        for match in re.finditer(
            r"https?://[^\s<>\]）)。,，；;]+", str(text or ""), flags=re.IGNORECASE
        ):
            url = match.group(0).rstrip(".,，。；;:：")
            if url and url not in urls:
                urls.append(url)
        return urls

    def _ensure_news_link_urls_in_reply(self, reply: str, urls: list[str]) -> str:
        """如果大语言模型最终回复漏掉 news_link 返回的链接，在末尾补齐。"""
        text = str(reply or "")
        missing = [url for url in urls or [] if url and url not in text]
        if not missing:
            return text
        suffix = "\n".join(missing)
        if text.strip():
            return f"{text.rstrip()}\n{suffix}"
        return suffix

    def _resolve_news_source_name(self, source: str | None = None):
        token = str(source or "").strip()
        if not token:
            return None

        token_lower = token.lower()
        if token in SOURCE_CN_MAP:
            return SOURCE_CN_MAP[token]
        if token_lower in NEWS_SOURCE_MAP:
            return token_lower

        for name, key in SOURCE_CN_MAP.items():
            if token in name or name in token:
                return key
        return None

    async def _build_news_link_context_prompt(self, target_uid: str) -> str:
        """为大语言模型追加最近新闻缓存状态，帮助它更稳地调用 news_link。"""
        manager = self.task_manager
        db = self.db
        snapshot_store = manager.snapshot_store

        target = str(target_uid or "").strip()
        if not target:
            return ""

        try:
            focus_key = snapshot_store._news_snapshot_focus_key(target)
            snapshot, focus = await db.get_latest_news_snapshot_with_focus(
                target,
                focus_key,
            )
            if not snapshot_store._is_news_snapshot(snapshot):
                return ""

            items = snapshot.get("items") or []
            source_name = snapshot.get("source_name") or "新闻热搜"
            source_key = snapshot.get("source_key") or ""
            focus_index = snapshot_store._coerce_news_tool_index(
                (focus or {}).get("index") if isinstance(focus, dict) else None
            )
            lines = [
                self.tool_context._NEWS_LINK_CONTEXT_MARKER,
                "当前会话存在新闻快照；查询链接、摘要、来源或列表时调用 news_link 工具。",
                f"最近新闻源：{source_name}"
                + (f"（source={source_key}）" if source_key else ""),
                f"可查条目数：{len(items)}",
            ]
            if focus_index and 1 <= focus_index <= len(items):
                lines.append(f"最近关注序号：{focus_index}")
            return "\n".join(lines)
        except Exception as exc:
            logger.debug(f"[日常分享] 构建新闻工具动态上下文失败: {exc}")
            return ""

    @staticmethod
    def _clean_context_text(value, max_len: int = 80) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if max_len > 0 and len(text) > max_len:
            return text[:max_len].rstrip() + "..."
        return text

    def _qzone_context_state_key(self, target_uid: str) -> str:
        return f"qzone_context:{target_uid}"

    def _request_context_has_marker(self, req, marker: str) -> bool:
        if marker in str(getattr(req, "system_prompt", "") or ""):
            return True

        for part in getattr(req, "extra_user_content_parts", []) or []:
            if isinstance(part, dict):
                text = str(part.get("text") or part.get("content") or "")
            else:
                text = str(
                    getattr(part, "text", "") or getattr(part, "content", "") or ""
                )
            if marker in text:
                return True
        return False

    def _append_request_context_prompt(self, req, prompt: str) -> None:
        current = str(getattr(req, "system_prompt", "") or "").rstrip()
        req.system_prompt = f"{current}\n\n{prompt}" if current else prompt

    @staticmethod
    def _qzone_context_item(post, index: int, *, self_uin: int = 0) -> dict:
        text = getattr(post, "text", None)
        repost = getattr(post, "rt_con", None)
        is_self = bool(self_uin and int(getattr(post, "uin", 0) or 0) == int(self_uin))
        return {
            "index": index,
            "post_id": str(getattr(post, "key", "") or "").strip(),
            "author": str(
                getattr(post, "name", "") or getattr(post, "uin", "") or ""
            ).strip(),
            "text": PluginToolContextService._clean_context_text(text or repost, 90),
            "repost_text": PluginToolContextService._clean_context_text(repost, 90),
            "repost_author": PluginToolContextService._clean_context_text(
                getattr(post, "rt_uinname", "") or getattr(post, "rt_uin", ""),
                32,
            ),
            "repost_images": len(getattr(post, "rt_images", []) or []),
            "created_at": int(getattr(post, "create_time", 0) or 0),
            "images": len(getattr(post, "images", []) or []),
            "videos": len(getattr(post, "videos", []) or []),
            "is_self": is_self,
        }

    async def _remember_qzone_context_posts(
        self,
        target_uid: str,
        posts,
        *,
        target_id: str = "",
        focus_post_id: str = "",
        self_uin: int = 0,
        target_label: str = "",
    ) -> None:
        db = self.db
        target = str(target_uid or "").strip()
        if not db or not target:
            return

        items = []
        for index, post in enumerate(list(posts or [])[:10], start=1):
            item = self.tool_context._qzone_context_item(post, index, self_uin=self_uin)
            if item.get("post_id"):
                items.append(item)
        if not items:
            return

        scope_label = str(target_label or "").strip()
        if not scope_label:
            scope_label = (
                "我的说说"
                if not str(target_id or "").strip()
                else f"QQ {str(target_id).strip()} 的说说"
            )

        await db.set_context_state(
            self.tool_context._qzone_context_state_key(target),
            {
                "timestamp": time.time(),
                "target_id": str(target_id or "").strip(),
                "target_label": scope_label,
                "focus_post_id": str(
                    focus_post_id or items[0]["post_id"] or ""
                ).strip(),
                "items": items,
            },
        )

    async def _remember_qzone_context_focus(
        self, target_uid: str, post_id: str
    ) -> None:
        db = self.db
        target = str(target_uid or "").strip()
        focus = str(post_id or "").strip()
        if not db or not target or not focus:
            return

        key = self.tool_context._qzone_context_state_key(target)
        snapshot = await db.get_context_state(key, {})
        if not isinstance(snapshot, dict):
            snapshot = {}
        snapshot.update({"timestamp": time.time(), "focus_post_id": focus})
        await db.set_context_state(key, snapshot)

    async def _clear_qzone_context_focus(
        self, target_uid: str, post_id: str = ""
    ) -> None:
        db = self.db
        target = str(target_uid or "").strip()
        if not db or not target:
            return

        key = self.tool_context._qzone_context_state_key(target)
        snapshot = await db.get_context_state(key, {})
        if not isinstance(snapshot, dict):
            return

        focus = str(snapshot.get("focus_post_id") or "").strip()
        target_post = str(post_id or "").strip()
        if target_post and focus and focus != target_post:
            return
        snapshot["focus_post_id"] = ""
        snapshot["timestamp"] = time.time()
        await db.set_context_state(key, snapshot)

    async def _build_qzone_context_prompt(self, target_uid: str) -> str:
        db = self.db
        target = str(target_uid or "").strip()
        if not db or not target:
            return ""

        try:
            snapshot = await db.get_context_state(
                self.tool_context._qzone_context_state_key(target), {}
            )
            if not isinstance(snapshot, dict):
                return ""

            items = [
                item for item in snapshot.get("items") or [] if isinstance(item, dict)
            ]
            if not items:
                return ""

            created_at = float(snapshot.get("timestamp") or 0)
            if (
                created_at <= 0
                or time.time() - created_at
                > self.tool_context._QZONE_CONTEXT_TTL_SECONDS
            ):
                return ""

            lines = [
                self.tool_context._QZONE_CONTEXT_MARKER,
                "当前会话存在最近 QQ 空间查询状态；需要列表、详情或操作时调用 qzone 工具。",
            ]
            target_id = str(snapshot.get("target_id") or "").strip()
            if target_id:
                lines.append(f"最近查询目标 QQ：{target_id}")

            target_label = str(snapshot.get("target_label") or "").strip()
            if target_label:
                lines.append(f"列表来源：{target_label}")

            focus_post_id = str(snapshot.get("focus_post_id") or "").strip()
            if focus_post_id:
                lines.append(f"最近关注 post_id：{focus_post_id}")

            lines.append(f"最近列表条数：{len(items)}")
            return "\n".join(lines)
        except Exception as exc:
            logger.debug(f"[日常分享] 构建 QQ 空间工具动态上下文失败: {exc}")
            return ""

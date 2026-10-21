from __future__ import annotations

import asyncio
import random
import time
from typing import TYPE_CHECKING

from astrbot.api import logger

if TYPE_CHECKING:
    from .models import QzonePost
    from .qzone import QzoneService

SELF_POST_STATE_KEY = "qzone_self_post"
SELF_POST_STATE_LIMIT = 500


def self_comment_probability(conf: dict) -> int:
    try:
        value = int(conf.get("qzone_self_comment_probability", 30))
    except (TypeError, ValueError, OverflowError):
        value = 30
    return max(0, min(100, value))


class QzoneSelfPostService:
    """仅处理刚确认发布的说说；预先保存抽签和提交标记，避免重复动作。"""

    def __init__(self, owner: QzoneService, plugin) -> None:
        self.owner = owner
        self.plugin = plugin
        self._claim_lock = asyncio.Lock()

    def schedule(self, post: QzonePost, *, image_count: int = 0) -> None:
        # 后续动作不能向发布层抛错，否则可能触发重新登录、重复发布。
        try:
            conf = self.owner._qzone_config()
            if not (
                conf.get("qzone_auto_like_own_post", True)
                or self_comment_probability(conf)
            ):
                return
            if not post.tid or not post.uin or int(post.appid) != 311:
                return
            track = getattr(self.plugin, "track_task", None)
            if callable(track):
                coro = self.run(post, image_count=image_count)
                try:
                    track(coro)
                except Exception:
                    coro.close()
                    raise
        except Exception as exc:
            logger.warning(f"[日常分享] 说说已发布，自互动启动失败: {exc}")

    async def _save(self, post_key: str, entry: dict) -> None:
        await self.plugin.db.merge_cache_entries(
            "qzone",
            SELF_POST_STATE_KEY,
            {post_key: dict(entry)},
            max_items=SELF_POST_STATE_LIMIT,
        )

    async def run(self, post: QzonePost, *, image_count: int = 0) -> None:
        try:
            await self._run(post, image_count=image_count)
        except Exception as exc:
            logger.warning(f"[日常分享] 说说已发布，自互动未完成: {exc}")

    async def _run(self, post: QzonePost, *, image_count: int) -> None:
        if (
            self.plugin._is_terminated
            or not post.tid
            or not post.uin
            or int(post.appid) != 311
        ):
            return
        ctx = await self.owner.context()
        if int(post.uin) != int(ctx.uin):
            return
        async with self._claim_lock:
            state = await self.plugin.db.get_qzone_state(SELF_POST_STATE_KEY, {})
            if isinstance(state, dict) and post.key in state:
                return
            conf = self.owner._qzone_config()
            like = bool(conf.get("qzone_auto_like_own_post", True))
            probability = self_comment_probability(conf)
            comment = probability > 0 and (
                probability == 100 or random.random() * 100 < probability
            )
            entry = {
                "at": int(time.time()),
                "like": "pending" if like else "disabled",
                "comment": "selected" if comment else "skipped",
            }
            # 持久化失败即停止，不能发送后丢失防重记录。
            await self._save(post.key, entry)

        if like and not self.plugin._is_terminated:
            try:
                await self.owner.like(post.key)
                entry["like"] = "liked"
            except Exception as exc:
                entry["like"] = "failed"
                logger.warning(f"[日常分享] 自己的说说点赞失败: {exc}")
            await self._save(post.key, entry)

        if comment and not self.plugin._is_terminated:
            try:
                interaction = self.plugin.task_manager.qzone_interaction
                content = await interaction.generate_qzone_self_comment(
                    post, image_count=image_count
                )
                bridge = getattr(self.plugin, "daily_life_bridge", None)
                clean = getattr(bridge, "clean_expression_punctuation", None)
                if callable(clean):
                    content = await clean(content, scene="qzone_comment")
                if not str(content or "").strip():
                    raise ValueError("自评清洗后为空，停止提交")
                if self.plugin._is_terminated or not self_comment_probability(
                    self.owner._qzone_config()
                ):
                    entry["comment"] = "cancelled"
                    await self._save(post.key, entry)
                    return
                # 发送前保存正文；超时、取消或结果不明均不自动再次提交。
                entry.update(comment="submitting", content=content)
                await self._save(post.key, entry)
                await self.owner.comment(post.key, content)
                entry["comment"] = "commented"
            except Exception as exc:
                entry["comment"] = "unconfirmed"
                logger.warning(f"[日常分享] 说说自评未完成，停止自动重试: {exc}")
            await self._save(post.key, entry)
            if entry["comment"] == "commented":
                await interaction.record_qzone_self_comment(post, content)

        actions = []
        if entry["like"] == "liked":
            actions.append("已点赞")
        if entry["comment"] == "commented":
            actions.append("已自评")
        if actions:
            logger.info(f"[日常分享] 自己的说说：{'，'.join(actions)}。")

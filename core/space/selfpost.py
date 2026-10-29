from __future__ import annotations

import asyncio
import random
import time
from typing import TYPE_CHECKING

from astrbot.api import logger

from ..schedule import QZONE_SCHEDULE, normalize_schedule_mode
from .models import QzonePost

if TYPE_CHECKING:
    from .qzone import QzoneService

SELF_POST_STATE_KEY = "qzone_self_post"
SELF_POST_STATE_LIMIT = 500
_RETRYABLE = {"pending", "selected", "waiting", "preparing"}


def self_comment_probability(conf: dict) -> int:
    try:
        value = int(conf.get("qzone_self_comment_probability", 30))
    except (TypeError, ValueError, OverflowError):
        value = 30
    return max(0, min(100, value))


def _living(conf: dict) -> bool:
    return (
        normalize_schedule_mode(
            conf.get("qzone_trigger_mode"), QZONE_SCHEDULE.mode_default
        )
        == "life_driven"
    )


class QzoneSelfPostService:
    """确认发布后独立互动；只复查尚未提交的等待，提交未知永久保留防重。"""

    def __init__(self, owner: QzoneService, plugin) -> None:
        self.owner = owner
        self.plugin = plugin
        self._claim_lock = asyncio.Lock()

    def schedule(self, post: QzonePost, *, image_count: int = 0) -> None:
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

    async def review_pending(self) -> None:
        """由现有生活观察器唤醒，重启后仍只恢复新版记录中的等待。"""
        if self.plugin._is_terminated or not _living(self.owner._qzone_config()):
            return
        states = await self.plugin.db.get_qzone_state(SELF_POST_STATE_KEY, {})
        now = time.time()
        candidates = [
            row
            for row in states.values()
            if isinstance(row, dict)
            and row.get("version") == 2
            and row.get("living")
            and any(
                row.get(action) in _RETRYABLE
                and now >= row.get("review", {}).get(action, 0)
                for action in ("like", "comment")
            )
        ]
        if (
            candidates
            and not await self.plugin.task_manager.qzone_interaction.interaction_ready()
        ):
            return
        for row in candidates[:4]:
            await self.run(
                QzonePost(**row["post"]), image_count=row.get("image_count", 0)
            )

    async def run(self, post: QzonePost, *, image_count: int = 0) -> None:
        try:
            # 同一实例的发布回调和观察器不能并发领取同一动作。
            async with self._claim_lock:
                await self._run(post, image_count=image_count)
        except Exception as exc:
            logger.warning(f"[日常分享] 说说已发布，自互动未完成: {exc}")

    async def _wait(self, post, entry, action, interaction) -> None:
        reader = getattr(interaction, "interaction_state", None)
        if not callable(reader):
            entry[action] = "skipped"
        else:
            intent = await reader("self_" + action, post)
            if intent.get("decision") == "skip":
                entry[action] = "skipped"
            elif (
                intent.get("decision") == "act" and intent.get("status") != "preparing"
            ):
                entry[action] = "unconfirmed"
            elif intent.get("attempts", 0) >= 3:
                entry[action] = "exhausted"
            else:
                entry[action] = "waiting"
                entry["review"][action] = max(
                    time.time() + 300, intent.get("review_at", 0)
                )
        await self._save(post.key, entry)

    async def _run(self, post: QzonePost, *, image_count: int) -> None:
        if (
            self.plugin._is_terminated
            or not post.tid
            or not post.uin
            or int(post.appid) != 311
        ):
            return
        state = await self.plugin.db.get_qzone_state(SELF_POST_STATE_KEY, {})
        entry = state.get(post.key)
        conf = self.owner._qzone_config()
        living = _living(conf)
        if entry is not None:
            # 升级不重开旧版的一次性决定，也不恢复已经开始的平台提交。
            if entry.get("version") != 2 or not entry.get("living"):
                return
            if not living or time.time() - entry["at"] > 6 * 3600:
                for action in ("like", "comment"):
                    if entry.get(action) in _RETRYABLE:
                        entry[action] = "expired"
                await self._save(post.key, entry)
                return
        else:
            probability = self_comment_probability(conf)
            selected = probability > 0 and (
                living or probability == 100 or random.random() * 100 < probability
            )
            entry = {
                "version": 2,
                "living": living,
                "at": int(time.time()),
                "like": "pending"
                if conf.get("qzone_auto_like_own_post", True)
                else "disabled",
                "comment": "selected" if selected else "skipped",
                "review": {},
                "checks": {},
                "attempts": {},
                "image_count": image_count,
                "post": {
                    name: getattr(post, name)
                    for name in ("tid", "uin", "name", "text", "images", "create_time")
                },
            }
        eligible = [
            action
            for action in ("like", "comment")
            if entry.get(action) in _RETRYABLE
            and time.time() >= entry["review"].get(action, 0)
        ]
        if not eligible:
            return
        ctx = await self.owner.context()
        if int(post.uin) != int(ctx.uin):
            return
        await self._save(post.key, entry)
        interaction = self.plugin.task_manager.qzone_interaction
        actions = []
        for action in eligible:
            current = self.owner._qzone_config()
            enabled = (
                current.get("qzone_auto_like_own_post", True)
                if action == "like"
                else self_comment_probability(current)
            )
            if not enabled:
                entry[action] = "cancelled"
                await self._save(post.key, entry)
                continue
            if (
                entry["checks"].get(action, 0) >= 24
                or entry["attempts"].get(action, 0) >= 3
            ):
                entry[action] = "exhausted"
                await self._save(post.key, entry)
                continue
            entry["checks"][action] = entry["checks"].get(action, 0) + 1
            entry.update({action: "preparing"})
            entry["review"][action] = time.time() + 300
            await self._save(post.key, entry)
            if living and not await interaction.wants_interaction(
                "self_" + action, post
            ):
                await self._wait(post, entry, action, interaction)
                continue
            entry["attempts"][action] = entry["attempts"].get(action, 0) + 1
            content = ""
            try:
                if action == "comment":
                    content = await interaction.generate_qzone_self_comment(
                        post, image_count=image_count
                    )
                    bridge = getattr(self.plugin, "daily_life_bridge", None)
                    clean = getattr(bridge, "clean_expression_punctuation", None)
                    if callable(clean):
                        content = await clean(content, scene="qzone_comment")
                    if not str(content or "").strip():
                        raise ValueError("自评清洗后为空，停止提交")
                current = self.owner._qzone_config()
                enabled = (
                    current.get("qzone_auto_like_own_post", True)
                    if action == "like"
                    else self_comment_probability(current)
                )
                if self.plugin._is_terminated or not enabled:
                    entry[action] = "cancelled"
                elif living and not _living(current):
                    entry[action] = "cancelled"
                elif living and not await interaction.interaction_ready():
                    await self._wait(post, entry, action, interaction)
                    continue
                else:
                    # 只有到这里才可能调用平台；取消和超时保留此标记，不再次提交。
                    entry[action] = "submitting"
                    if content:
                        entry["content"] = content
                    await self._save(post.key, entry)
                    if action == "like":
                        await self.owner.like(post.key)
                        entry[action] = "liked"
                    else:
                        await self.owner.comment(post.key, content)
                        entry[action] = "commented"
                    actions.append("已点赞" if action == "like" else "已自评")
            except Exception as exc:
                submitted = entry[action] == "submitting"
                entry[action] = (
                    ("failed" if action == "like" else "unconfirmed")
                    if submitted or not living
                    else "waiting"
                )
                logger.warning(f"[日常分享] 说说自互动未完成：{type(exc).__name__}")
            await self._save(post.key, entry)
            if action == "comment" and entry[action] == "commented":
                await interaction.record_qzone_self_comment(post, content)
        if actions:
            logger.info(f"[日常分享] 自己的说说：{'，'.join(actions)}。")

"""B站独立动态复用公开短文案与配图服务，不读取或转发空间帖子。"""

from __future__ import annotations

import json

from ..config import ShareType
from ..database.keys import BILIBILI_TARGET_ID


class BiliPostComposer:
    def __init__(self, plugin):
        self.plugin = plugin

    @staticmethod
    def material(source):
        # 只投影生活插件提供的公开资料，私聊、文件路径不进入正文生成。
        return {key: source[key] for key in (
            "id", "kind", "title", "evidence", "impression", "appearance", "images"
        ) if key in source}

    async def compose(self, opportunity, source):
        material = self.material(source)
        history = [
            str(row.get("text") or "") for row in opportunity.get("recent_public_actions", [])
            if row.get("kind") == "dynamic" and row.get("status") in {"accepted", "confirmed"}
        ][:6]
        context = (
            "【本次B站公开素材，只依据这项素材表达；观看感受不冒充亲历】\n"
            + json.dumps(material, ensure_ascii=False)
        )
        if history:
            context += "\n【本账号近期已发布的B站动态，避免重复】\n" + json.dumps(history, ensure_ascii=False)
        period = self.plugin.task_manager.executor_helpers.period.get_curr_period()
        text = await self.plugin.content_service.generate(
            ShareType.MOOD, period, BILIBILI_TARGET_ID, False, context,
            nickname="", structured_history="", recent_post_contents=history,
            share_materials=[material],
        )
        if not isinstance(text, str) or not text.strip() or len(text.strip()) > 80:
            return None
        if "".join(text.split()) in {"".join(item.split()) for item in history}:
            return None
        return text.strip()

    async def image(self, job):
        if job.get("pending_media") == "image":
            # 续接只查询原任务，不再让视觉模型重新设计同一张配图。
            return await self.plugin.daily_life_bridge.generate_image(
                None, job.get("image_description", ""),
                contains_character=bool(job.get("contains_character")),
            )
        if job.get("image_path") or job.get("image_failed"):
            return job.get("image_path") or None
        if "image_life_context" not in job:
            # 与空间配图复用公开生活投影，只读取当前外观/生活资料，不读取空间帖子。
            context = await self.plugin.ctx_service.get_qzone_share_context()
            job["image_life_context"] = str(context.get("life_context") or "")
            await job["service"].save(job)
        return await self.plugin.image_service.generate_image(
            job["text"], ShareType.MOOD,
            job["image_life_context"]
            + "\n【仅限已选择的公开素材，创作配图不冒充视频原画或现场拍摄】\n"
            + json.dumps(job["source_material"], ensure_ascii=False),
            target_umo=BILIBILI_TARGET_ID,
        )

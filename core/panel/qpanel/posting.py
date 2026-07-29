from __future__ import annotations

from ..panelcomponent import PanelComponent

from ...database.keys import (
    HISTORY_SHARE_QZONE,
    MEDIA_IMAGE,
    QZONE_TARGET_ID,
    SOURCE_MANUAL,
)


class DashboardQzonePublishService(PanelComponent):
    async def page_qzone_publish(self):
        async def handler():
            body = await self.server._page_json_body()
            text = str(body.get("text") or body.get("content") or "").strip()
            images = self.qzone_publish._page_qzone_publish_media(body)

            if not text and not images:
                raise RuntimeError("说说内容或媒体不能为空")

            history_source = images[0] if images else ""
            history_media_url = (
                str(history_source)
                if history_source and not str(history_source).startswith("base64://")
                else ""
            )

            post = await self.qzone_service.publish_post(text=text, images=images)
            await self.db.add_sent_history(
                QZONE_TARGET_ID,
                HISTORY_SHARE_QZONE,
                text or "QQ 空间说说",
                True,
                source_type=SOURCE_MANUAL,
                media_type=MEDIA_IMAGE if images else "",
                media_url=history_media_url,
            )
            self.events.emit_dashboard_event(
                "qzone", {"action": "publish", "post_id": post.key}
            )
            ctx = await self.qzone_service.context()
            return {
                "ok": True,
                "data": {
                    "item": self.qzone_tools._page_qzone_post_payload(
                        post, self_uin=ctx.uin
                    )
                },
                "message": "说说已发布",
            }

        return await self.server._page_json(handler)

    def _page_qzone_publish_media(self, body: dict) -> list[str]:
        images = body.get("images") or []
        if isinstance(images, str):
            images = [line.strip() for line in images.splitlines() if line.strip()]
        if not isinstance(images, list):
            images = []

        media = body.get("media") or []
        if isinstance(media, list):
            for item in media:
                if not isinstance(item, dict):
                    continue
                source = str(item.get("source") or "").strip()
                if not source:
                    continue
                kind = str(item.get("kind") or item.get("type") or "").strip().lower()
                mime_type = (
                    str(item.get("mime_type") or item.get("mime") or "").strip().lower()
                )
                if kind == "video" or mime_type.startswith("video/"):
                    raise RuntimeError(
                        "QQ 空间说说已移除视频发布支持，请上传图片或只发送文字"
                    )
                images.append(source)
        return images

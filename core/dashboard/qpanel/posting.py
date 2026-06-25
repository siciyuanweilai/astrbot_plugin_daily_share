from __future__ import annotations

from ...database.keys import (
    HISTORY_SHARE_QZONE,
    MEDIA_IMAGE,
    MEDIA_VIDEO,
    QZONE_TARGET_ID,
    SOURCE_MANUAL,
)


class DashboardQzonePublishMixin:
    async def page_qzone_publish(self):
        async def handler():
            body = await self._page_json_body()
            text = str(body.get("text") or body.get("content") or "").strip()
            images, videos = self._page_qzone_publish_media(body)

            if images and videos:
                raise RuntimeError("QQ 空间视频不能和图片混发，请只保留一种媒体")
            if len(videos) > 1:
                raise RuntimeError("QQ 空间一次只能发布 1 个视频")
            if not text and not images and not videos:
                raise RuntimeError("说说内容或媒体不能为空")

            history_source = videos[0]["source"] if videos else images[0] if images else ""
            history_media_url = str(history_source) if history_source and not str(history_source).startswith("base64://") else ""

            post = await self.qzone_service.publish_post(text=text, images=images, videos=videos)
            await self.db.add_sent_history(
                QZONE_TARGET_ID,
                HISTORY_SHARE_QZONE,
                text or "QQ 空间说说",
                True,
                source_type=SOURCE_MANUAL,
                media_type=MEDIA_VIDEO if videos else MEDIA_IMAGE if images else "",
                media_url=history_media_url,
            )
            self._page_emit_dashboard_event("qzone", {"action": "publish", "post_id": post.key})
            ctx = await self.qzone_service.context()
            return {
                "ok": True,
                "data": {"item": self._page_qzone_post_payload(post, self_uin=ctx.uin)},
                "message": "说说已发布",
            }

        return await self._page_json(handler)

    def _page_qzone_publish_media(self, body: dict) -> tuple[list[str], list[dict]]:
        images = body.get("images") or []
        if isinstance(images, str):
            images = [line.strip() for line in images.splitlines() if line.strip()]
        if not isinstance(images, list):
            images = []

        videos = []
        media = body.get("media") or []
        if isinstance(media, list):
            for item in media:
                if not isinstance(item, dict):
                    continue
                source = str(item.get("source") or "").strip()
                if not source:
                    continue
                kind = str(item.get("kind") or item.get("type") or "").strip().lower()
                mime_type = str(item.get("mime_type") or item.get("mime") or "").strip().lower()
                if kind == "video" or mime_type.startswith("video/"):
                    videos.append(self._page_qzone_video_media(item, source=source, mime_type=mime_type))
                else:
                    images.append(source)
        return images, videos

    @staticmethod
    def _page_qzone_video_media(item: dict, *, source: str, mime_type: str) -> dict:
        if source.startswith(("http://", "https://")):
            raise RuntimeError("面板发布视频请上传本地视频文件")
        video = {
            "source": source,
            "name": str(item.get("name") or item.get("filename") or "video.mp4").strip() or "video.mp4",
            "mime_type": mime_type or "video/mp4",
            "require_album_dynamic": True,
        }
        cover = str(item.get("cover") or item.get("preview") or item.get("thumbnail") or "").strip()
        if cover:
            video["cover"] = cover
        return video

import asyncio
import json

from astrbot.api import logger

from ..jsonio import write_json_atomic
from .common import (
    _PAGE_MEDIA_CACHE_SECONDS,
    _PAGE_PREFERENCES_DEFAULTS,
    _quart_jsonify,
    _quart_request,
)
from .panelcomponent import PanelComponent


class DashboardBaseService(PanelComponent):
    """仪表盘基础能力。"""

    def register_web_apis(self) -> None:
        routes = (
            (
                "page/media/delete",
                self.media_page.page_media_delete,
                ["POST"],
                "删除每日分享媒体记录",
            ),
            (
                "page/preferences",
                self.config_routes.page_preferences,
                ["GET", "POST"],
                "仪表盘偏好",
            ),
            (
                "page/status",
                self.status_routes.page_status,
                ["GET"],
                "每日分享仪表盘状态",
            ),
            (
                "page/config",
                self.config_routes.page_config,
                ["GET", "POST"],
                "每日分享配置",
            ),
            ("page/history", self.query_routes.page_history, ["GET"], "每日分享历史"),
            (
                "page/failures",
                self.query_routes.page_failures,
                ["GET"],
                "每日分享失败记录",
            ),
            (
                "page/failures/clear",
                self.query_routes.page_failures_clear,
                ["POST"],
                "清空每日分享失败记录",
            ),
            ("page/media", self.media_page.page_media, ["GET"], "每日分享媒体"),
            (
                "page/media/view",
                self.media_page.page_media_view,
                ["POST"],
                "查看每日分享媒体",
            ),
            ("page/events", self.events.page_events, ["GET"], "每日分享仪表盘事件"),
            (
                "page/qzone/feed",
                self.qzone_feed.page_qzone_feed,
                ["GET"],
                "QQ 空间动态",
            ),
            (
                "page/qzone/detail",
                self.qzone_feed.page_qzone_detail,
                ["GET"],
                "QQ 空间说说详情",
            ),
            (
                "page/qzone/relation",
                self.qzone_relations.page_qzone_relation,
                ["GET"],
                "QQ 空间在意好友",
            ),
            (
                "page/qzone/entry",
                self.qzone_entry.page_qzone_entry,
                ["GET"],
                "QQ 空间扩展入口",
            ),
            (
                "page/qzone/upload-media",
                self.qzone_upload.page_qzone_upload_media,
                ["POST"],
                "上传 QQ 空间说说媒体",
            ),
            (
                "page/qzone/publish",
                self.qzone_publish.page_qzone_publish,
                ["POST"],
                "发布 QQ 空间说说",
            ),
            (
                "page/qzone/like",
                self.qzone_actions.page_qzone_like,
                ["POST"],
                "点赞 QQ 空间说说",
            ),
            (
                "page/qzone/comment",
                self.qzone_actions.page_qzone_comment,
                ["POST"],
                "评论 QQ 空间说说",
            ),
            (
                "page/qzone/delete",
                self.qzone_actions.page_qzone_delete,
                ["POST"],
                "删除 QQ 空间说说",
            ),
            (
                "page/toggle",
                self.config_routes.page_toggle,
                ["POST"],
                "切换每日分享开关",
            ),
            ("page/run", self.action_routes.page_run, ["POST"], "手动分享"),
            ("page/retry", self.retry_routes.page_retry, ["POST"], "重试每日分享"),
            (
                "page/targets",
                self.target_routes.page_targets_update,
                ["POST"],
                "更新每日分享目标",
            ),
        )
        for endpoint, handler, methods, desc in routes:
            route = f"/astrbot_plugin_daily_share/{endpoint}"
            self.context.register_web_api(
                route,
                handler,
                methods,
                desc,
            )
            self.runtime._registered_web_api_routes.add((route, tuple(methods)))

    def unregister_web_apis(self) -> None:
        """移除当前插件实例注册的全部面板接口。"""
        if not self.runtime._registered_web_api_routes:
            return
        registered = self.context.registered_web_apis
        registered[:] = [
            api
            for api in registered
            if (str(api[0]), tuple(api[2]))
            not in self.runtime._registered_web_api_routes
        ]
        self.runtime._registered_web_api_routes.clear()

    async def _page_response(self, payload: dict, status: int = 200, headers=None):
        response = _quart_jsonify(payload)
        response.status_code = status
        if headers:
            response.headers.update(headers)
        return response

    @staticmethod
    def _page_error_status(exc: Exception) -> int:
        if isinstance(exc, PermissionError):
            return 403
        if isinstance(exc, FileNotFoundError):
            return 404
        if isinstance(exc, BlockingIOError):
            return 409
        if isinstance(exc, (ValueError, TypeError)):
            return 400
        if isinstance(exc, RuntimeError):
            return 422
        return 500

    async def _page_json(self, callback, headers=None):
        try:
            payload = await callback()
            status = 200
            response_headers = headers
        except Exception as exc:
            status = self.server._page_error_status(exc)
            if status == 500:
                logger.exception("[日常分享] 仪表盘接口处理失败: %s", exc)
            else:
                logger.warning("[日常分享] 仪表盘请求未完成: %s", exc)
            payload = {
                "ok": False,
                "error": {"message": str(exc) or "请求失败"},
            }
            response_headers = None
        return await self.server._page_response(payload, status, response_headers)

    def _page_media_cache_headers(self) -> dict:
        return {
            "Cache-Control": f"private, max-age={_PAGE_MEDIA_CACHE_SECONDS}",
        }

    async def _page_query_params(self) -> dict:
        args = _quart_request.args or {}
        return {str(key): value for key, value in args.items()}

    async def _page_json_body(self) -> dict:
        data = await _quart_request.get_json(silent=True)
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _read_json_sync(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _normalize_page_preferences(self, preferences=None) -> dict:
        normalized = dict(_PAGE_PREFERENCES_DEFAULTS)
        if isinstance(preferences, dict):
            if "sakura_enabled" in preferences:
                normalized["sakura_enabled"] = bool(preferences.get("sakura_enabled"))
        return normalized

    async def _load_page_preferences(self) -> dict:
        if not await asyncio.to_thread(self.page_preferences_file.is_file):
            return dict(_PAGE_PREFERENCES_DEFAULTS)
        try:
            loop = asyncio.get_running_loop()
            preferences = await loop.run_in_executor(
                None,
                self.server._read_json_sync,
                self.page_preferences_file,
            )
            return self.server._normalize_page_preferences(preferences)
        except Exception as exc:
            logger.error("[日常分享] 读取仪表盘偏好失败: %s", exc)
            return dict(_PAGE_PREFERENCES_DEFAULTS)

    async def _save_page_preferences(self, preferences: dict) -> dict:
        normalized = self.server._normalize_page_preferences(preferences)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            self.server._write_page_preferences_sync,
            self.page_preferences_file,
            normalized,
        )
        return normalized

    @staticmethod
    def _write_page_preferences_sync(path, data) -> None:
        write_json_atomic(path, data)

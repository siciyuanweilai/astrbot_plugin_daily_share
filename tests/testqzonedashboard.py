import importlib.util
import sys
import types
import unittest
from pathlib import Path

from quart import Response, jsonify, request


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "daily_share_qzone_dashboard_testpkg"
CORE_PACKAGE_NAME = f"{PACKAGE_NAME}.core"
DASHBOARD_PACKAGE_NAME = f"{CORE_PACKAGE_NAME}.panel"
SPACE_PACKAGE_NAME = f"{CORE_PACKAGE_NAME}.space"
DATABASE_PACKAGE_NAME = f"{CORE_PACKAGE_NAME}.database"
QZONE_MODULE_NAME = f"{DASHBOARD_PACKAGE_NAME}.zoneview"
MODELS_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.models"
KEYS_MODULE_NAME = f"{DATABASE_PACKAGE_NAME}.keys"


class _Logger:
    def debug(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None

    def exception(self, *args, **kwargs):
        return None


def _install_stub_module(name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _load_dashboard_qzone_module():
    _install_stub_module(
        "astrbot", api=_install_stub_module("astrbot.api", logger=_Logger())
    )
    package_paths = {
        PACKAGE_NAME: ROOT,
        CORE_PACKAGE_NAME: ROOT / "core",
        DASHBOARD_PACKAGE_NAME: ROOT / "core" / "panel",
        SPACE_PACKAGE_NAME: ROOT / "core" / "space",
        DATABASE_PACKAGE_NAME: ROOT / "core" / "database",
    }
    for name, path in package_paths.items():
        module = _install_stub_module(name)
        module.__path__ = [str(path)]

    common = _install_stub_module(
        f"{DASHBOARD_PACKAGE_NAME}.common",
        _PAGE_MEDIA_CACHE_SECONDS=7 * 24 * 60 * 60,
        _PAGE_PREFERENCES_DEFAULTS={"sakura_enabled": True},
        _quart_jsonify=jsonify,
        _quart_request=request,
        _quart_response=Response,
    )

    keys_spec = importlib.util.spec_from_file_location(
        KEYS_MODULE_NAME,
        ROOT / "core" / "database" / "keys.py",
    )
    keys_module = importlib.util.module_from_spec(keys_spec)
    sys.modules[KEYS_MODULE_NAME] = keys_module
    keys_spec.loader.exec_module(keys_module)

    models_spec = importlib.util.spec_from_file_location(
        MODELS_MODULE_NAME,
        ROOT / "core" / "space" / "models.py",
    )
    models_module = importlib.util.module_from_spec(models_spec)
    sys.modules[MODELS_MODULE_NAME] = models_module
    models_spec.loader.exec_module(models_module)

    qzone_spec = importlib.util.spec_from_file_location(
        QZONE_MODULE_NAME,
        ROOT / "core" / "panel" / "zoneview.py",
    )
    qzone_module = importlib.util.module_from_spec(qzone_spec)
    sys.modules[QZONE_MODULE_NAME] = qzone_module
    qzone_spec.loader.exec_module(qzone_module)
    qzone_module._quart_request = common._quart_request
    return qzone_module, models_module


class _Db:
    def __init__(self):
        self.history = []

    async def add_sent_history(self, *args, **kwargs):
        self.history.append((args, kwargs))


class _QzoneService:
    def __init__(self, post_cls):
        self.post_cls = post_cls
        self.calls = []

    async def publish_post(self, *, text="", images=None):
        self.calls.append({"text": text, "images": list(images or [])})
        return self.post_cls(tid="post-1", uin=100000001, text=text)

    async def context(self):
        return types.SimpleNamespace(uin=100000001, nickname="测试用户乙")

    async def query_relations(self, *, relation_type="care"):
        self.calls.append({"relation_type": relation_type})
        return {
            "type": relation_type,
            "items": [
                {
                    "uin": 10001,
                    "name": "好友",
                    "remark": "",
                    "avatar": "https://q.qlogo.cn/headimg_dl?dst_uin=10001&spec=100",
                    "score": 66,
                    "time_label": "02:39",
                    "rank": 1,
                    "home": "https://user.qzone.qq.com/10001",
                }
            ],
        }

    async def query_visit_stats(self):
        return {
            "available": True,
            "today_views": 2,
            "total_views": 3087,
            "visitor_count": 9,
        }

    async def query_about_me(self, *, offset=0, count=10):
        self.calls.append({"entry": "about", "offset": offset, "count": count})
        return {
            "items": [
                self.post_cls(tid="about-1", uin=10001, name="好友", text="提到了我")
            ],
            "has_more": False,
            "next_offset": offset + 1,
            "message": "",
        }

    async def query_last_year(self, *, year=None, count=10):
        self.calls.append({"entry": "today", "year": year, "count": count})
        return {
            "items": [
                self.post_cls(
                    tid="today-1", uin=100000001, name="测试用户乙", text="去年的今天"
                )
            ],
            "has_more": False,
        }

    async def query_message_board(self, *, target_id="", start=0, num=10):
        self.calls.append(
            {"entry": "board", "target_id": target_id, "start": start, "num": num}
        )
        return {
            "items": [
                {
                    "id": "msg-1",
                    "content": "留言内容",
                    "floor": 1,
                    "author": {"uin": 10001, "nickname": "好友", "avatar": ""},
                }
            ],
            "total": 1,
            "has_more": False,
        }


class DashboardQzonePublishTests(unittest.IsolatedAsyncioTestCase):
    def _plugin(self, body):
        qzone_module, models_module = _load_dashboard_qzone_module()

        class Plugin(qzone_module.DashboardQzoneService):
            pass

        plugin = Plugin()
        plugin.db = _Db()
        plugin.qzone_service = _QzoneService(models_module.QzonePost)
        plugin.event_log = []

        async def page_json(callback, headers=None):
            try:
                payload = await callback()
            except Exception as exc:
                return {"ok": False, "error": {"message": str(exc)}}
            return {
                "ok": True,
                "data": payload.get("data", payload),
                **{k: v for k, v in payload.items() if k not in {"data"}},
            }

        async def page_json_body():
            return body

        async def page_query_params():
            return {}

        plugin.server._page_json = page_json
        plugin.server._page_json_body = page_json_body
        plugin.server._page_query_params = page_query_params
        plugin.events.emit_dashboard_event = lambda *args, **kwargs: (
            plugin.event_log.append((args, kwargs))
        )
        return plugin

    async def test_page_qzone_publish_rejects_video_media(self):
        plugin = self._plugin(
            {
                "text": "今天测试一下",
                "media": [
                    {
                        "kind": "video",
                        "name": "clip.mp4",
                        "source": "base64://AAAA",
                        "cover": "data:image/jpeg;base64,BBBB",
                        "mime_type": "video/mp4",
                    }
                ],
            }
        )

        result = await plugin.qzone_publish.page_qzone_publish()

        self.assertFalse(result["ok"])
        self.assertIn("已移除视频发布支持", result["error"]["message"])
        self.assertEqual(plugin.qzone_service.calls, [])

    async def test_page_qzone_relation_returns_items_and_stats(self):
        plugin = self._plugin({})

        result = await plugin.qzone_relations.page_qzone_relation()

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["account"]["nickname"], "测试用户乙")
        self.assertEqual(result["data"]["type"], "care")
        self.assertEqual(result["data"]["items"][0]["uin"], 10001)
        self.assertEqual(result["data"]["stats"]["today_views"], 2)

    async def test_page_qzone_entry_returns_about_me(self):
        plugin = self._plugin({})

        async def page_query_params():
            return {"entry": "about", "pos": "0", "num": "5"}

        plugin.server._page_query_params = page_query_params
        result = await plugin.qzone_entry.page_qzone_entry()

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["entry"], "about")
        self.assertEqual(result["data"]["kind"], "posts")
        self.assertEqual(result["data"]["items"][0]["content"], "提到了我")
        self.assertEqual(plugin.qzone_service.calls[-1]["entry"], "about")

    async def test_page_qzone_entry_returns_message_board(self):
        plugin = self._plugin({})

        async def page_query_params():
            return {"entry": "board", "pos": "0", "num": "5"}

        plugin.server._page_query_params = page_query_params
        result = await plugin.qzone_entry.page_qzone_entry()

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["entry"], "board")
        self.assertEqual(result["data"]["kind"], "messages")
        self.assertEqual(result["data"]["items"][0]["content"], "留言内容")
        self.assertEqual(plugin.qzone_service.calls[-1]["entry"], "board")

    async def test_page_qzone_publish_rejects_video_even_with_image_media(self):
        plugin = self._plugin(
            {
                "text": "混发测试",
                "media": [
                    {
                        "kind": "image",
                        "source": "base64://IMG",
                        "mime_type": "image/png",
                    },
                    {
                        "kind": "video",
                        "source": "base64://VID",
                        "mime_type": "video/mp4",
                    },
                ],
            }
        )

        result = await plugin.qzone_publish.page_qzone_publish()

        self.assertFalse(result["ok"])
        self.assertIn("已移除视频发布支持", result["error"]["message"])
        self.assertEqual(plugin.qzone_service.calls, [])

    async def test_page_qzone_upload_media_reads_chunks_and_limits_size(self):
        qzone_module, _ = _load_dashboard_qzone_module()
        uploader_module = sys.modules[f"{DASHBOARD_PACKAGE_NAME}.qpanel.uploader"]

        class Upload:
            filename = "image.png"
            content_type = "image/png"

            def __init__(self, chunks):
                self.chunks = list(chunks)
                self.read_sizes = []

            async def read(self, size=-1):
                self.read_sizes.append(size)
                return self.chunks.pop(0) if self.chunks else b""

        class Request:
            def __init__(self, upload):
                self.upload = upload

            @property
            def files(self):
                async def load_files():
                    return {"file": self.upload}

                return load_files()

        class Plugin(qzone_module.DashboardQzoneService):
            pass

        async def page_json(callback, headers=None):
            try:
                payload = await callback()
            except Exception as exc:
                return {"ok": False, "error": {"message": str(exc)}}
            return {"ok": True, "data": payload["data"]}

        plugin = Plugin()
        plugin.server._page_json = page_json
        plugin.qzone_upload._QZONE_PANEL_UPLOAD_MAX_BYTES = 5
        upload = Upload([b"abc", b"def"])
        old_request = uploader_module._quart_request
        uploader_module._quart_request = Request(upload)
        try:
            result = await plugin.qzone_upload.page_qzone_upload_media()
        finally:
            uploader_module._quart_request = old_request

        self.assertFalse(result["ok"])
        self.assertIn("24MB", result["error"]["message"])
        self.assertTrue(upload.read_sizes)


if __name__ == "__main__":
    unittest.main()

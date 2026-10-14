"""PC 点赞抓包的脱敏回归：原始复合键、实际网关和自动防重。"""

import json
import types
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, patch

from .testqzone import _load_qzone_service, _new_qzone_service, _parser
from .testqzonecomment import FakeDb, _interaction_args, _load_auto_comment_module

PHOTO_KEY = (
    "http://user.qzone.qq.com/20002/photo/album-1/pic_key!!"
    "^||^http://user.qzone.qq.com/20002/batchphoto/album-1/1791725078942066^||^1"
)
MOOD_KEY = (
    "http://user.qzone.qq.com/20002/mood/post-1.1"
    "^||^http://user.qzone.qq.com//photo/album-2/pic_key!!^||^0"
)


def callback(payload):
    return (
        '<html><body><script>var cb;try{document.domain="user.qzone.qq.com";'
        "cb=frameElement.callback;}catch(e){cb=frameElement.callback;}"
        f"frameElement.callback({json.dumps(payload)});</script></body></html>"
    )


SUCCESS = callback({"code": 0, "subcode": 0, "message": "succ", "data": ""})


class LikeSession:
    closed = False

    def __init__(self, body=SUCCESS, status=200):
        self.body = body
        self.status = status
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        body, status = self.body, self.status

        class Response:
            async def text(self):
                return body

            async def __aenter__(self):
                self.status = status
                return self

            async def __aexit__(self, *args):
                return None

        return Response()


def service_with_session(module, session=None):
    service = _new_qzone_service(module)
    service._session = session or LikeSession()
    service._session_timeout_seconds = service._api_timeout_seconds()
    service._ctx = module.QzoneContext(10001, "test-skey", "test-p-skey")
    service._ctx_at = 9999999999
    return service


class QzoneLikeParsingTests(unittest.TestCase):
    def test_feed_sources_preserve_both_composite_keys(self):
        for appid, key in ((311, MOOD_KEY), (4, PHOTO_KEY)):
            for source in ("item", "like", "cell_like", "operation", "common"):
                with self.subTest(appid=appid, source=source):
                    item = {
                        "uin": 20002,
                        "fid": "post-1",
                        "tid": "post-1",
                        "appid": appid,
                        "content": "测试动态",
                        "html": '<div class="f-info">测试动态</div>',
                    }
                    keys = {"unilikekey": key, "curlikekey": key + "-distinct"}
                    if source == "item":
                        item.update(keys)
                    else:
                        item[source] = keys
                    parser = _parser()
                    for post in (
                        parser.parse_feed_list([item])[0],
                        parser.parse_recent_feed_list({"data": {"data": [item]}})[0],
                    ):
                        self.assertEqual(post.unikey, key)
                        self.assertEqual(post.curkey, key + "-distinct")

    def test_nested_liked_state_skips_previously_liked_photo(self):
        item = {
            "uin": 20002,
            "tid": "batch-feed",
            "appid": 4,
            "content": "上传了照片",
            "cell_like": {"isliked": 1, "unlikekey": PHOTO_KEY},
        }
        for post in (
            _parser().parse_feed_list([item])[0],
            _parser().parse_recent_feed_list({"data": {"data": [item]}})[0],
        ):
            self.assertTrue(post.liked)
            self.assertEqual(post.like_keys, (PHOTO_KEY, PHOTO_KEY))

    def test_html_button_single_key_fills_both_fields_without_fabricating(self):
        item = {
            "uin": 20002,
            "fid": "batch-feed",
            "appid": 4,
            "html": (
                '<div class="f-info">上传了照片</div>'
                f'<a class="qz_like_btn_v3" data-unikey="{PHOTO_KEY}"></a>'
            ),
        }
        post = _parser().parse_recent_feed_list({"data": {"data": [item]}})[0]
        self.assertEqual(post.like_keys, (PHOTO_KEY, PHOTO_KEY))
        self.assertEqual(post.like_target_error, "")

    def test_missing_album_key_stays_unknown(self):
        post = _parser().parse_recent_feed_list(
            {
                "data": {
                    "data": [
                        {
                            "uin": 20002,
                            "fid": "batch-feed",
                            "appid": 4,
                            "html": '<div class="f-info">上传了照片</div>',
                        }
                    ]
                }
            }
        )[0]
        self.assertEqual(post.like_keys, ("", ""))
        self.assertIn("缺少原始点赞键", post.like_target_error)

    def test_detail_merge_preserves_feed_keys_and_can_fill_missing_keys(self):
        module = _load_qzone_service()
        base = module.QzonePost(
            uin=20002, tid="post-1", unikey=MOOD_KEY, curkey=MOOD_KEY
        )
        detail = module.QzonePost(
            uin=20002, tid="post-1", unikey="detail-key", curkey="detail-key"
        )
        merged = module.QzoneService._merge_post_detail(base, detail)
        self.assertEqual(merged.like_keys, (MOOD_KEY, MOOD_KEY))
        base = module.QzonePost(uin=20002, tid="post-1")
        detail = module.QzonePost(uin=20002, tid="post-1", unikey=MOOD_KEY)
        self.assertEqual(
            module.QzoneService._merge_post_detail(base, detail).like_keys,
            (MOOD_KEY, MOOD_KEY),
        )


class QzoneLikeServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_captured_forms_and_html_success_via_real_gateway(self):
        module = _load_qzone_service()
        for appid, key in ((311, MOOD_KEY), (4, PHOTO_KEY)):
            with self.subTest(appid=appid):
                service = service_with_session(module)
                post = module.QzonePost(
                    uin=20002, tid="post-1", appid=appid, unikey=key, curkey=key
                )
                service._remember_posts([post])
                with patch.object(service, "_invalidate_qzone_cache") as invalidate:
                    await service.like(post.key)
                self.assertTrue(post.liked)
                invalidate.assert_called_once_with(post_id=post.key, target_id="20002")
                self.assertEqual(len(service._session.calls), 1)
                call = service._session.calls[0]
                self.assertEqual(
                    (call["method"], call["url"]), ("POST", service.LIKE_URL)
                )
                self.assertEqual(call["params"], {"g_tk": service._ctx.gtk})
                self.assertEqual(
                    call["data"],
                    {
                        "opuin": 10001,
                        "unikey": key,
                        "curkey": key,
                        "from": -100,
                        "face": 0,
                        "fupdate": 1,
                        "qzreferrer": "https://user.qzone.qq.com/20002/main",
                    },
                )
                self.assertEqual(call["headers"]["Referer"], call["data"]["qzreferrer"])
                self.assertEqual(call["headers"]["Origin"], "https://user.qzone.qq.com")

    async def test_plain_mood_fallback_and_already_liked_are_idempotent(self):
        module = _load_qzone_service()
        service = service_with_session(module)
        await service.like("20002:post-1")
        await service.like("20002:post-1")
        self.assertEqual(len(service._session.calls), 1)
        data = service._session.calls[0]["data"]
        self.assertEqual(data["unikey"], "http://user.qzone.qq.com/20002/mood/post-1")
        self.assertEqual(data["curkey"], data["unikey"])

    async def test_invalid_album_targets_never_submit_as_mood(self):
        module = _load_qzone_service()
        for key in (
            "",
            "https://user.qzone.qq.com/20002/app/4/batch-feed",
            "https://user.qzone.qq.com/20002/mood/batch-feed",
            PHOTO_KEY.replace("/20002/", "/30003/"),
            "http://[invalid",
        ):
            with self.subTest(key=key):
                service = service_with_session(module)
                post = module.QzonePost(
                    uin=20002, tid="batch-feed", appid=4, unikey=key
                )
                service._remember_posts([post])
                with self.assertRaisesRegex(RuntimeError, "相册动态"):
                    await service.like(post.key)
                self.assertFalse(post.liked)
                self.assertEqual(service._session.calls, [])

    async def test_business_and_http_errors_never_mark_success(self):
        module = _load_qzone_service()
        for payload, status in (
            ({"code": -10004, "subcode": -10004, "message": "参数错误"}, 200),
            ({"code": 0, "subcode": -41031}, 200),
            ({"code": 0, "ret": -1}, 200),
            ({"code": 0, "subcode": 0}, 500),
            ({"message": "success"}, 200),
            ({"code": "invalid"}, 200),
        ):
            with self.subTest(payload=payload, status=status):
                service = service_with_session(
                    module, LikeSession(callback(payload), status)
                )
                post = module.QzonePost(uin=20002, tid="post-1", unikey=MOOD_KEY)
                service._remember_posts([post])
                with patch.object(service, "_invalidate_qzone_cache") as invalidate:
                    with self.assertRaisesRegex(
                        RuntimeError, f"transport=pc_like.*http={status}"
                    ):
                        await service.like(post.key)
                    invalidate.assert_not_called()
                self.assertFalse(post.liked)
                self.assertEqual(len(service._session.calls), 1)

    async def test_empty_http_200_does_not_mark_success_or_repeat_submit(self):
        module = _load_qzone_service()
        service = service_with_session(module, LikeSession(""))
        post = module.QzonePost(uin=20002, tid="post-1")
        service._remember_posts([post])
        with self.assertRaisesRegex(RuntimeError, "transport=pc_like"):
            await service.like(post.key)
        self.assertFalse(post.liked)
        self.assertEqual(len(service._session.calls), 1)

    async def test_auto_like_whole_album_once_and_skip_missing_target(self):
        tasks, models = _load_auto_comment_module()
        module = _load_qzone_service()
        service = service_with_session(module)
        posts = [
            models.QzonePost(
                uin=20002,
                tid="batch-1",
                appid=4,
                text="两张照片",
                unikey=PHOTO_KEY,
                curkey=PHOTO_KEY,
                photo_targets=[
                    models.QzonePhoto(owner_uin=20002, album_id="album-1", pic_key=pic)
                    for pic in ("pic_key!!", "pic-2!!")
                ],
            ),
            models.QzonePost(
                uin=20002,
                tid="changed-feed-id",
                appid=4,
                text="两张照片",
                unikey=PHOTO_KEY,
                curkey=PHOTO_KEY,
            ),
            models.QzonePost(uin=30003, tid="missing-key", appid=4, text="上传了照片"),
        ]
        service._remember_posts(posts)
        service.query_recent_posts = AsyncMock(return_value=posts)
        service.query_mention_posts = AsyncMock(return_value=[])

        class Manager(tasks.TaskQzoneAutoCommentService):
            def __init__(self):
                super().__init__(*_interaction_args(tasks))
                self.config.qzone = {
                    "enable_qzone": True,
                    "qzone_enable_auto_like": True,
                    "qzone_auto_like_limit": 3,
                }
                self.runtime = replace(
                    self.runtime,
                    db=FakeDb(),
                    plugin=types.SimpleNamespace(
                        _is_terminated=False,
                        qzone_service=service,
                        emit_dashboard_event=lambda *args: None,
                        call_llm=AsyncMock(side_effect=AssertionError("不应调用模型")),
                    ),
                )

        manager = Manager()
        with patch.object(tasks.asyncio, "sleep", AsyncMock()):
            result = await manager.execute_qzone_auto_like()
            self.assertEqual(
                (result["liked"], result["failed"], result["skipped"]), (1, 0, 2)
            )
            self.assertEqual(len(service._session.calls), 1)
            self.assertEqual(service._session.calls[0]["data"]["unikey"], PHOTO_KEY)
            processed = manager.db.state[tasks.QZONE_AUTO_LIKE_STATE_KEY]["processed"]
            self.assertEqual(processed["20002:batch-1"]["action"], "liked")
            self.assertNotIn("30003:missing-key", processed)
            # 同一批次换了列表 ID，持久化点赞键别名仍阻止重复提交。
            result = await manager.execute_qzone_auto_like()
            self.assertEqual(result["liked"], 0)
            self.assertEqual(len(service._session.calls), 1)
        manager.plugin.call_llm.assert_not_called()

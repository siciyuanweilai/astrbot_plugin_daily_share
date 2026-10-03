"""相册自动评论分流；字段来自用户抓包，列表夹具为脱敏合成数据。"""

import json
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from .testqzone import _load_qzone_service, _new_qzone_service, _parser
from .testqzonecomment import FakeDb, _load_auto_comment_module


def captured_album_response():
    fixture = Path(__file__).parent / "fixtures/qzone_album_comment_success.html"
    return fixture.read_text(encoding="utf-8")


def album_feed(**extra):
    return {
        "uin": 20002,
        "fid": "album-feed",
        "appid": 4,
        "html": "<div class='f-info'>上传了照片</div>",
        "photos": [{"albumId": "album-1", "picKey": "pic-1!!", "ownerUin": 20002}],
        **extra,
    }


def parse_feed(item):
    return _parser().parse_recent_feed_list({"data": {"data": [item]}})[0]


class PhotoResponseSession:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        body = next(self.responses)

        class Response:
            status = 200

            async def text(self):
                return body

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

        return Response()


class AlbumFeedParsingTests(unittest.TestCase):
    def test_explicit_photo_identifiers_survive_feed_parsing(self):
        post = parse_feed(album_feed())
        self.assertEqual(post.appid, 4)
        self.assertEqual(post.photo_targets[0].comment_topic_id, "album-1_pic-1!!")
        self.assertEqual(
            post.photo_targets[0].feed_comment_topic_id, "album-1_pic-1!!_0_0"
        )
        self.assertEqual(post.comment_target_error, "")

    def test_photo_html_attributes_and_links_are_paired_and_deduplicated(self):
        post = parse_feed(
            album_feed(
                photos=[],
                html="""
            <div class='f-info'>上传了照片</div>
            <img data-albumid='album-1' data-pickey='pic-1!!'>
            <a href='https://user.qzone.qq.com/view?topicId=album-1&amp;picKey=pic-1!!'>照片</a>
            <div class='comments-list'><img data-albumid='other' data-pickey='other'></div>
        """,
            )
        )
        self.assertEqual(len(post.photo_targets), 1)
        self.assertEqual(post.photo_targets[0].comment_topic_id, "album-1_pic-1!!")

    def test_captured_feed_metadata_and_photo_link_are_one_target(self):
        response = _parser().parse_qzone_response(captured_album_response())
        post = parse_feed(album_feed(photos=[], html=response["data"]["feeds"]))
        self.assertEqual(response["code"], 0)
        self.assertEqual(len(post.photo_targets), 1)
        photo = post.photo_targets[0]
        self.assertEqual(photo.album_id, "album-1")
        self.assertEqual(photo.pic_key, "pic_key!!")
        self.assertEqual(photo.feed_topic_id, "album-1_pic_key!!_0_0")
        self.assertEqual(post.comment_target_error, "")
        parsed_html = _parser().parse_feedinfo_html(response["data"]["feeds"])
        self.assertEqual(parsed_html.appid, 4)
        self.assertEqual(len(parsed_html.photo_targets), 1)
        self.assertEqual(
            parsed_html.photo_targets[0].feed_topic_id, photo.feed_topic_id
        )

    def test_composite_link_is_deduplicated_without_feed_metadata(self):
        post = parse_feed(
            album_feed(
                photos=[],
                html="""
            <div class='f-info'>上传了照片</div>
            <a data-topicid='album-1' data-pickey='pic_key!!'
               href='https://h5.qzone.qq.com/page/photo?topicId=album-1_pic_key!!_0_0&amp;picKey=pic_key!!'>照片</a>
        """,
            )
        )
        self.assertEqual(len(post.photo_targets), 1)
        self.assertEqual(post.photo_targets[0].album_id, "album-1")
        self.assertEqual(post.photo_targets[0].feed_topic_id, "album-1_pic_key!!_0_0")

    def test_conflicting_topic_is_not_overwritten_by_later_valid_link(self):
        post = parse_feed(
            album_feed(
                photos=[
                    {"albumId": "album-1", "picKey": "p1", "topicId": "album-1_p1_0_0"}
                ],
                html="""
                <div class='f-info'>上传了照片</div>
                <img data-albumid='album-1' data-pickey='p1' data-topicid='other_p1_0_0'>
                <a href='https://h5.qzone.qq.com/page/photo?topicId=album-1_p1_0_0&amp;picKey=p1'>照片</a>
            """,
            )
        )
        self.assertEqual(len(post.photo_targets), 1)
        self.assertIn("topicId", post.comment_target_error)

    def test_two_distinct_html_photos_still_require_explicit_selection(self):
        post = parse_feed(
            album_feed(
                photos=[],
                html="""
            <div class='f-info'>上传了照片</div>
            <a data-topicid='album-1' data-pickey='p1'
               href='https://h5.qzone.qq.com/page/photo?topicId=album-1_p1_0_0&amp;picKey=p1'>照片1</a>
            <a data-topicid='album-1' data-pickey='p2'
               href='https://h5.qzone.qq.com/page/photo?topicId=album-1_p2_0_0&amp;picKey=p2'>照片2</a>
        """,
            )
        )
        self.assertEqual(len(post.photo_targets), 2)
        self.assertIn("多个照片", post.comment_target_error)

    def test_missing_multiple_or_foreign_photo_targets_fail_closed(self):
        scenarios = [
            album_feed(
                photos=[], unikey="https://user.qzone.qq.com/20002/app/4/album-feed"
            ),
            album_feed(
                photos=[
                    {"albumId": "album-1", "picKey": "p1"},
                    {"albumId": "album-1", "picKey": "p2"},
                ]
            ),
            album_feed(
                photos=[
                    {"albumId": "album-1", "picKey": "p1"},
                    {"url": "https://photo.example/unresolved.jpg"},
                ]
            ),
            album_feed(
                photos=[{"albumId": "album-1", "picKey": "p1", "ownerUin": 30003}]
            ),
        ]
        for item in scenarios:
            with self.subTest(item=item):
                self.assertTrue(parse_feed(item).comment_target_error)

    def test_picture_in_a_mood_is_not_an_album_feed(self):
        post = parse_feed(album_feed(appid=311))
        self.assertEqual(post.photo_targets, [])
        self.assertEqual(post.comment_target_error, "")

    def test_generic_details_do_not_erase_album_type_and_identifiers(self):
        module = _load_qzone_service()
        base = parse_feed(album_feed())
        detail = module.QzonePost(uin=base.uin, tid=base.tid)
        merged = module.QzoneService._merge_post_detail(base, detail)
        self.assertEqual(merged.appid, 4)
        self.assertEqual(merged.photo_targets[0].comment_topic_id, "album-1_pic-1!!")

    def test_photo_detail_merge_preserves_feed_topic_separate_from_viewer_topic(self):
        module = _load_qzone_service()
        base = parse_feed(album_feed())
        base.photo_targets[0].feed_topic_id = "album-1_pic-1!!_0_0"
        detail = module.QzonePost(
            uin=base.uin,
            tid=base.tid,
            photo_targets=[
                type(base.photo_targets[0])(
                    owner_uin=base.uin,
                    album_id="album-1",
                    pic_key="pic-1!!",
                    topic_id="album-1",
                )
            ],
        )
        merged = module.QzoneService._merge_post_detail(base, detail)
        self.assertEqual(len(merged.photo_targets), 1)
        self.assertEqual(merged.photo_targets[0].topic_id, "album-1")
        self.assertEqual(merged.photo_targets[0].feed_topic_id, "album-1_pic-1!!_0_0")


class AlbumCommentRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.module = _load_qzone_service()
        self.service = _new_qzone_service(self.module)
        self.service.context = AsyncMock(
            return_value=self.module.QzoneContext(
                uin=10001, skey="dummy", p_skey="dummy"
            )
        )
        self.post = parse_feed(album_feed())
        self.service._remember_posts([self.post])

    async def test_auto_entry_uses_captured_photo_form_not_mood_form(self):
        self.service._request = AsyncMock(
            return_value={"code": 0, "data": {"id": 343965921, "content": "这是你吗？"}}
        )
        await self.service.comment(self.post.key, "这是你吗？")
        self.service._request.assert_awaited_once()
        data = self.service._request.call_args.kwargs["data"]
        self.assertEqual(
            self.service._request.call_args.args[:2],
            ("POST", self.service.PHOTO_COMMENT_URL),
        )
        self.assertEqual(
            data,
            {
                "topicId": "album-1_pic-1!!",
                "inCharset": "utf-8",
                "outCharset": "utf-8",
                "plat": "qzone",
                "hostUin": 20002,
                "uin": 10001,
                "commentUin": 10001,
                "ref": "photo",
                "need_private_comment": 1,
                "albumId": "album-1",
                "qzone": "qzone",
                "content": "这是你吗？",
                "richval": "",
                "richtype": "",
                "private": 0,
                "with_fwd": 0,
                "to_tweet": 0,
                "qzreferrer": "https://user.qzone.qq.com/10001/infocenter",
            },
        )
        self.assertEqual(
            self.service._request.call_args.kwargs["params"],
            {"g_tk": (await self.service.context()).gtk},
        )
        headers = self.service._request.call_args.kwargs["headers"]
        self.assertEqual(
            headers["Content-Type"], "application/x-www-form-urlencoded;charset=UTF-8"
        )
        self.assertEqual(headers["Origin"], "https://user.qzone.qq.com")
        self.assertEqual(headers["Referer"], data["qzreferrer"])
        self.assertEqual(headers["Sec-Fetch-Site"], "same-origin")

    async def test_missing_identifiers_do_not_submit_or_fallback(self):
        self.post.photo_targets = []
        self.service._request = AsyncMock()
        with self.assertRaisesRegex(RuntimeError, "albumId/picKey"):
            await self.service.comment(self.post.key, "hello")
        self.service._request.assert_not_awaited()

    async def test_photo_error_names_actual_transport_and_does_not_retry(self):
        self.service._request = AsyncMock(
            return_value={"code": -10004, "message": "参数错误", "_http_status": 200}
        )
        with self.assertRaisesRegex(
            RuntimeError, "transport=photo_comment, appid=4.*code=-10004"
        ):
            await self.service.comment(self.post.key, "hello")
        self.service._request.assert_awaited_once()

    async def test_invalid_topic_does_not_submit(self):
        self.post.photo_targets[0].feed_topic_id = "other_pic-1!!_0_0"
        self.service._request = AsyncMock()
        with self.assertRaisesRegex(RuntimeError, "topicId.*不一致"):
            await self.service.comment(self.post.key, "hello")
        with self.assertRaisesRegex(RuntimeError, "topicId.*不一致"):
            await self.service.comment_photo(
                owner_uin=20002,
                album_id="album-1",
                pic_key="pic-1!!",
                content="hello",
                feed_topic_id="other_pic-1!!_0_0",
            )
        self.service._request.assert_not_awaited()

    async def test_unknown_or_failed_response_is_not_recorded_as_success(self):
        responses = [
            {"code": -1, "_http_status": 200, "_raw_blank": True},
            {"_http_status": 200},
            {"code": 0, "subcode": -10004, "data": {"id": 42}},
            {"code": 0, "_http_status": 500, "data": {"id": 42}},
            {"code": 0, "data": {}},
            {"code": 0, "data": {"id": 0}},
            {"code": 0, "data": {"id": "invalid"}},
        ]
        for payload in responses:
            with self.subTest(payload=payload):
                self.service._request = AsyncMock(return_value=payload)
                with patch.object(
                    self.service, "_invalidate_qzone_cache"
                ) as invalidate:
                    with self.assertRaises(RuntimeError):
                        await self.service.comment(self.post.key, "hello")
                    invalidate.assert_not_called()
                self.service._request.assert_awaited_once()
                self.assertFalse(
                    self.service._request.call_args.kwargs["retry_parse_error"]
                )

    async def test_captured_feed_to_viewer_to_submit_through_real_gateway(self):
        response = _parser().parse_qzone_response(captured_album_response())
        post = _parser().parse_feedinfo_html(response["data"]["feeds"])
        session = PhotoResponseSession(
            json.dumps(
                {
                    "code": 0,
                    "data": {
                        "photos": [
                            {
                                "albumId": "album-1",
                                "picKey": "pic_key!!",
                                "topicId": "album-1",
                                "ownerUin": 20002,
                            }
                        ],
                        "single": {
                            "comments": [
                                {"id": 41, "content": "hello", "poster": {"id": 30003}}
                            ]
                        },
                    },
                }
            ),
            captured_album_response(),
        )
        self.service._http = AsyncMock(return_value=session)
        detailed = (await self.service._query_recent_post_details([post]))[0]
        self.assertEqual(detailed.photo_targets[0].topic_id, "album-1")
        self.assertEqual(
            detailed.photo_targets[0].feed_topic_id, "album-1_pic_key!!_0_0"
        )
        self.assertEqual(detailed.comments[0].uin, 30003)
        with patch.object(self.service, "_invalidate_qzone_cache") as invalidate:
            await self.service.comment(detailed.key, "喜欢")
            invalidate.assert_called_once_with(post_id=detailed.key, target_id="20002")
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[0]["method"], "GET")
        self.assertEqual(session.calls[0]["url"], self.service.PHOTO_VIEW_URL)
        self.assertEqual(session.calls[1]["method"], "POST")
        self.assertEqual(session.calls[1]["url"], self.service.PHOTO_COMMENT_URL)
        self.assertEqual(session.calls[1]["data"]["topicId"], "album-1_pic_key!!")
        self.assertEqual(session.calls[1]["data"]["ref"], "photo")
        self.assertEqual(
            session.calls[1]["params"]["g_tk"], (await self.service.context()).gtk
        )
        self.assertEqual(session.calls[1]["cookies"]["p_skey"], "dummy")

    async def test_real_gateway_does_not_replay_parameter_error_or_blank_page(self):
        for body in (
            'frameElement.callback({"code":-10004,"message":"参数错误"});',
            "",
        ):
            with self.subTest(body=body):
                session = PhotoResponseSession(body)
                self.service._http = AsyncMock(return_value=session)
                with patch.object(
                    self.service, "_invalidate_qzone_cache"
                ) as invalidate:
                    with self.assertRaisesRegex(RuntimeError, "transport=photo_comment"):
                        await self.service.comment(self.post.key, "hello")
                    invalidate.assert_not_called()
                self.assertEqual(len(session.calls), 1)
                self.assertEqual(
                    session.calls[0]["url"], self.service.PHOTO_COMMENT_URL
                )

    async def test_album_detail_uses_photo_viewer_and_matches_requested_photo(self):
        self.post.photo_targets[0].feed_topic_id = "album-1_pic-1!!_0_0"
        self.service._request = AsyncMock(
            return_value={
                "code": 0,
                "data": {
                    "photos": [
                        {"albumId": "album-1", "picKey": "neighbor", "ownerUin": 20002},
                        {"albumId": "album-1", "picKey": "pic-1!!", "ownerUin": 20002},
                    ],
                    "single": {
                        "comments": [
                            {"id": 42, "content": "已评论", "poster": {"id": 10001}}
                        ]
                    },
                },
            }
        )
        posts = await self.service._query_recent_post_details([self.post])
        self.assertEqual(posts[0].appid, 4)
        self.assertEqual(posts[0].photo_targets[0].pic_key, "pic-1!!")
        self.assertEqual(posts[0].photo_targets[0].feed_topic_id, "album-1_pic-1!!_0_0")
        self.assertEqual(posts[0].comments[0].uin, 10001)
        self.service._request.assert_awaited_once()
        self.assertEqual(
            self.service._request.call_args.args[:2],
            ("GET", self.service.PHOTO_VIEW_URL),
        )

    async def test_wrong_photo_response_is_rejected(self):
        self.service._request = AsyncMock(
            return_value={
                "code": 0,
                "data": {
                    "photos": [
                        {"albumId": "album-1", "picKey": "wrong", "ownerUin": 20002}
                    ]
                },
            }
        )
        with self.assertRaisesRegex(RuntimeError, "未包含请求"):
            await self.service.query_photo(
                owner_uin=20002, album_id="album-1", pic_key="pic-1!!"
            )

    async def test_photo_comments_are_not_sent_through_mood_reply(self):
        self.service._request = AsyncMock(return_value={"code": 0, "data": {"id": 43}})
        result = await self.service.reply_comment(
            self.post.key, self.module.QzoneComment(tid="42", uin=30003), "hello"
        )
        self.service._request.assert_awaited_once()
        self.assertEqual(
            self.service._request.call_args.args[:2],
            ("POST", self.service.PHOTO_REPLY_URL),
        )
        self.assertEqual(result["transport"], "photo_reply")


class AlbumAutoTaskTests(unittest.IsolatedAsyncioTestCase):
    async def test_task_skips_unresolved_album_before_llm_and_records_photo_success(
        self,
    ):
        module, models = _load_auto_comment_module()
        posts = [
            models.QzonePost(uin=20002, tid="unresolved", appid=4, text="上传了照片"),
            models.QzonePost(
                uin=20002,
                tid="resolved",
                appid=4,
                text="上传了照片",
                photo_targets=[
                    models.QzonePhoto(
                        owner_uin=20002, album_id="album-1", pic_key="pic-1"
                    )
                ],
            ),
        ]
        service_module = _load_qzone_service()
        service = _new_qzone_service(service_module)
        service.context = AsyncMock(
            return_value=service_module.QzoneContext(
                uin=10001, skey="dummy", p_skey="dummy"
            )
        )
        service.query_recent_posts = AsyncMock(return_value=posts)
        service.query_mention_posts = AsyncMock(return_value=[])
        service._request = AsyncMock(return_value={"code": 0, "data": {"id": 42}})
        service._remember_posts(posts)

        class Manager(module.TaskQzoneAutoCommentService):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_comment": True,
                    "qzone_auto_comment_limit": 2,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=service,
                    emit_dashboard_event=lambda *args, **kwargs: None,
                )
                self.generated_for = []

            async def generate_qzone_auto_comment(self, post, **kwargs):
                self.generated_for.append(post.key)
                return "好好看"

        manager = Manager()
        with patch.object(module.asyncio, "sleep", new=AsyncMock()):
            first = await manager.execute_qzone_auto_comment()
            second = await manager.execute_qzone_auto_comment()
        self.assertEqual(first["commented"], 1)
        self.assertEqual(first["failed"], 0)
        self.assertEqual(second["commented"], 0)
        self.assertEqual(manager.generated_for, ["20002:resolved"])
        service._request.assert_awaited_once()
        self.assertEqual(service._request.call_args.kwargs["data"]["ref"], "photo")
        state = manager.db.state[module.QZONE_AUTO_COMMENT_STATE_KEY]
        self.assertEqual(state["processed"]["20002:resolved"]["action"], "commented")

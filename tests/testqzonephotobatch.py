"""多图上传共用识图上限，仅发一条评论，各照片回评目标独立。"""

import copy
import json
import sys
import types
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

from .testqzone import (
    _load_qzone_service,
    _new_qzone_service,
    _parser,
)
from .testqzonecomment import FakeDb, _load_auto_comment_module
from .testqzonephotoauto import PhotoResponseSession, album_feed, parse_feed
from .testqzonephototarget import batch_feed_html, upload_feed_html


def batch_capture():
    return (
        Path(__file__).parent / "fixtures/qzone_album_batch_viewer.jsonp"
    ).read_text()


def upload_capture():
    return (
        Path(__file__).parent / "fixtures/qzone_album_upload_viewer.jsonp"
    ).read_text()


class PhotoBatchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.module = _load_qzone_service()
        self.service = _new_qzone_service(self.module)
        self.service.context = AsyncMock(
            return_value=self.module.QzoneContext(
                uin=10001,
                skey="dummy",
                p_skey="dummy",
            )
        )
        self.payload = _parser().parse_qzone_response(batch_capture())
        self.post = parse_feed(
            album_feed(photos=copy.deepcopy(self.payload["data"]["photos"]))
        )
        self.service._remember_posts([self.post])
        self.comments = {}
        self.failed_pics = set()
        self.service._request = AsyncMock(side_effect=self.request)
        self.service.query_mention_posts = AsyncMock(return_value=[])
        self.service.query_recent_posts = AsyncMock(
            side_effect=lambda **kwargs: [self.post]
        )
        self.service.query_posts = AsyncMock(return_value=[])
        self.task_module, _ = _load_auto_comment_module()
        service = self.service

        class Manager(self.task_module.TaskQzoneAutoCommentService):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_comment": True,
                    "qzone_auto_comment_limit": 10,
                    "qzone_enable_auto_reply": True,
                    "qzone_auto_reply_limit": 10,
                    "qzone_auto_interaction_active_hours": 0,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=service,
                    emit_dashboard_event=lambda *args, **kwargs: None,
                )
                self.generated = []

            async def generate_qzone_auto_comment(self, post, **kwargs):
                self.generated.append(
                    ("comment", post.photo_targets[0].pic_key, post.images)
                )
                return "Nice photo!"

            async def generate_qzone_auto_photo_comment(
                self, post, photo_posts, **kwargs
            ):
                return post.photo_targets[
                    0
                ].key, await self.generate_qzone_auto_comment(post, **kwargs)

            async def _generate_qzone_auto_reply(self, post, comment, **kwargs):
                self.generated.append(
                    ("reply", post.photo_targets[0].pic_key, comment.uin)
                )
                return "Thanks!"

            async def _generate_qzone_auto_reply_thread(
                self, post, parent, comment, **kwargs
            ):
                self.generated.append(
                    ("thread", post.photo_targets[0].pic_key, comment.uin)
                )
                return "Thanks!"

        self.manager = Manager()

    async def request(self, method, url, **kwargs):
        if method == "POST":
            data = kwargs["data"]
            pic = next(
                item["picKey"]
                for item in self.payload["data"]["photos"]
                if data["topicId"]
                == (
                    f"album-1_{item['picKey']}_0_0"
                    if url == self.service.PHOTO_REPLY_URL
                    else f"album-1_{item['picKey']}"
                )
            )
            if url == self.service.PHOTO_REPLY_URL:
                for root in self.comments.get(pic, []):
                    if str(root["id"]) == data["commentId"]:
                        root.setdefault("replies", []).append(
                            {
                                "id": 1790960000,
                                "postTime": 1790960000,
                                "poster": {"id": 10001, "name": "Bot"},
                                "content": data["content"],
                            }
                        )
            return {"code": 0, "subcode": 0, "data": {"id": 1790960000}}
        pic = kwargs["params"]["picKey"]
        if pic in self.failed_pics:
            raise RuntimeError("viewer unavailable")
        response = copy.deepcopy(self.payload)
        response["data"]["picPosInPage"] = next(
            index
            for index, item in enumerate(response["data"]["photos"])
            if item["picKey"] == pic
        )
        response["data"]["single"]["comments"] = copy.deepcopy(
            self.comments.get(pic, [])
        )
        return response

    async def run_comment(self):
        with patch("asyncio.sleep", new=AsyncMock()):
            return await self.manager.execute_qzone_auto_comment()

    async def run_reply(self):
        with patch("asyncio.sleep", new=AsyncMock()):
            return await self.manager.execute_qzone_auto_reply()

    def writes(self):
        return [
            call
            for call in self.service._request.call_args_list
            if call.args[0] == "POST"
        ]

    def use_image_vision(self, *, limit=None, enabled=True):
        self.manager.qzone_conf["qzone_enable_auto_comment_image_vision"] = enabled
        if limit is None:
            self.manager.qzone_conf.pop("qzone_auto_comment_image_vision_limit", None)
        else:
            self.manager.qzone_conf["qzone_auto_comment_image_vision_limit"] = limit

        async def describe(**kwargs):
            return types.SimpleNamespace(
                completion_text=f"Visible details of {kwargs['image_urls'][0]}"
            )

        self.vision = AsyncMock(side_effect=describe)
        self.manager.plugin.context = types.SimpleNamespace(
            llm_generate=self.vision,
            get_using_provider=lambda: types.SimpleNamespace(
                meta=lambda: types.SimpleNamespace(id="vision-provider")
            ),
        )
        self.manager.plugin.call_llm = AsyncMock(
            return_value=json.dumps({"photo_index": 1, "comment": "Nice photo!"})
        )
        self.manager.generate_qzone_auto_comment = types.MethodType(
            self.task_module.TaskQzoneAutoCommentService.generate_qzone_auto_comment,
            self.manager,
        )
        self.manager.generate_qzone_auto_photo_comment = types.MethodType(
            self.task_module.TaskQzoneAutoCommentService.generate_qzone_auto_photo_comment,
            self.manager,
        )

    def root(self, pic, *, bot=False):
        return {
            "id": 41,
            "postTime": 1790954256,
            "poster": {"id": 10001 if bot else 30003, "name": "Tester"},
            "content": "Nice!",
            "private": 0,
            "topicId": f"album-1_{pic}_0_0",
        }

    def own_post(self):
        self.post.uin = 10001
        for photo in self.post.photo_targets:
            photo.owner_uin = 10001
        for photo in self.payload["data"]["photos"]:
            photo["ownerUin"] = 10001
        self.payload["data"]["topic"]["ownerUin"] = 10001
        self.service._remember_posts([self.post])

    def use_upload_capture(self, *, photos=None):
        self.payload = _parser().parse_qzone_response(upload_capture())
        self.post = parse_feed(album_feed(photos=photos or [], html=upload_feed_html()))
        self.service._remember_posts([self.post])

    async def test_numeric_upload_topic_reaches_shared_vision_and_one_photo_comment(
        self,
    ):
        self.use_upload_capture()
        original_topics = [target.feed_topic_id for target in self.post.photo_targets]
        self.use_image_vision(limit=2)
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (1, 0))
        self.assertEqual(
            [call.kwargs["image_urls"] for call in self.vision.call_args_list],
            [[f"https://photo.example/photo-{index}.jpg"] for index in (1, 2)],
        )
        self.manager.plugin.call_llm.assert_awaited_once()
        prompt = self.manager.plugin.call_llm.call_args.kwargs["prompt"]
        for index in (1, 2):
            self.assertIn(
                f"Visible details of https://photo.example/photo-{index}.jpg", prompt
            )
        self.assertNotIn("Visible details of https://photo.example/photo-3.jpg", prompt)
        self.assertEqual(len(self.writes()), 1)
        call = self.writes()[0]
        self.assertEqual(call.args[1], self.service.PHOTO_COMMENT_URL)
        self.assertEqual(call.kwargs["data"]["topicId"], "album-1_pic-1!!")
        self.assertEqual(call.kwargs["data"]["ref"], "photo")
        self.assertEqual(call.kwargs["data"]["commentUin"], 10001)
        self.assertEqual(call.kwargs["data"]["albumId"], "album-1")
        self.assertNotIn("feedsType", call.kwargs["data"])
        self.assertEqual(
            [target.feed_topic_id for target in self.post.photo_targets],
            original_topics,
        )
        for index in (1, 2, 3):
            scope = self.service._require_post(f"20002:photo:album-1:pic-{index}!!")
            self.assertTrue(scope.photo_batch_complete)
            self.assertEqual(
                scope.photo_batch_key, "20002:photo-batch:album-1:1790992589220000"
            )
            self.assertEqual(scope.comment_target_error, "")
            self.assertEqual(scope.images, [f"https://photo.example/photo-{index}.jpg"])
        self.post.tid = "renamed-feed"
        self.post.photo_targets.reverse()
        self.service._remember_posts([self.post])
        self.assertEqual((await self.run_comment())["commented"], 0)
        self.assertEqual(len(self.writes()), 1)

    async def test_json_and_decorated_html_merge_can_comment_after_verification(self):
        self.use_upload_capture(
            photos=[
                {"albumId": "album-1", "picKey": f"pic-{index}!!"}
                for index in (1, 2, 3)
            ]
        )
        self.assertEqual((await self.run_comment())["commented"], 1)
        self.assertEqual(len(self.writes()), 1)

    async def test_numeric_upload_uses_real_gateway_with_captured_photo_success(self):
        self.use_upload_capture()
        self.use_image_vision(limit=3)
        responses = []
        for index in range(3):
            payload = copy.deepcopy(self.payload)
            payload["data"]["picPosInPage"] = index
            responses.append(f"viewer_Callback({json.dumps(payload)});")
        responses.append(
            (
                Path(__file__).parent
                / "fixtures/qzone_album_photo_comment_success.html"
            ).read_text()
        )
        session = PhotoResponseSession(*responses)
        del self.service._request
        self.service._http = AsyncMock(return_value=session)
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (1, 0))
        self.assertEqual(self.vision.await_count, 3)
        self.manager.plugin.call_llm.assert_awaited_once()
        self.assertEqual(
            [call["method"] for call in session.calls], ["GET"] * 3 + ["POST"]
        )
        self.assertEqual(
            [call["params"]["picKey"] for call in session.calls[:3]],
            [f"pic-{index}!!" for index in (1, 2, 3)],
        )
        submit = session.calls[-1]
        self.assertEqual(submit["url"], self.service.PHOTO_COMMENT_URL)
        self.assertEqual(submit["data"]["topicId"], "album-1_pic-1!!")
        self.assertEqual(submit["data"]["ref"], "photo")
        self.assertEqual(submit["headers"]["Referer"], submit["data"]["qzreferrer"])
        self.assertEqual(submit["params"], {"g_tk": (await self.service.context()).gtk})

    async def test_numeric_upload_topic_requires_actual_viewer_batch_and_platform(self):
        for invalid in (
            "different_batch",
            "no_batch",
            "different_platform",
            "no_platform",
            "anchor_unreadable",
        ):
            with self.subTest(invalid=invalid):
                self.manager.db = FakeDb()
                self.failed_pics.clear()
                self.use_upload_capture()
                if invalid == "different_batch":
                    self.payload["data"]["photos"][1]["batchId"] = "another-batch"
                elif invalid == "no_batch":
                    for photo in self.payload["data"]["photos"]:
                        photo.pop("batchId")
                elif invalid == "different_platform":
                    self.payload["data"]["photos"][1]["platformSubId"] = 0
                elif invalid == "no_platform":
                    for photo in self.payload["data"]["photos"]:
                        photo.pop("platformSubId")
                else:
                    self.failed_pics.add("pic-1!!")
                self.service._request.reset_mock()
                self.assertEqual((await self.run_comment())["commented"], 0)
                self.assertEqual(self.writes(), [])
        self.assertEqual(self.manager.generated, [])

    async def test_numeric_upload_source_conflict_is_rejected_before_any_request(self):
        for extra in ({"batchId": "another-batch"}, {"platformSubId": 0}):
            with self.subTest(extra=extra):
                self.use_upload_capture(
                    photos=[{"albumId": "album-1", "picKey": "pic-1!!", **extra}]
                )
                self.service._request.reset_mock()
                with self.assertRaisesRegex(RuntimeError, "批次或 platformSubId"):
                    await self.service.query_photo_posts(self.post.key)
                self.service._request.assert_not_awaited()

    async def test_single_numeric_upload_target_is_verified_before_auto_comment(self):
        self.use_upload_capture()
        self.post.photo_targets = self.post.photo_targets[:1]
        self.payload["data"]["photos"] = self.payload["data"]["photos"][:1]
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (1, 0))
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.writes()[0].kwargs["data"]["topicId"], "album-1_pic-1!!")
        self.assertEqual(self.writes()[0].kwargs["data"]["ref"], "photo")

    async def test_single_numeric_upload_target_can_reply_in_own_album(self):
        self.use_upload_capture()
        self.post.photo_targets = self.post.photo_targets[:1]
        self.payload["data"]["photos"] = self.payload["data"]["photos"][:1]
        self.own_post()
        self.comments["pic-1!!"] = [self.root("pic-1!!")]
        result = await self.run_reply()
        self.assertEqual((result["replied"], result["failed"]), (1, 0))
        self.assertEqual(len(self.writes()), 1)
        call = self.writes()[0]
        self.assertEqual(call.args[1], self.service.PHOTO_REPLY_URL)
        self.assertEqual(call.kwargs["data"]["topicId"], "album-1_pic-1!!_0_0")
        self.assertEqual(call.kwargs["data"]["commentId"], "41")
        self.assertEqual(call.kwargs["data"]["commentUin"], 30003)

    async def test_numeric_upload_missing_identifiers_are_filled_only_from_same_batch(
        self,
    ):
        self.use_upload_capture()
        self.post = parse_feed(
            album_feed(
                photos=[
                    {
                        "albumId": "album-1",
                        "picKey": "pic-1!!",
                        "topicId": "album-1_pic-1!!_1790992589220000_4",
                    },
                    {"url": "https://photo.example/photo-2.jpg"},
                    {"url": "https://photo.example/photo-3.jpg"},
                ]
            )
        )
        self.service._remember_posts([self.post])
        self.assertEqual((await self.run_comment())["commented"], 1)
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(
            self.manager.generated[0][2],
            [f"https://photo.example/photo-{index}.jpg" for index in (1, 2, 3)],
        )

    async def test_numeric_upload_business_error_does_not_retry_with_feed_form_or_sibling(
        self,
    ):
        self.use_upload_capture()
        normal_request = self.request

        async def request(method, url, **kwargs):
            if method == "POST":
                return {
                    "code": -10004,
                    "subcode": -10004,
                    "message": "bad params",
                    "_http_status": 200,
                }
            return await normal_request(method, url, **kwargs)

        self.service._request.side_effect = request
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (0, 1))
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.writes()[0].kwargs["data"]["topicId"], "album-1_pic-1!!")
        self.assertEqual(self.writes()[0].kwargs["data"]["ref"], "photo")

    async def test_numeric_upload_unknown_submit_stops_later_batch_retry(self):
        self.use_upload_capture()
        normal_request = self.request

        async def request(method, url, **kwargs):
            if method == "POST":
                raise RuntimeError("timeout")
            return await normal_request(method, url, **kwargs)

        self.service._request.side_effect = request
        self.assertEqual((await self.run_comment())["commented"], 0)
        state = self.manager.db.state[self.task_module.QZONE_AUTO_COMMENT_STATE_KEY][
            "processed"
        ]
        entry = state["20002:photo-batch:album-1:1790992589220000"]
        self.assertTrue(entry["submission_unknown"])
        self.assertEqual(entry["photo_target_key"], "album-1:pic-1!!")
        self.assertEqual((await self.run_comment())["commented"], 0)
        self.assertEqual(len(self.writes()), 1)

    async def test_actual_shape_selects_one_requested_photo_not_all_viewer_neighbors(
        self,
    ):
        session = PhotoResponseSession(batch_capture())
        del self.service._request
        self.service._http = AsyncMock(return_value=session)
        photo = await self.service.query_photo(
            owner_uin=20002, album_id="album-1", pic_key="pic-1!!"
        )
        self.assertEqual(photo.batch_id, "batch-1")
        self.assertEqual(photo.pic_key, "pic-1!!")
        self.assertEqual(photo.comments, [])
        self.assertEqual(len(session.calls), 1)

    async def test_scopes_are_registered_with_only_their_image_and_comment_tree(self):
        self.comments["pic-2!!"] = [self.root("pic-2!!")]
        scopes = await self.service.query_photo_posts(self.post.key)
        self.assertEqual(len(scopes), 3)
        self.assertEqual(len({item.photo_batch_key for item in scopes}), 1)
        for index, post in enumerate(scopes, start=1):
            self.assertEqual(post.comment_target_error, "")
            self.assertEqual(post.photo_targets[0].pic_key, f"pic-{index}!!")
            self.assertEqual(post.images, [f"https://photo.example/photo-{index}.jpg"])
            self.assertIs(self.service._require_post(post.key), post)
            self.assertEqual(len(post.comments), 1 if index == 2 else 0)
        self.assertEqual(len(self.post.photo_targets), 3)
        self.assertIn("多个照片", self.post.comment_target_error)

    async def test_batch_feed_metadata_reaches_vision_then_one_photo_comment(self):
        self.post = parse_feed(album_feed(photos=[], html=batch_feed_html()))
        self.service._remember_posts([self.post])
        self.use_image_vision(limit=3)
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (1, 0))
        self.assertEqual(self.vision.await_count, 3)
        self.manager.plugin.call_llm.assert_awaited_once()
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.writes()[0].kwargs["data"]["topicId"], "album-1_pic-1!!")
        self.assertEqual(
            [
                call.kwargs["params"]["picKey"]
                for call in self.service._request.call_args_list
                if call.args[0] == "GET"
            ],
            ["pic-1!!", "pic-2!!", "pic-3!!"],
        )

    async def test_shared_feed_topic_requires_viewer_confirmed_batch(self):
        html = batch_feed_html()
        for index in (2, 3):
            html = html.replace(
                f"topicId=album-1_pic-{index}!!_0_0",
                "topicId=album-1_pic-1!!_0_0",
            )
        self.post = parse_feed(album_feed(photos=[], html=html))
        self.service._remember_posts([self.post])
        original_topics = [target.feed_topic_id for target in self.post.photo_targets]
        scopes = await self.service.query_photo_posts(self.post.key)
        self.assertEqual(len(scopes), 3)
        self.assertTrue(all(post.photo_batch_complete for post in scopes))
        for post in scopes:
            photo = post.photo_targets[0]
            self.assertEqual(
                photo.feed_comment_topic_id, f"album-1_{photo.pic_key}_0_0"
            )
            self.assertEqual(post.comment_target_error, "")
        self.assertEqual(
            [target.feed_topic_id for target in self.post.photo_targets],
            original_topics,
        )
        self.assertEqual((await self.run_comment())["commented"], 1)
        self.assertEqual(len(self.writes()), 1)

    async def test_json_photo_list_shared_topic_is_confirmed_before_commenting(self):
        photos = copy.deepcopy(self.payload["data"]["photos"])
        for photo in photos:
            photo["topicId"] = "album-1_pic-1!!_0_0"
        self.post = parse_feed(album_feed(photos=photos))
        self.service._remember_posts([self.post])
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (1, 0))
        self.assertEqual(len(self.manager.generated), 1)
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.writes()[0].kwargs["data"]["topicId"], "album-1_pic-1!!")

    async def test_shared_topic_different_batch_or_unreadable_anchor_cannot_submit(
        self,
    ):
        for invalid in ("different_batch", "no_batch", "anchor_unreadable"):
            with self.subTest(invalid=invalid):
                self.manager.db = FakeDb()
                self.failed_pics.clear()
                self.payload = _parser().parse_qzone_response(batch_capture())
                self.post = parse_feed(
                    album_feed(photos=copy.deepcopy(self.payload["data"]["photos"]))
                )
                for target in self.post.photo_targets:
                    target.feed_topic_id = "album-1_pic-1!!_0_0"
                if invalid == "different_batch":
                    self.payload["data"]["photos"][1]["batchId"] = "another-batch"
                elif invalid == "no_batch":
                    for photo in self.payload["data"]["photos"]:
                        photo.pop("batchId")
                else:
                    self.failed_pics.add("pic-1!!")
                self.service._remember_posts([self.post])
                self.service._request.reset_mock()
                result = await self.run_comment()
                self.assertEqual(result["commented"], 0)
                self.assertEqual(self.writes(), [])
        self.assertEqual(self.manager.generated, [])

    async def test_unknown_shared_topic_fails_before_reading_or_writing(self):
        self.post.photo_targets[1].feed_topic_id = "album-1_unknown-photo_0_0"
        with self.assertRaisesRegex(RuntimeError, "topicId.*不一致.*unknown-photo"):
            await self.service.query_photo_posts(self.post.key)
        self.service._request.assert_not_awaited()

    async def test_three_photos_comment_once_even_after_feed_rename_and_order_change(
        self,
    ):
        first = await self.run_comment()
        self.assertEqual((first["commented"], first["failed"]), (1, 0))
        self.assertEqual(len(self.manager.generated), 1)
        self.assertEqual(
            self.manager.generated[0],
            (
                "comment",
                "pic-1!!",
                [f"https://photo.example/photo-{index}.jpg" for index in range(1, 4)],
            ),
        )
        self.assertEqual(self.writes()[0].kwargs["data"]["topicId"], "album-1_pic-1!!")
        state = self.manager.db.state[self.task_module.QZONE_AUTO_COMMENT_STATE_KEY][
            "processed"
        ]
        self.assertEqual(
            state["20002:photo-batch:album-1:batch-1"]["action"], "commented"
        )
        self.post.tid = "renamed-feed"
        self.post.photo_targets.reverse()
        self.service._remember_posts([self.post])
        second = await self.run_comment()
        self.assertEqual(second["commented"], 0)
        self.assertEqual(len(self.writes()), 1)

    async def test_no_batch_id_uses_stable_photo_set_identity(self):
        for photo in self.post.photo_targets:
            photo.batch_id = ""
        for photo in self.payload["data"]["photos"]:
            photo.pop("batchId")
        self.assertEqual((await self.run_comment())["commented"], 1)
        self.post.tid = "renamed-feed"
        self.post.photo_targets.reverse()
        self.service._remember_posts([self.post])
        self.assertEqual((await self.run_comment())["commented"], 0)
        self.assertEqual(len(self.writes()), 1)

    async def test_batch_vision_obeys_shared_limit_and_synthesizes_one_comment(self):
        for limit, expected in ((None, 1), (1, 1), (2, 2), (3, 3), (9, 3)):
            with self.subTest(limit=limit):
                self.manager.db = FakeDb()
                self.service._request.reset_mock()
                self.use_image_vision(limit=limit)
                result = await self.run_comment()
                self.assertEqual((result["commented"], result["failed"]), (1, 0))
                self.assertEqual(
                    [call.kwargs["image_urls"] for call in self.vision.call_args_list],
                    [
                        [f"https://photo.example/photo-{index}.jpg"]
                        for index in range(1, expected + 1)
                    ],
                )
                self.manager.plugin.call_llm.assert_awaited_once()
                prompt = self.manager.plugin.call_llm.call_args.kwargs["prompt"]
                for index in range(1, expected + 1):
                    self.assertIn(
                        f"Visible details of https://photo.example/photo-{index}.jpg",
                        prompt,
                    )
                if expected < 3:
                    self.assertNotIn(
                        f"Visible details of https://photo.example/photo-{expected + 1}.jpg",
                        prompt,
                    )
                self.assertEqual(len(self.writes()), 1)
                self.assertEqual(
                    self.writes()[0].kwargs["data"]["topicId"], "album-1_pic-1!!"
                )
                for index in range(1, 4):
                    scoped = self.service._require_post(
                        f"20002:photo:album-1:pic-{index}!!"
                    )
                    self.assertEqual(
                        scoped.images, [f"https://photo.example/photo-{index}.jpg"]
                    )
                    self.assertEqual(len(scoped.photo_targets), 1)

    async def test_disabled_batch_vision_still_sends_only_one_text_comment(self):
        self.use_image_vision(limit=3, enabled=False)
        self.manager.plugin.call_llm.return_value = "Nice photo!"
        self.assertEqual((await self.run_comment())["commented"], 1)
        self.vision.assert_not_awaited()
        self.manager.plugin.call_llm.assert_awaited_once()
        self.assertNotIn(
            "【配图识别】", self.manager.plugin.call_llm.call_args.kwargs["prompt"]
        )
        self.assertEqual(len(self.writes()), 1)

    async def test_batch_vision_keeps_other_summaries_when_one_image_fails(self):
        self.use_image_vision(limit=3)
        self.manager.plugin.call_llm.return_value = json.dumps(
            {"photo_index": 3, "comment": "Third photo details are lovely!"}
        )
        self.vision.side_effect = [
            types.SimpleNamespace(completion_text="First photo details"),
            RuntimeError("vision unavailable"),
            types.SimpleNamespace(completion_text="Third photo details"),
        ]
        self.assertEqual((await self.run_comment())["commented"], 1)
        self.assertEqual(self.vision.await_count, 3)
        self.manager.plugin.call_llm.assert_awaited_once()
        prompt = self.manager.plugin.call_llm.call_args.kwargs["prompt"]
        self.assertIn("First photo details", prompt)
        self.assertIn("Third photo details", prompt)
        self.assertIn("图3（候选评论照片）: Third photo details", prompt)
        self.assertNotIn("图2（候选评论照片）", prompt)
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.writes()[0].kwargs["data"]["topicId"], "album-1_pic-3!!")

    async def test_third_photo_comment_is_bound_to_third_photo_and_keeps_life_style(
        self,
    ):
        self.use_image_vision(limit=3)
        self.vision.side_effect = [
            types.SimpleNamespace(completion_text="室内伸懒腰"),
            types.SimpleNamespace(completion_text="展厅里欣赏画作"),
            types.SimpleNamespace(completion_text="夕阳下坐在江边捧着饮料"),
        ]
        content = "江边这张好惬意，夕阳也刚刚好。"
        self.manager.plugin.call_llm.return_value = json.dumps(
            {"photo_index": 3, "comment": content}, ensure_ascii=False
        )
        self.manager.plugin.content_service = types.SimpleNamespace(
            get_qzone_chat_style_prompt=AsyncMock(
                return_value="生活聊天表达：自然、轻松。"
            ),
            get_persona_info=AsyncMock(return_value={"prompt": "原有人设"}),
        )
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (1, 0))
        self.assertEqual(self.vision.await_count, 3)
        self.manager.plugin.call_llm.assert_awaited_once()
        call = self.manager.plugin.call_llm.call_args
        self.assertIn("媒体：正文图片 3 张", call.kwargs["prompt"])
        self.assertIn("生活聊天表达：自然、轻松。", call.kwargs["system_prompt"])
        self.assertIn("原有人设", call.kwargs["system_prompt"])
        self.assertIn("只输出 JSON 对象", call.kwargs["system_prompt"])
        self.assertNotIn("只输出评论/回复正文", call.kwargs["system_prompt"])
        self.assertEqual(len(self.writes()), 1)
        data = self.writes()[0].kwargs["data"]
        self.assertEqual(
            (data["topicId"], data["content"]), ("album-1_pic-3!!", content)
        )
        entry = self.manager.db.state[self.task_module.QZONE_AUTO_COMMENT_STATE_KEY][
            "processed"
        ]["20002:photo-batch:album-1:batch-1"]
        self.assertEqual(entry["photo_target_key"], "album-1:pic-3!!")
        self.assertEqual(entry["post_key"], "20002:photo:album-1:pic-3!!")
        self.assertEqual(entry["content"], content)
        self.assertEqual((await self.run_comment())["commented"], 0)
        self.assertEqual(len(self.writes()), 1)

    async def test_first_photo_vision_failure_does_not_renumber_second_photo(self):
        self.use_image_vision(limit=3)
        self.vision.side_effect = [
            RuntimeError("vision unavailable"),
            types.SimpleNamespace(completion_text="Second photo details"),
            types.SimpleNamespace(completion_text="Third photo details"),
        ]
        self.manager.plugin.call_llm.return_value = json.dumps(
            {"photo_index": 2, "comment": "Second photo looks great!"}
        )
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (1, 0))
        prompt = self.manager.plugin.call_llm.call_args.kwargs["prompt"]
        self.assertIn("图2（候选评论照片）: Second photo details", prompt)
        self.assertNotIn("图1（候选评论照片）", prompt)
        self.assertEqual(self.writes()[0].kwargs["data"]["topicId"], "album-1_pic-2!!")

    async def test_comprehensive_comment_keeps_all_three_images_and_explicit_batch_wording(
        self,
    ):
        self.use_image_vision(limit=3)
        self.vision.side_effect = [
            types.SimpleNamespace(completion_text="室内伸懒腰"),
            types.SimpleNamespace(completion_text="展厅里欣赏画作"),
            types.SimpleNamespace(completion_text="夕阳下坐在江边捧着饮料"),
        ]
        content = "这组从屋里的慵懒到看展、江边的夕阳，松弛得刚刚好。"
        self.manager.plugin.call_llm.return_value = json.dumps(
            {"photo_index": 1, "comment": content}, ensure_ascii=False
        )
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (1, 0))
        self.assertEqual(self.vision.await_count, 3)
        self.manager.plugin.call_llm.assert_awaited_once()
        call = self.manager.plugin.call_llm.call_args
        for detail in ("室内伸懒腰", "展厅里欣赏画作", "夕阳下坐在江边捧着饮料"):
            self.assertIn(detail, call.kwargs["prompt"])
        self.assertIn("本批照片只发一条综合评论", call.kwargs["prompt"])
        self.assertIn("不是只评价提交落点这一张", call.kwargs["prompt"])
        self.assertIn("综合同批全部已识别图片", call.kwargs["system_prompt"])
        self.assertEqual(len(self.writes()), 1)
        data = self.writes()[0].kwargs["data"]
        self.assertEqual(
            (data["topicId"], data["content"]), ("album-1_pic-1!!", content)
        )

    async def test_bad_photo_selection_never_falls_back_to_first_photo(self):
        cases = [
            "caption without a photo index",
            "[]",
            "null",
            "{bad json}",
            json.dumps({"comment": "Nice!"}),
            json.dumps({"photo_index": True, "comment": "Nice!"}),
            json.dumps({"photo_index": "1", "comment": "Nice!"}),
            json.dumps({"photo_index": 1.0, "comment": "Nice!"}),
            json.dumps({"photo_index": 0, "comment": "Nice!"}),
            json.dumps({"photo_index": -1, "comment": "Nice!"}),
            json.dumps({"photo_index": 4, "comment": "Nice!"}),
            json.dumps({"photo_index": 1}),
            json.dumps({"photo_index": 1, "comment": []}),
            json.dumps({"photo_index": 1, "comment": " "}),
            json.dumps({"photo_index": 1, "comment": "skip"}),
        ]
        for response in cases:
            with self.subTest(response=response):
                self.manager.db = FakeDb()
                self.service._request.reset_mock()
                self.use_image_vision(limit=3)
                self.manager.plugin.call_llm.return_value = response
                result = await self.run_comment()
                self.assertEqual(
                    (result["commented"], result["generation_failed"]), (0, 1)
                )
                self.manager.plugin.call_llm.assert_awaited_once()
                self.assertEqual(self.writes(), [])

    async def test_photo_selection_cannot_exceed_vision_limit_or_select_failed_image(
        self,
    ):
        for limit, failure, selected in ((2, None, 3), (3, 2, 2)):
            with self.subTest(limit=limit, failure=failure):
                self.manager.db = FakeDb()
                self.service._request.reset_mock()
                self.use_image_vision(limit=limit)
                if failure:
                    self.vision.side_effect = [
                        types.SimpleNamespace(completion_text="First photo details"),
                        RuntimeError("vision unavailable"),
                        types.SimpleNamespace(completion_text="Third photo details"),
                    ]
                self.manager.plugin.call_llm.return_value = json.dumps(
                    {"photo_index": selected, "comment": "Nice!"}
                )
                result = await self.run_comment()
                self.assertEqual(
                    (result["commented"], result["generation_failed"]), (0, 1)
                )
                self.assertEqual(self.vision.await_count, limit)
                self.assertEqual(self.writes(), [])

    async def test_reordered_feed_keeps_selected_photo_identity(self):
        self.use_image_vision(limit=3)
        self.post.photo_targets.reverse()
        self.payload["data"]["photos"].reverse()
        self.manager.plugin.call_llm.return_value = (
            '```json\n{"photo_index": 3, "comment": "Third photo!"}\n```'
        )
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (1, 0))
        self.assertEqual(
            [call.kwargs["image_urls"] for call in self.vision.call_args_list],
            [[f"https://photo.example/photo-{index}.jpg"] for index in (1, 2, 3)],
        )
        data = self.writes()[0].kwargs["data"]
        self.assertEqual(
            (data["topicId"], data["content"]), ("album-1_pic-3!!", "Third photo!")
        )

    async def test_duplicate_or_missing_image_url_keeps_selection_mapping(self):
        for image_url, selected in (("https://photo.example/photo-1.jpg", 2), ("", 2)):
            with self.subTest(image_url=image_url):
                self.manager.db = FakeDb()
                self.service._request.reset_mock()
                self.payload["data"]["photos"][1]["url"] = image_url
                self.payload["data"]["photos"][1]["pre"] = image_url
                self.use_image_vision(limit=3)
                self.manager.plugin.call_llm.return_value = json.dumps(
                    {"photo_index": selected, "comment": "Third photo!"}
                )
                result = await self.run_comment()
                self.assertEqual((result["commented"], result["failed"]), (1, 0))
                self.assertEqual(self.vision.await_count, 2)
                self.assertEqual(
                    self.writes()[0].kwargs["data"]["topicId"], "album-1_pic-3!!"
                )

    async def test_selected_third_photo_is_pinned_across_rate_limited_retry(self):
        self.use_image_vision(limit=3)
        self.manager.plugin.call_llm.return_value = json.dumps(
            {"photo_index": 3, "comment": "Third photo!"}
        )
        normal_request = self.request

        async def request(method, url, **kwargs):
            if method == "POST":
                return {"code": -10000, "message": "操作频繁，请稍后再试"}
            return await normal_request(method, url, **kwargs)

        self.service._request.side_effect = request
        first = await self.run_comment()
        self.assertEqual((first["commented"], first["failed"]), (0, 0))
        self.assertTrue(first["rate_limited"])
        entry = self.manager.db.state[self.task_module.QZONE_AUTO_COMMENT_STATE_KEY][
            "processed"
        ]["20002:photo-batch:album-1:batch-1"]
        self.assertEqual(entry["action"], "retry_later")
        self.assertEqual(entry["photo_target_key"], "album-1:pic-3!!")
        self.post.photo_targets.reverse()
        self.service._request.side_effect = normal_request
        second = await self.run_comment()
        self.assertEqual((second["commented"], second["failed"]), (1, 0))
        self.manager.plugin.call_llm.assert_awaited_once()
        self.assertEqual(self.vision.await_count, 3)
        self.assertEqual(
            [
                (call.kwargs["data"]["topicId"], call.kwargs["data"]["content"])
                for call in self.writes()
            ],
            [("album-1_pic-3!!", "Third photo!"), ("album-1_pic-3!!", "Third photo!")],
        )

    async def test_all_batch_vision_failures_fall_back_to_one_text_comment(self):
        self.use_image_vision(limit=3)
        self.manager.plugin.call_llm.return_value = "Nice photo!"
        self.vision.side_effect = RuntimeError("vision unavailable")
        self.assertEqual((await self.run_comment())["commented"], 1)
        self.assertEqual(self.vision.await_count, 3)
        self.manager.plugin.call_llm.assert_awaited_once()
        self.assertNotIn(
            "【配图识别】", self.manager.plugin.call_llm.call_args.kwargs["prompt"]
        )
        self.assertEqual(len(self.writes()), 1)

    async def test_batch_vision_cache_survives_generation_failure_and_feed_reordering(
        self,
    ):
        self.use_image_vision(limit=3)
        self.manager.plugin.call_llm.side_effect = [
            RuntimeError("generation unavailable"),
            json.dumps({"photo_index": 1, "comment": "Nice photo!"}),
        ]
        first = await self.run_comment()
        self.assertEqual((first["commented"], first["generation_failed"]), (0, 1))
        self.assertEqual(self.vision.await_count, 3)
        self.assertEqual(self.writes(), [])
        self.post.tid = "renamed-feed"
        self.post.photo_targets.reverse()
        for photo in self.payload["data"]["photos"]:
            photo["url"] += "?token=rotated"
        self.service._remember_posts([self.post])
        self.assertEqual((await self.run_comment())["commented"], 1)
        self.assertEqual(self.vision.await_count, 3)
        self.assertEqual(self.manager.plugin.call_llm.await_count, 2)
        self.assertEqual(len(self.writes()), 1)

    async def test_changed_batch_image_is_not_reused_by_same_text_and_photo_position(
        self,
    ):
        self.use_image_vision(limit=3)
        self.manager.plugin.call_llm.side_effect = [
            RuntimeError("generation unavailable"),
            json.dumps({"photo_index": 1, "comment": "Nice photo!"}),
        ]
        self.assertEqual((await self.run_comment())["generation_failed"], 1)
        self.payload["data"]["photos"][0]["url"] = (
            "https://photo.example/updated-photo.jpg"
        )
        self.assertEqual((await self.run_comment())["commented"], 1)
        self.assertEqual(self.vision.await_count, 4)
        prompt = self.manager.plugin.call_llm.call_args.kwargs["prompt"]
        self.assertIn(
            "Visible details of https://photo.example/updated-photo.jpg", prompt
        )
        self.assertNotIn("Visible details of https://photo.example/photo-1.jpg", prompt)
        self.assertIn("Visible details of https://photo.example/photo-2.jpg", prompt)
        self.assertIn("Visible details of https://photo.example/photo-3.jpg", prompt)
        self.assertEqual(len(self.writes()), 1)

    async def test_legacy_album_cache_cannot_supply_cross_photo_summaries(self):
        self.use_image_vision(limit=3)
        sight = sys.modules[f"{self.task_module.__package__}.interact.sight"]
        self.manager.db.state[self.task_module.QZONE_AUTO_COMMENT_STATE_KEY] = {
            "image_vision_cache": {
                sight._qzone_image_url_cache_key(photo["url"]): "Wrong legacy details"
                for photo in self.payload["data"]["photos"]
            }
        }
        self.assertEqual((await self.run_comment())["commented"], 1)
        self.assertEqual(self.vision.await_count, 3)
        prompt = self.manager.plugin.call_llm.call_args.kwargs["prompt"]
        self.assertNotIn("Wrong legacy details", prompt)
        self.assertEqual(len(self.writes()), 1)

    async def test_generation_copy_deduplicates_images_without_mixing_batches_or_owners(
        self,
    ):
        scopes = await self.service.query_photo_posts(self.post.key)
        discuss = sys.modules[
            f"{self.task_module.__package__}.interact.executors.discuss"
        ]
        foreign = replace(
            scopes[1], uin=30003, images=["https://photo.example/foreign.jpg"]
        )
        other_batch = replace(
            scopes[1],
            photo_batch_key="20002:photo-batch:album-1:batch-2",
            images=["https://photo.example/other-batch.jpg"],
        )
        invalid = replace(
            scopes[1], photo_targets=[], images=["https://photo.example/invalid.jpg"]
        )
        incomplete = replace(
            scopes[1],
            photo_batch_complete=False,
            images=["https://photo.example/incomplete.jpg"],
        )
        duplicate = replace(scopes[1], images=list(scopes[0].images))
        generated = discuss._qzone_auto_comment_generation_post(
            scopes[0],
            [
                scopes[2],
                foreign,
                other_batch,
                invalid,
                incomplete,
                duplicate,
                scopes[0],
            ],
        )
        self.assertEqual(
            generated.images,
            ["https://photo.example/photo-1.jpg", "https://photo.example/photo-3.jpg"],
        )
        self.assertIsNot(generated, scopes[0])
        self.assertEqual(generated.photo_targets, scopes[0].photo_targets)
        self.assertEqual(generated.comments, scopes[0].comments)
        self.assertEqual(scopes[0].images, ["https://photo.example/photo-1.jpg"])
        self.assertIs(self.service._require_post(scopes[0].key), scopes[0])

    async def test_two_batches_in_one_album_are_recognized_and_commented_separately(
        self,
    ):
        self.use_image_vision(limit=3)
        second_photos = copy.deepcopy(self.payload["data"]["photos"])
        for index, photo in enumerate(second_photos, start=4):
            photo["picKey"] = photo["lloc"] = f"pic-{index}!!"
            photo["batchId"] = "batch-2"
            photo["url"] = f"https://photo.example/photo-{index}.jpg"
        self.payload["data"]["photos"].extend(second_photos)
        second = parse_feed(album_feed(fid="next-batch", photos=second_photos))
        self.service._remember_posts([second])
        self.service.query_recent_posts = AsyncMock(return_value=[self.post, second])
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (2, 0))
        self.assertEqual(self.vision.await_count, 6)
        self.assertEqual(self.manager.plugin.call_llm.await_count, 2)
        for call, indexes in zip(
            self.manager.plugin.call_llm.call_args_list,
            (range(1, 4), range(4, 7)),
        ):
            prompt = call.kwargs["prompt"]
            for index in range(1, 7):
                summary = f"Visible details of https://photo.example/photo-{index}.jpg"
                if index in indexes:
                    self.assertIn(summary, prompt)
                else:
                    self.assertNotIn(summary, prompt)
        self.assertEqual(
            [call.kwargs["data"]["topicId"] for call in self.writes()],
            ["album-1_pic-1!!", "album-1_pic-4!!"],
        )

    async def test_existing_bot_comment_on_another_photo_suppresses_whole_batch(self):
        self.comments["pic-3!!"] = [self.root("pic-3!!", bot=True)]
        result = await self.run_comment()
        self.assertEqual(result["commented"], 0)
        self.assertEqual(self.manager.generated, [])
        self.assertEqual(self.writes(), [])

    async def test_partial_read_failure_blocks_new_comments_but_other_photos_can_reply(
        self,
    ):
        self.failed_pics.add("pic-3!!")
        self.assertEqual((await self.run_comment())["commented"], 0)
        self.assertEqual(self.manager.generated, [])
        self.assertEqual(self.writes(), [])
        self.own_post()
        self.comments["pic-2!!"] = [self.root("pic-2!!")]
        result = await self.run_reply()
        self.assertEqual((result["replied"], result["failed"]), (1, 0))
        self.assertEqual(
            self.writes()[0].kwargs["data"]["topicId"], "album-1_pic-2!!_0_0"
        )

    async def test_unresolved_or_foreign_identifier_fails_closed_before_any_request(
        self,
    ):
        photo_type = type(self.post.photo_targets[0])
        for target in (
            photo_type(owner_uin=20002),
            photo_type(owner_uin=30003, album_id="album-1", pic_key="pic-3!!"),
            photo_type(
                owner_uin=20002,
                album_id="album-1",
                pic_key="pic-3!!",
                feed_topic_id="other",
            ),
        ):
            with self.subTest(target=target):
                self.post.photo_targets[-1] = target
                with self.assertRaises(RuntimeError):
                    await self.service.query_photo_posts(self.post.key)
        self.service._request.assert_not_awaited()

    async def test_unknown_post_stops_batch_retry_without_switching_to_sibling(self):
        normal_request = self.request

        async def request(method, url, **kwargs):
            if method == "POST":
                raise RuntimeError("timeout")
            return await normal_request(method, url, **kwargs)

        self.service._request.side_effect = request
        first = await self.run_comment()
        self.assertEqual(first["commented"], 0)
        state = self.manager.db.state[self.task_module.QZONE_AUTO_COMMENT_STATE_KEY][
            "processed"
        ]
        entry = state["20002:photo-batch:album-1:batch-1"]
        self.assertTrue(entry["submission_unknown"])
        self.assertEqual(entry["photo_target_key"], "album-1:pic-1!!")
        self.assertEqual((await self.run_comment())["commented"], 0)
        self.assertEqual(len(self.writes()), 1)

    async def test_same_root_id_on_different_photos_replies_independently(self):
        self.own_post()
        self.comments = {
            f"pic-{index}!!": [self.root(f"pic-{index}!!")] for index in range(1, 4)
        }
        result = await self.run_reply()
        self.assertEqual((result["replied"], result["failed"]), (3, 0))
        self.assertEqual(len(self.writes()), 3)
        self.assertEqual(
            {call.kwargs["data"]["topicId"] for call in self.writes()},
            {f"album-1_pic-{index}!!_0_0" for index in range(1, 4)},
        )
        state = self.manager.db.state[self.task_module.QZONE_AUTO_REPLY_STATE_KEY][
            "processed"
        ]
        for index in range(1, 4):
            self.assertEqual(
                state[f"10001:photo:album-1:pic-{index}!!:41"]["action"], "replied"
            )
        self.assertEqual((await self.run_reply())["replied"], 0)
        self.assertEqual(len(self.writes()), 3)

    async def test_friend_thread_on_second_photo_continues_without_new_root_comment(
        self,
    ):
        root = self.root("pic-2!!", bot=True)
        root["replies"] = [
            {
                "id": 1790957204,
                "postTime": 1790957204,
                "poster": {"id": 20002, "name": "Friend"},
                "content": "@{uin:10001,nick:Bot,auto:1} Hi!",
            }
        ]
        self.comments["pic-2!!"] = [root]
        first = await self.run_comment()
        self.assertEqual((first["commented"], first["failed"]), (1, 0))
        self.assertEqual(self.manager.generated, [("thread", "pic-2!!", 20002)])
        call = self.writes()[0]
        self.assertEqual(call.args[1], self.service.PHOTO_REPLY_URL)
        self.assertEqual(call.kwargs["data"]["topicId"], "album-1_pic-2!!_0_0")
        self.assertEqual(call.kwargs["data"]["commentId"], "41")
        self.assertEqual(call.kwargs["data"]["commentUin"], 10001)
        self.assertEqual(
            call.kwargs["data"]["content"], "@{uin:20002,nick:Friend,auto:1} Thanks!"
        )
        self.assertEqual((await self.run_comment())["commented"], 0)
        self.assertEqual(len(self.writes()), 1)

    async def test_viewer_comments_cannot_be_associated_with_neighbor_photo(self):
        # 响应中包含请求的照片标识，但查看器当前照片并非该目标。
        self.service._request = AsyncMock(return_value=self.payload)
        with self.assertRaisesRegex(RuntimeError, "未包含请求"):
            await self.service.query_photo(
                owner_uin=20002, album_id="album-1", pic_key="pic-2!!"
            )

    async def test_evicted_photo_scope_cannot_fall_back_to_mood_transport(self):
        scopes = await self.service.query_photo_posts(self.post.key)
        key = scopes[0].key
        self.service._post_cache.pop(key)
        self.service._request.reset_mock()
        with self.assertRaisesRegex(RuntimeError, "相册照片引用已失效"):
            await self.service.comment(key, "Hi")
        self.service._request.assert_not_awaited()

    async def test_processed_participation_from_other_photo_cannot_authorize_a_thread(
        self,
    ):
        scopes = await self.service.query_photo_posts(self.post.key)
        tracker = sys.modules[f"{self.task_module.__package__}.interact.tracker"]
        other_photo_state = {
            "20002:photo:album-1:pic-2!!:41_r_7_30003": {
                "action": "thread_replied",
                "parent_comment_id": "41",
            }
        }
        parent = self.module.QzoneComment(tid="41", uin=30003)
        self.assertFalse(
            tracker._qzone_processed_thread_has_self_reply(
                scopes[0], parent, other_photo_state
            )
        )
        self.assertTrue(
            tracker._qzone_processed_thread_has_self_reply(
                scopes[1], parent, other_photo_state
            )
        )

    async def test_duplicate_targets_are_read_only_once(self):
        self.post.photo_targets.append(copy.deepcopy(self.post.photo_targets[0]))
        scopes = await self.service.query_photo_posts(self.post.key)
        self.assertEqual(len(scopes), 3)
        self.assertEqual(self.service._request.await_count, 3)

    async def test_partly_resolved_feed_uses_verified_batch_members_not_thumbnail_urls(
        self,
    ):
        raw_photos = [
            copy.deepcopy(self.payload["data"]["photos"][0]),
            {"url": "https://photo.example/photo-2.jpg"},
            {"url": "https://photo.example/photo-3.jpg"},
        ]
        self.post = parse_feed(album_feed(photos=raw_photos))
        self.service._remember_posts([self.post])
        self.assertEqual(self.post.photo_targets[-1].unresolved_count, 2)
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (1, 0))
        self.assertEqual(len(self.writes()), 1)
        reads = [
            call.kwargs["params"]["picKey"]
            for call in self.service._request.call_args_list
            if call.args[0] == "GET"
        ]
        self.assertEqual(reads, ["pic-1!!", "pic-2!!", "pic-3!!"])

    async def test_partial_targets_with_missing_batch_or_count_mismatch_are_not_guessed(
        self,
    ):
        for invalid in (
            "no_batch",
            "different_batch",
            "different_owner",
            "count_mismatch",
        ):
            with self.subTest(invalid=invalid):
                self.payload = _parser().parse_qzone_response(batch_capture())
                raw_photos = [
                    copy.deepcopy(self.payload["data"]["photos"][0]),
                    {"url": "https://photo.example/unknown.jpg"},
                ]
                if invalid != "count_mismatch":
                    raw_photos.append({"url": "https://photo.example/other.jpg"})
                if invalid == "no_batch":
                    for item in self.payload["data"]["photos"]:
                        item.pop("batchId")
                elif invalid == "different_batch":
                    self.payload["data"]["photos"][1]["batchId"] = "another-batch"
                elif invalid == "different_owner":
                    self.payload["data"]["photos"][1]["ownerUin"] = 30003
                self.post = parse_feed(album_feed(photos=raw_photos))
                self.service._remember_posts([self.post])
                with self.assertRaises(RuntimeError):
                    await self.service.query_photo_posts(self.post.key)
                self.assertEqual(self.writes(), [])

    async def test_new_batch_in_same_album_is_not_suppressed_by_previous_batch(self):
        self.assertEqual((await self.run_comment())["commented"], 1)
        for index, photo in enumerate(self.payload["data"]["photos"], start=4):
            photo["picKey"] = photo["lloc"] = f"pic-{index}!!"
            photo["batchId"] = "batch-2"
        self.post = parse_feed(
            album_feed(
                fid="next-batch", photos=copy.deepcopy(self.payload["data"]["photos"])
            )
        )
        self.service._remember_posts([self.post])
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (1, 0))
        self.assertEqual(len(self.writes()), 2)
        self.assertEqual(self.writes()[1].kwargs["data"]["topicId"], "album-1_pic-4!!")

    async def test_explicit_parameter_rejection_does_not_try_three_siblings_in_one_run(
        self,
    ):
        normal_request = self.request

        async def request(method, url, **kwargs):
            if method == "POST":
                return {
                    "code": -10004,
                    "message": "parameter error",
                    "_http_status": 200,
                }
            return await normal_request(method, url, **kwargs)

        self.service._request.side_effect = request
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (0, 1))
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(len(self.manager.generated), 1)

    async def test_pending_retry_remains_on_original_photo_after_reordering(self):
        self.use_image_vision(limit=3)
        scopes = await self.service.query_photo_posts(self.post.key)
        tracker = sys.modules[f"{self.task_module.__package__}.interact.tracker"]
        processed = {}
        tracker._mark_qzone_post_processed(
            processed,
            scopes[1],
            "retry_later",
            content="Saved caption",
            photo_target_key="album-1:pic-2!!",
        )
        self.manager.db.state[self.task_module.QZONE_AUTO_COMMENT_STATE_KEY] = {
            "processed": processed
        }
        self.post.photo_targets.reverse()
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (1, 0))
        self.assertEqual(self.manager.generated, [])
        self.vision.assert_not_awaited()
        self.manager.plugin.call_llm.assert_not_awaited()
        data = self.writes()[0].kwargs["data"]
        self.assertEqual(data["topicId"], "album-1_pic-2!!")
        self.assertEqual(data["content"], "Saved caption")

    async def test_unbound_batch_html_comments_do_not_cross_into_photo_scopes(self):
        self.post.comments = [
            self.module.QzoneComment(
                tid="41", uin=10001, content="Unbound HTML comment"
            )
        ]
        self.comments["pic-2!!"] = [self.root("pic-2!!")]
        scopes = await self.service.query_photo_posts(self.post.key)
        self.assertEqual([len(post.comments) for post in scopes], [0, 1, 0])
        self.assertEqual(scopes[1].comments[0].uin, 30003)

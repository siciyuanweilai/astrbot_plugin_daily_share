"""多图上传共用识图上限，仅发一条评论，各照片回评目标独立。"""

import copy
import html
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
from .testqzonecomment import FakeDb, _interaction_args, _load_auto_comment_module
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


def batch_reply_html(reply_id, uin, nickname, target_uin, target_name, content):
    return (
        '<li class="comments-item" data-type="replyroot" '
        f'data-tid="{reply_id}" data-uin="{uin}" data-nick="{html.escape(nickname)}">'
        f'<div class="comments-content"><a class="nickname">{html.escape(nickname)}</a>'
        ' 回复<a class="nickname" '
        f'link="nameCard_{target_uin}" href="http://user.qzone.qq.com/{target_uin}">'
        f"{html.escape(target_name)}</a>&nbsp; : {html.escape(content)}</div></li>"
    )


def batch_thread_html(replies):
    root = (
        Path(__file__).parent / "fixtures/qzone_album_upload_comments.html"
    ).read_text()
    return root.rsplit("</li>", 1)[0] + (
        f'<div class="mod-comments-sub"><ul>{replies}</ul></div></li>'
    )


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
        self.batch_comment_html = None
        self.failed_pics = set()
        self.service._request = AsyncMock(side_effect=self.request)
        self.service.query_mention_posts = AsyncMock(return_value=[])
        self.service.query_recent_posts = AsyncMock(
            side_effect=lambda **kwargs: [self.post]
        )
        self.service.query_posts = AsyncMock(return_value=[])
        self.task_module, _ = _load_auto_comment_module()
        service = self.service
        task_module = self.task_module

        class Manager(self.task_module.TaskQzoneAutoCommentService):
            def __init__(self):
                super().__init__(*_interaction_args(task_module))
                self.config.qzone = {
                    "qzone_trigger_mode": "llm_smart",
                    "enable_qzone": True,
                    "qzone_enable_auto_comment": True,
                    "qzone_auto_comment_limit": 10,
                    "qzone_auto_comment_photo_batch_probability": 0,
                    "qzone_enable_auto_reply": True,
                    "qzone_auto_reply_limit": 10,
                    "qzone_auto_interaction_active_hours": 0,
                }
                self.runtime = replace(self.runtime, db=FakeDb())
                self.runtime = replace(
                    self.runtime,
                    plugin=types.SimpleNamespace(
                        _is_terminated=False,
                        qzone_service=service,
                        emit_dashboard_event=lambda *args, **kwargs: None,
                    ),
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
        if kwargs.get("data", {}).get("isfakereq") == 1:
            if self.batch_comment_html is None:
                raise RuntimeError("batch comments unavailable")
            return {"code": 0, "data": {"feeds": self.batch_comment_html}}
        if method == "POST":
            data = kwargs["data"]
            pic = next(
                item["picKey"]
                for item in self.payload["data"]["photos"]
                if data["topicId"]
                in (
                    {
                        f"album-1_{item['picKey']}_0_0",
                        f"album-1_{item['picKey']}_{item.get('batchId')}_4",
                    }
                    if url
                    in (
                        self.service.PHOTO_REPLY_URL,
                        self.service.PHOTO_BATCH_REPLY_URL,
                    )
                    or data.get("ref") == "feeds"
                    else {f"album-1_{item['picKey']}"}
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
            and not call.kwargs.get("data", {}).get("isfakereq")
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
            get_all_providers=lambda: [
                types.SimpleNamespace(
                    meta=lambda: types.SimpleNamespace(id="vision-provider")
                )
            ],
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
        responses.append(json.dumps({"code": 0, "data": {"feeds": ""}}))
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
            [call["method"] for call in session.calls], ["GET"] * 3 + ["POST"] * 2
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
                self.manager.runtime = replace(self.manager.runtime, db=FakeDb())
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
                self.manager.runtime = replace(self.manager.runtime, db=FakeDb())
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
                self.manager.runtime = replace(self.manager.runtime, db=FakeDb())
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
        self.assertGreater(
            call.kwargs["system_prompt"].index("只输出 JSON 对象"),
            call.kwargs["system_prompt"].index("生活聊天表达：自然、轻松。"),
        )
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

    async def test_single_photo_selection_sees_batch_but_focuses_selected_photo(
        self,
    ):
        self.use_image_vision(limit=3)
        self.vision.side_effect = [
            types.SimpleNamespace(completion_text="室内伸懒腰"),
            types.SimpleNamespace(completion_text="展厅里欣赏画作"),
            types.SimpleNamespace(completion_text="夕阳下坐在江边捧着饮料"),
        ]
        content = "伸个懒腰都这么惬意。"
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
        self.assertIn("评论针对本批中的一张照片", call.kwargs["system_prompt"])
        self.assertIn("评论聚焦该张", call.kwargs["system_prompt"])
        self.assertIn("不混入其他照片的细节", call.kwargs["system_prompt"])
        self.assertIn("可选提交落点", call.kwargs["prompt"])
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
                self.manager.runtime = replace(self.manager.runtime, db=FakeDb())
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
                self.manager.runtime = replace(self.manager.runtime, db=FakeDb())
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
                self.manager.runtime = replace(self.manager.runtime, db=FakeDb())
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

    def use_batch_comment(self, *, replace_params=(), replies=""):
        self.use_upload_capture()
        comment_html = (
            Path(__file__).parent / "fixtures/qzone_album_upload_comments.html"
        ).read_text()
        for old, new in replace_params:
            comment_html = comment_html.replace(old, new)
        if replies:
            comment_html = comment_html.rsplit("</li>", 1)[0] + (
                f'<div class="mod-comments-sub">{replies}</div></li>'
            )
        self.post = parse_feed(
            album_feed(html=upload_feed_html() + comment_html, photos=[])
        )
        self.service._remember_posts([self.post])
        self.manager.qzone_conf["qzone_auto_comment_reply_probability"] = 100

    async def test_upload_batch_comment_is_bound_to_one_verified_anchor(self):
        self.use_batch_comment()
        self.assertEqual(self.post.comments[0].content, "Nice photos!")
        self.comments["pic-2!!"] = [self.root("pic-2!!")]
        scopes = await self.service.query_photo_posts(self.post.key)
        self.assertEqual([len(post.comments) for post in scopes], [0, 1, 0, 1])
        self.assertEqual(
            scopes[0].photo_targets[0].verified_batch_topic_id,
            "album-1_pic-1!!_1790992589220000_4",
        )
        self.assertEqual(
            scopes[0].photo_targets[0].feed_comment_topic_id,
            "album-1_pic-1!!_0_0",
        )
        self.assertTrue(all(not post.comment_target_error for post in scopes))

    def use_remote_batch_comments(self):
        self.use_upload_capture()
        self.batch_comment_html = (
            Path(__file__).parent / "fixtures/qzone_album_upload_comments.html"
        ).read_text()
        self.manager.qzone_conf["qzone_auto_comment_reply_probability"] = 100

    async def test_missing_feed_comments_are_read_before_probability_reply(self):
        self.use_remote_batch_comments()
        self.assertEqual(self.post.comments, [])
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (2, 0))
        main, reply = self.writes()
        self.assertEqual(main.args[1], self.service.PHOTO_COMMENT_URL)
        self.assertEqual(reply.args[1], self.service.PHOTO_BATCH_REPLY_URL)
        data = reply.kwargs["data"]
        self.assertEqual(data["topicId"], "album-1_pic-1!!_1790992589220000_4")
        self.assertEqual((data["commentId"], data["commentUin"]), ("41", 30003))
        self.assertEqual((data["feedsType"], data["platformid"]), (100, 52))
        self.assertEqual((data["ref"], data["paramstr"]), ("feeds", 1))
        read = next(
            call
            for call in self.service._request.call_args_list
            if call.kwargs.get("data", {}).get("isfakereq") == 1
        )
        self.assertEqual(read.kwargs["data"]["feedsType"], 8)
        self.assertNotIn("content", read.kwargs["data"])
        self.assertLess(
            self.service._request.call_args_list.index(read),
            self.service._request.call_args_list.index(reply),
        )

    async def test_batch_probability_reply_can_join_two_distinct_users(self):
        self.use_remote_batch_comments()
        self.manager.qzone_conf["qzone_auto_comment_reply_user_limit"] = 2
        original = self.batch_comment_html
        self.batch_comment_html += (
            original.replace('data-tid="41"', 'data-tid="42"')
            .replace("cmtid=41", "cmtid=42")
            .replace('data-uin="30003"', 'data-uin="40004"')
        )
        first = await self.run_comment()
        second = await self.run_comment()
        self.assertEqual((first["commented"], second["commented"]), (3, 0))
        writes = self.writes()
        self.assertEqual(len(writes), 3)
        self.assertTrue(
            all(
                call.args[1] == self.service.PHOTO_BATCH_REPLY_URL
                for call in writes[1:]
            )
        )
        self.assertEqual(
            {call.kwargs["data"]["commentUin"] for call in writes[1:]}, {30003, 40004}
        )
        self.assertEqual(
            {call.kwargs["data"]["commentId"] for call in writes[1:]}, {"41", "42"}
        )

    async def test_batch_and_photo_replies_share_user_quota_across_rounds(self):
        self.use_remote_batch_comments()
        self.manager.qzone_conf.update(
            qzone_auto_comment_reply_user_limit=2, qzone_auto_comment_limit=1
        )
        photo_comment = self.root("pic-2!!")
        photo_comment["poster"]["id"] = 40004
        self.comments["pic-2!!"] = [photo_comment]
        results = [(await self.run_comment())["commented"] for _ in range(3)]
        self.assertEqual(results, [2, 1, 0])
        replies = self.writes()[1:]
        self.assertEqual(len(replies), 2)
        self.assertEqual(
            {call.args[1] for call in replies},
            {self.service.PHOTO_BATCH_REPLY_URL, self.service.PHOTO_REPLY_URL},
        )
        self.assertEqual(
            {call.kwargs["data"]["commentUin"] for call in replies}, {30003, 40004}
        )

    async def test_remote_comments_must_match_batch_owner_and_public_scope(self):
        self.use_remote_batch_comments()
        original = self.batch_comment_html
        for old, new in (
            ("oweruin=20002", "oweruin=40004"),
            ("batchId=1790992589220000", "batchId=1790992589220001"),
            ("zz=0", "zz=1"),
            ("cmtType=4", "cmtType=0"),
        ):
            with self.subTest(binding=new):
                self.batch_comment_html = original.replace(old, new)
                self.service._post_detail_cache_at.clear()
                scopes = await self.service.query_photo_posts(self.post.key)
                self.assertEqual(scopes[-1].comments, [])
                self.assertTrue(all(not post.comments for post in scopes))
        self.assertEqual(self.writes(), [])

    async def test_batch_detail_reuses_cache_then_reads_new_comments(self):
        self.use_remote_batch_comments()
        scopes = await self.service.query_photo_posts(self.post.key)
        batch = scopes[-1]
        self.assertEqual([item.tid for item in batch.comments], ["41"])
        before = self.service._request.call_count
        self.assertEqual((await self.service.detail(batch.key)).comments[0].tid, "41")
        self.assertEqual(self.service._request.call_count, before)
        self.batch_comment_html = self.batch_comment_html.replace(
            'tid="41"', 'tid="42"'
        ).replace("cmtid=41", "cmtid=42")
        self.service._post_detail_cache_at.pop(batch.key, None)
        refreshed = await self.service.detail(batch.key)
        self.assertEqual([item.tid for item in refreshed.comments], ["42"])
        self.assertEqual(self.service._request.call_count, before + 1)
        self.assertEqual(self.writes(), [])

    async def test_empty_remote_comments_remove_stale_feed_candidates(self):
        self.use_batch_comment()
        self.batch_comment_html = ""
        scopes = await self.service.query_photo_posts(self.post.key)
        self.assertEqual(scopes[-1].comments, [])

    async def test_upload_batch_comment_runs_after_main_and_is_not_repeated(self):
        self.use_batch_comment()
        self.manager.qzone_conf["qzone_auto_comment_limit"] = 1
        first = await self.run_comment()
        self.assertEqual((first["commented"], first["failed"]), (2, 0))
        main, reply = self.writes()
        self.assertEqual(main.args[1], self.service.PHOTO_COMMENT_URL)
        self.assertEqual(main.kwargs["data"]["topicId"], "album-1_pic-1!!")
        self.assertEqual(reply.args[1], self.service.PHOTO_BATCH_REPLY_URL)
        self.assertEqual(
            reply.kwargs["data"]["topicId"],
            "album-1_pic-1!!_1790992589220000_4",
        )
        self.assertEqual(reply.kwargs["data"]["commentId"], "41")
        self.assertEqual(reply.kwargs["data"]["commentUin"], 30003)
        self.assertEqual(reply.kwargs["data"]["hostUin"], 20002)
        self.assertIn("@{uin:30003", reply.kwargs["data"]["content"])
        second = await self.run_comment()
        self.assertEqual(second["commented"], 0)
        self.assertEqual(len(self.writes()), 2)

    async def test_upload_batch_comment_does_not_require_another_main_comment(self):
        self.use_batch_comment()
        self.comments["pic-3!!"] = [self.root("pic-3!!", bot=True)]
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (1, 0))
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.writes()[0].args[1], self.service.PHOTO_BATCH_REPLY_URL)

    async def test_batch_reply_uses_verified_feed_id_when_callback_omits_data_id(self):
        self.use_batch_comment()
        scopes = await self.service.query_photo_posts(self.post.key)
        batch = scopes[-1]
        root = batch.comments[0]
        photo = batch.photo_targets[0]
        root_html = (
            Path(__file__).parent / "fixtures/qzone_album_upload_comments.html"
        ).read_text()
        root_html = root_html.rsplit("</li>", 1)[0] + (
            '<div class="mod-comments-sub"><ul>'
            '<li class="comments-item" data-type="replyroot" '
            'data-tid="1790960000" data-uin="10001" data-nick="Bot">'
            '<div class="comments-content"><a class="nickname">Bot</a>'
            '回复<a class="nickname">Friend</a> : Thanks!</div>'
            "</li></ul></div></li>"
        )
        self.service._request = AsyncMock(
            return_value={
                "code": 0,
                "subcode": 0,
                "data": {"feeds": root_html},
            }
        )

        result = await self.service.reply_photo_comment(
            owner_uin=20002,
            album_id=photo.album_id,
            pic_key=photo.pic_key,
            feed_topic_id=root.raw_fields["photo_topic_id"],
            comment=root,
            content="Thanks!",
        )

        self.assertEqual(result["reply_id"], "1790960000")
        self.assertEqual(result["transport"], "photo_reply")
        self.service._request.assert_awaited_once()

    async def test_batch_reply_without_matching_feed_entry_stays_unknown(self):
        self.use_batch_comment()
        scopes = await self.service.query_photo_posts(self.post.key)
        batch = scopes[-1]
        root = batch.comments[0]
        photo = batch.photo_targets[0]
        wrong_root_html = (
            (Path(__file__).parent / "fixtures/qzone_album_upload_comments.html")
            .read_text()
            .replace('data-tid="41"', 'data-tid="42"')
        )
        self.service._request = AsyncMock(
            return_value={
                "code": 0,
                "subcode": 0,
                "data": {"feeds": wrong_root_html},
            }
        )

        with self.assertRaisesRegex(RuntimeError, "状态未知") as error:
            await self.service.reply_photo_comment(
                owner_uin=20002,
                album_id=photo.album_id,
                pic_key=photo.pic_key,
                feed_topic_id=root.raw_fields["photo_topic_id"],
                comment=root,
                content="Thanks!",
            )

        self.assertTrue(error.exception.submission_unknown)
        self.service._request.assert_awaited_once()

    async def test_upload_batch_comment_requires_exact_public_binding(self):
        for old, new in (
            ("oweruin=20002", "oweruin=40004"),
            ("albumid=album-1", "albumid=other-album"),
            ("lloc=pic-1!!", "lloc=pic-2!!"),
            ("batchId=1790992589220000", "batchId=1790992589220001"),
            ("cmtType=4", "cmtType=0"),
            ("cmtid=41", "cmtid=42"),
            ("zz=0", "zz=1"),
            ("zz=0", "zz="),
            ("oweruin=20002", "oweruin=20002&amp;oweruin=40004"),
            ("http://photo.qq.com/", "http://unrelated.example/"),
            ("http://photo.qq.com/", "http://[invalid/"),
        ):
            with self.subTest(binding=new):
                self.use_batch_comment(replace_params=[(old, new)])
                scopes = await self.service.query_photo_posts(self.post.key)
                self.assertEqual([len(post.comments) for post in scopes], [0, 0, 0, 0])
        self.assertEqual(self.writes(), [])

    async def test_existing_bot_reply_in_batch_thread_prevents_repeat_join(self):
        self.use_batch_comment(
            replies="""
            <li class="comments-item" data-type="replyroot" data-tid="1"
                data-uin="10001" data-nick="Bot">
              <div class="comments-content"><a class="nickname">Bot</a> :
                Already joined this thread
              </div>
            </li>
        """
        )
        scopes = await self.service.query_photo_posts(self.post.key)
        root, reply = scopes[-1].comments
        self.assertEqual(reply.parent_tid, root.tid)
        self.assertEqual(reply.uin, 10001)
        self.assertEqual(
            reply.raw_fields["photo_topic_id"], root.raw_fields["photo_topic_id"]
        )
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (1, 0))
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.writes()[0].args[1], self.service.PHOTO_COMMENT_URL)

    def use_batch_conversation(self, *, owner_reply=None):
        bot = batch_reply_html(1790997800, 10001, "Bot", 30003, "Other", "Nice!")
        owner = owner_reply or batch_reply_html(
            1790997849, 20002, "Owner", 10001, "Bot", "What do you think?"
        )
        other = batch_reply_html(1790997908, 30003, "Other", 10001, "Bot", "I agree!")
        self.batch_replies = bot + owner + other
        self.use_batch_comment(replies=self.batch_replies)
        self.batch_comment_html = batch_thread_html(self.batch_replies)
        self.comments["pic-3!!"] = [self.root("pic-3!!", bot=True)]

    def batch_candidates(self, posts):
        candidate = sys.modules[f"{self.task_module.__package__}.interact.candidate"]
        return candidate._qzone_friend_thread_comment_candidates(
            self.manager, posts, self_uin=10001, processed={}
        )

    async def test_batch_join_keeps_both_people_replying_to_bot_as_candidates(self):
        self.use_batch_conversation()
        scopes = await self.service.query_photo_posts(self.post.key)
        root, bot, owner, other = scopes[-1].comments
        self.assertEqual(bot.reply_to_tid, root.tid)
        self.assertEqual(bot.create_time, 1790997800)
        for reply in (owner, other):
            self.assertEqual(reply.reply_to_uin, 10001)
            self.assertEqual(reply.reply_to_tid, bot.tid)
            self.assertEqual(reply.reply_to_tid_source, "photo_mention")
            self.assertEqual(reply.raw_fields["photo_root_id"], root.tid)
            self.assertEqual(reply.raw_fields["photo_root_uin"], root.uin)
        self.assertEqual(
            [item.comment.uin for item in self.batch_candidates(scopes)],
            [30003, 20002],
        )

    async def test_batch_bot_root_can_continue_without_precise_root_timestamp(self):
        reply = batch_reply_html(1790997849, 20002, "Owner", 10001, "Bot", "Hi!")
        self.use_batch_comment(replies=reply)
        self.batch_comment_html = batch_thread_html(reply).replace(
            'data-uin="30003" data-nick="Friend"',
            'data-uin="10001" data-nick="Bot"',
        )
        scopes = await self.service.query_photo_posts(self.post.key)
        root, child = scopes[-1].comments
        self.assertEqual(root.create_time, 0)
        self.assertEqual(child.reply_to_tid, root.tid)
        self.assertEqual(child.reply_to_uin, 10001)
        self.assertEqual(
            [item.comment.uin for item in self.batch_candidates(scopes)], [20002]
        )

    async def test_reordered_duplicate_batch_replies_keep_stable_candidates(self):
        self.use_batch_conversation()
        items = self.batch_replies.split("</li>")
        self.batch_comment_html = batch_thread_html(
            "".join(items[index] + "</li>" for index in (2, 0, 1, 1))
        )
        scopes = await self.service.query_photo_posts(self.post.key)
        self.assertEqual(len(scopes[-1].comments), 4)
        self.assertEqual(
            [item.comment.raw_tid for item in self.batch_candidates(scopes)],
            ["1790997908", "1790997849"],
        )

    async def test_batch_conversation_continues_across_people_and_rounds_without_repeat(
        self,
    ):
        self.use_batch_conversation()
        submitted = 0

        async def request(method, url, **kwargs):
            nonlocal submitted
            if url != self.service.PHOTO_BATCH_REPLY_URL:
                return await self.request(method, url, **kwargs)
            submitted += 1
            data = kwargs["data"]
            self.assertEqual(data["commentId"], "41")
            self.assertEqual(data["commentUin"], 30003)
            target = 20002 if "uin:20002," in data["content"] else 30003
            reply_id = 1790998100 + submitted if submitted <= 2 else 1790998300
            self.batch_replies += batch_reply_html(
                reply_id, 10001, "Bot", target, "Friend", "Thanks!"
            )
            self.batch_comment_html = batch_thread_html(self.batch_replies)
            # 与实际抓包一致：成功回包只有整楼 HTML，没有 data.id。
            return {"code": 0, "subcode": 0, "data": {"feeds": self.batch_comment_html}}

        self.service._request = AsyncMock(side_effect=request)
        first = await self.run_comment()
        self.assertEqual((first["commented"], first["failed"]), (2, 0))
        self.assertEqual([item[2] for item in self.manager.generated], [30003, 20002])
        state = self.manager.db.state[self.task_module.QZONE_AUTO_COMMENT_STATE_KEY][
            "processed"
        ]
        confirmed = [item for item in state.values() if item.get("verification_status")]
        self.assertEqual(len(confirmed), 2)
        self.assertTrue(
            all(item["verification_status"] == "confirmed" for item in confirmed)
        )
        self.assertEqual((await self.run_comment())["commented"], 0)

        self.batch_replies += batch_reply_html(
            1790998200, 30003, "Other", 10001, "Bot", "One more thing!"
        )
        self.batch_comment_html = batch_thread_html(self.batch_replies)
        self.service._post_detail_cache_at.clear()
        second = await self.run_comment()
        self.assertEqual((second["commented"], second["failed"]), (1, 0))
        self.assertEqual(submitted, 3)
        self.manager.runtime = replace(self.manager.runtime, db=FakeDb())
        self.service._post_detail_cache_at.clear()
        self.assertEqual((await self.run_comment())["commented"], 0)
        self.assertEqual(submitted, 3)

    async def test_batch_reply_uses_batch_readback_when_callback_omits_feeds(self):
        self.use_batch_conversation()
        scopes = await self.service.query_photo_posts(self.post.key)
        candidate = self.batch_candidates(scopes)[0]
        self.batch_replies += batch_reply_html(
            1790998100, 10001, "Bot", 30003, "Other", "Thanks!"
        )
        self.batch_comment_html = batch_thread_html(self.batch_replies)
        self.service.query_photo = AsyncMock(side_effect=AssertionError("wrong scope"))

        async def request(method, url, **kwargs):
            if url == self.service.PHOTO_BATCH_REPLY_URL:
                return {"code": 0, "subcode": 0, "data": {"id": 1790998100}}
            return await self.request(method, url, **kwargs)

        self.service._request = AsyncMock(side_effect=request)
        result = await self.service.reply_photo_comment(
            owner_uin=20002,
            album_id="album-1",
            pic_key="pic-1!!",
            feed_topic_id=candidate.post.photo_batch_topic_id,
            comment=candidate.comment,
            parent_comment=candidate.parent_comment,
            content="Thanks!",
        )
        self.assertEqual(result["verification_status"], "confirmed")
        self.service.query_photo.assert_not_awaited()
        self.assertEqual(len(self.writes()), 1)

    async def test_batch_reply_with_missing_or_conflicting_recipient_is_not_candidate(
        self,
    ):
        valid = batch_reply_html(1790997849, 20002, "Owner", 10001, "Bot", "Hi!")
        for invalid in (
            valid.replace('link="nameCard_10001"', "").replace(
                'href="http://user.qzone.qq.com/10001"', ""
            ),
            valid.replace("nameCard_10001", "nameCard_40004"),
            valid.replace('data-tid="1790997849"', 'data-tid="2"'),
            valid.replace("Hi!", "Hi! @{uin:40004}"),
            valid.replace("nameCard_10001", "nameCard_40004").replace(
                "qzone.qq.com/10001", "qzone.qq.com/40004"
            ),
        ):
            with self.subTest(invalid=invalid):
                self.use_batch_conversation(owner_reply=invalid)
                self.service._post_detail_cache_at.clear()
                scopes = await self.service.query_photo_posts(self.post.key)
                self.assertEqual(
                    [item.comment.uin for item in self.batch_candidates(scopes)],
                    [30003],
                )
        self.assertEqual(self.writes(), [])

    async def test_batch_comment_cannot_be_submitted_to_another_photo_or_owner(self):
        self.use_batch_comment()
        scopes = await self.service.query_photo_posts(self.post.key)
        comment = scopes[-1].comments[0]
        for owner, pic, topic in (
            (40004, "pic-1!!", "album-1_pic-1!!_1790992589220000_4"),
            (20002, "pic-2!!", "album-1_pic-1!!_1790992589220000_4"),
            (20002, "pic-1!!", "album-1_pic-1!!_1790992589220001_4"),
            (20002, "pic-1!!", "album-1_pic-1!!_0_0"),
        ):
            with self.subTest(owner=owner, pic=pic, topic=topic):
                with self.assertRaises(RuntimeError):
                    await self.service.reply_photo_comment(
                        owner_uin=owner,
                        album_id="album-1",
                        pic_key=pic,
                        feed_topic_id=topic,
                        comment=comment,
                        content="Reply",
                    )
        self.assertEqual(self.writes(), [])

    async def test_whole_batch_main_uses_captured_feed_form_and_all_images(self):
        self.use_upload_capture()
        self.manager.qzone_conf.pop("qzone_auto_comment_photo_batch_probability")
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (1, 0))
        self.assertEqual(len(self.writes()), 1)
        data = self.writes()[0].kwargs["data"]
        self.assertEqual(data["topicId"], "album-1_pic-1!!_1790992589220000_4")
        self.assertEqual(
            (data["feedsType"], data["platformid"], data["ref"]), (100, 52, "feeds")
        )
        self.assertEqual(
            (data["hostUin"], data["uin"], data["private"]), (20002, 10001, 0)
        )
        self.assertEqual(data["paramstr"], 1)
        for field in ("albumId", "picKey", "commentUin", "commentId"):
            self.assertNotIn(field, data)
        self.assertEqual(
            self.manager.generated[0][2],
            [f"https://photo.example/photo-{i}.jpg" for i in (1, 2, 3)],
        )
        self.assertEqual((await self.run_comment())["commented"], 0)
        self.assertEqual(len(self.writes()), 1)

    async def test_batch_probability_rolls_once_and_respects_boundary(self):
        self.use_upload_capture()
        scopes = await self.service.query_photo_posts(self.post.key)
        discuss = sys.modules[
            f"{self.task_module.__package__}.interact.executors.discuss"
        ]
        self.manager.qzone_conf["qzone_auto_comment_photo_batch_probability"] = 50
        ctx = await self.service.context()
        for value, scope in ((0.499, "batch"), (0.5, "photo")):
            with (
                self.subTest(value=value),
                patch.object(discuss.random, "random", return_value=value) as draw,
            ):
                generated = await discuss._generate_qzone_comment_target(
                    self.manager,
                    scopes[0],
                    scopes,
                    ctx,
                    {},
                    {},
                    target_umo="",
                    skip_post_keys=set(),
                )
                self.assertEqual(generated[0].photo_comment_scope, scope)
                draw.assert_called_once_with()

    async def test_fixed_probability_modes_do_not_draw_random(self):
        self.use_upload_capture()
        scopes = await self.service.query_photo_posts(self.post.key)
        discuss = sys.modules[
            f"{self.task_module.__package__}.interact.executors.discuss"
        ]
        for probability, scope in ((0, "photo"), (100, "batch")):
            self.manager.qzone_conf["qzone_auto_comment_photo_batch_probability"] = (
                probability
            )
            with (
                self.subTest(probability=probability),
                patch.object(
                    discuss.random,
                    "random",
                    side_effect=AssertionError("Unexpected random draw"),
                ),
            ):
                generated = await discuss._generate_qzone_comment_target(
                    self.manager,
                    scopes[0],
                    scopes,
                    await self.service.context(),
                    {},
                    {},
                    target_umo="",
                    skip_post_keys=set(),
                )
                self.assertEqual(generated[0].photo_comment_scope, scope)

    async def test_whole_batch_vision_shares_budget_and_cache_with_single_mode(self):
        self.use_upload_capture()
        self.use_image_vision(limit=2)
        scopes = await self.service.query_photo_posts(self.post.key)
        state = {}
        await self.manager.generate_qzone_auto_photo_comment(
            scopes[0], scopes[:-1], state=state
        )
        self.assertEqual(self.vision.await_count, 2)
        self.manager.plugin.call_llm.return_value = "这组拍得很惬意。"
        await self.manager.generate_qzone_auto_comment(scopes[-1], state=state)
        self.assertEqual(self.vision.await_count, 2)
        prompt = self.manager.plugin.call_llm.call_args.kwargs["prompt"]
        self.assertIn("评论范围：整组上传照片", prompt)
        self.assertIn("Visible details of https://photo.example/photo-1.jpg", prompt)
        self.assertIn("Visible details of https://photo.example/photo-2.jpg", prompt)
        self.assertNotIn("Visible details of https://photo.example/photo-3.jpg", prompt)

    async def test_whole_batch_pending_retry_survives_probability_change(self):
        self.use_upload_capture()
        scopes = await self.service.query_photo_posts(self.post.key)
        tracker = sys.modules[f"{self.task_module.__package__}.interact.tracker"]
        processed = {}
        tracker._mark_qzone_post_processed(
            processed,
            scopes[-1],
            "retry_later",
            content="Saved batch caption",
            photo_target_key=tracker._photo_target_key(scopes[-1]),
        )
        self.manager.db.state[self.task_module.QZONE_AUTO_COMMENT_STATE_KEY] = {
            "processed": processed
        }
        self.manager.qzone_conf["qzone_auto_comment_photo_batch_probability"] = 0
        self.post.photo_targets.reverse()
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (1, 0))
        self.assertEqual(self.manager.generated, [])
        data = self.writes()[0].kwargs["data"]
        self.assertEqual(
            (data["ref"], data["content"]), ("feeds", "Saved batch caption")
        )
        self.assertEqual(data["topicId"], "album-1_pic-1!!_1790992589220000_4")

    async def test_batch_main_then_batch_reply_are_independent_and_deduplicated(self):
        self.use_batch_comment()
        self.manager.qzone_conf["qzone_auto_comment_photo_batch_probability"] = 100
        self.manager.qzone_conf["qzone_auto_comment_limit"] = 1
        result = await self.run_comment()
        self.assertEqual((result["commented"], result["failed"]), (2, 0))
        main, reply = self.writes()
        self.assertEqual(main.kwargs["data"]["ref"], "feeds")
        self.assertEqual(reply.args[1], self.service.PHOTO_BATCH_REPLY_URL)
        self.assertEqual(
            main.kwargs["data"]["topicId"], reply.kwargs["data"]["topicId"]
        )
        self.assertEqual(reply.kwargs["data"]["commentId"], "41")
        self.assertEqual((await self.run_comment())["commented"], 0)
        self.assertEqual(len(self.writes()), 2)

    async def test_batch_and_photo_comments_with_same_id_do_not_share_thread_state(
        self,
    ):
        self.use_batch_comment()
        self.comments["pic-1!!"] = [self.root("pic-1!!")]
        scopes = await self.service.query_photo_posts(self.post.key)
        tracker = sys.modules[f"{self.task_module.__package__}.interact.tracker"]
        self.assertEqual(scopes[0].comments[0].tid, scopes[-1].comments[0].tid)
        photo_key = tracker._comment_key(scopes[0], scopes[0].comments[0])
        batch_key = tracker._comment_key(scopes[-1], scopes[-1].comments[0])
        self.assertNotEqual(photo_key, batch_key)
        self.assertIn(":photo-batch:", batch_key)
        self.service._post_detail_cache_at.clear()
        self.service.query_photo = AsyncMock(
            side_effect=AssertionError("Batch detail must not read single photo")
        )
        detailed = await self.service.detail(scopes[-1].key)
        self.assertEqual([c.content for c in detailed.comments], ["Nice photos!"])

    async def test_unverified_batch_cannot_submit_or_reconstruct_as_mood(self):
        self.use_upload_capture()
        scopes = await self.service.query_photo_posts(self.post.key)
        batch = scopes[-1]
        bad = replace(batch, photo_batch_topic_id="album-1_pic-2!!_1790992589220000_4")
        self.service._remember_posts([bad])
        with self.assertRaisesRegex(RuntimeError, "未经"):
            await self.service.comment(bad.key, "Caption")
        self.service._post_cache.pop(batch.key, None)
        with self.assertRaisesRegex(RuntimeError, "引用已失效"):
            self.service._require_post(batch.key)
        self.assertEqual(self.writes(), [])

    def test_batch_probability_defaults_and_clamps_preserve_zero(self):
        options = sys.modules[f"{self.task_module.__package__}.interact.options"]
        config = options.QzoneAutoInteractionConfig
        self.assertEqual(config.from_conf({}).comment_photo_batch_probability, 100)
        for value, expected in (
            (0, 0),
            (50, 50),
            (100, 100),
            (-1, 0),
            (101, 100),
            ("invalid", 100),
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    config.from_conf(
                        {"qzone_auto_comment_photo_batch_probability": value}
                    ).comment_photo_batch_probability,
                    expected,
                )

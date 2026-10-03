"""相册二级回评：按抓包构造脱敏表单，禁止网络实发和跨照片落点。"""

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from .testqzone import _load_qzone_service, _new_qzone_service
from .testqzonecomment import FakeDb, _load_auto_comment_module
from .testqzonephotoauto import PhotoResponseSession, album_feed, parse_feed


def reply_response():
    return (
        Path(__file__).parent / "fixtures/qzone_album_reply_success.html"
    ).read_text(encoding="utf-8")


def viewer_response(owner=10001, *, private=0, topic="album-1_pic-1!!_0_0"):
    return {
        "code": 0,
        "data": {
            "photos": [{"albumId": "album-1", "picKey": "pic-1!!", "ownerUin": owner}],
            "single": {
                "comments": [
                    {
                        "id": 41,
                        "content": "好看",
                        "poster": {"id": 30003, "name": "Tester"},
                        "topicId": topic,
                        "private": private,
                    },
                    {"id": 42, "content": "我的评论", "poster": {"id": owner}},
                ]
            },
        },
    }


class AlbumReplyTransportTests(unittest.IsolatedAsyncioTestCase):
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
        self.comment = self.module.QzoneComment(
            tid="41", uin=30003, nickname="Tester", content="好看"
        )

    async def test_reply_uses_exact_captured_form_and_separate_actor_ids(self):
        self.service._request = AsyncMock(return_value={"code": 0, "data": {"id": 43}})
        result = await self.service.reply_comment(self.post.key, self.comment, "像你")
        self.service._request.assert_awaited_once()
        call = self.service._request.call_args
        self.assertEqual(call.args[:2], ("POST", self.service.PHOTO_REPLY_URL))
        self.assertEqual(
            call.kwargs["data"],
            {
                "uin": 10001,
                "hostUin": 20002,
                "topicId": "album-1_pic-1!!_0_0",
                "commentId": "41",
                "commentUin": 30003,
                "content": "@{uin:30003,nick:Tester,auto:1} 像你",
                "inCharset": "utf-8",
                "outCharset": "utf-8",
                "ref": "photo",
                "need_private_comment": 1,
                "albumId": "album-1",
                "qzone": "qzone",
                "plat": "qzone",
                "private": 0,
                "with_fwd": 0,
                "to_tweet": 0,
                "qzreferrer": "https://user.qzone.qq.com/20002",
            },
        )
        self.assertEqual(
            call.kwargs["params"], {"g_tk": (await self.service.context()).gtk}
        )
        self.assertEqual(
            call.kwargs["headers"]["Referer"], "https://user.qzone.qq.com/20002"
        )
        self.assertEqual(
            call.kwargs["headers"]["Content-Type"],
            "application/x-www-form-urlencoded;charset=UTF-8",
        )
        self.assertFalse(call.kwargs["retry_parse_error"])
        self.assertEqual(result["transport"], "photo_reply")
        self.assertEqual(result["comment_id"], "41")
        self.assertEqual(result["reply_id"], "43")

    async def test_html_callback_is_parsed_by_real_gateway_without_duplicate_mention(
        self,
    ):
        session = PhotoResponseSession(reply_response())
        self.service._http = AsyncMock(return_value=session)
        result = await self.service.reply_comment(
            self.post.key, self.comment, "@{uin:30003,nick:Tester,auto:1} 像你"
        )
        self.assertEqual(result["reply_id"], "1790955016")
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(session.calls[0]["data"]["content"].count("@{"), 1)
        self.assertEqual(session.calls[0]["cookies"]["p_skey"], "dummy")

    async def test_invalid_or_nested_targets_are_rejected_before_network(self):
        invalid = [
            self.module.QzoneComment(tid="", uin=30003),
            self.module.QzoneComment(tid="41_r_2_30003", uin=30003),
            self.module.QzoneComment(tid="41", uin=0),
            self.module.QzoneComment(tid="41", uin=30003, parent_tid="40"),
            self.module.QzoneComment(tid="41", uin=30003, reply_to_tid="40"),
            self.module.QzoneComment(
                tid="41", uin=30003, raw_fields={"photo_private": 1}
            ),
            self.module.QzoneComment(
                tid="41", uin=30003, raw_fields={"photo_topic_id": "another-photo"}
            ),
        ]
        self.service._request = AsyncMock()
        for comment in invalid:
            with self.subTest(comment=comment):
                with self.assertRaises(RuntimeError):
                    await self.service.reply_comment(self.post.key, comment, "hello")
        with self.assertRaisesRegex(RuntimeError, "二级回复 ID无效"):
            await self.service.reply_comment(
                self.post.key, self.comment, "hello", parent_comment=self.comment
            )
        with self.assertRaisesRegex(RuntimeError, "不能为空"):
            await self.service.reply_comment(self.post.key, self.comment, " ")
        self.service._request.assert_not_awaited()

    async def test_missing_or_multiple_photos_never_fall_back_to_mood(self):
        self.service._request = AsyncMock()
        for targets in ([], self.post.photo_targets * 2):
            self.post.photo_targets = targets
            with self.assertRaises(RuntimeError):
                await self.service.reply_comment(self.post.key, self.comment, "hello")
        self.service._request.assert_not_awaited()

    async def test_parameter_error_does_not_retry_or_clear_success_cache(self):
        for payload in (
            {"code": -10004, "message": "参数错误", "_http_status": 200},
            {"code": 0, "subcode": -10004, "data": {"id": 43}},
        ):
            with self.subTest(payload=payload):
                self.service._request = AsyncMock(return_value=payload)
                with patch.object(
                    self.service, "_invalidate_qzone_cache"
                ) as invalidate:
                    with self.assertRaisesRegex(
                        RuntimeError, "transport=photo_reply"
                    ) as error:
                        await self.service.reply_comment(
                            self.post.key, self.comment, "hello"
                        )
                    self.assertFalse(
                        getattr(error.exception, "submission_unknown", False)
                    )
                    self.assertEqual(
                        error.exception.attempted_targets,
                        [{"comment_id": "41", "comment_uin": 30003}],
                    )
                    invalidate.assert_not_called()
                self.service._request.assert_awaited_once()

    async def test_blank_success_without_id_and_timeout_are_unknown_not_success(self):
        for payload in (
            {"code": -1, "_http_status": 200},
            {"code": 0, "data": {}},
            {"code": 0, "data": {"id": 0}},
        ):
            with self.subTest(payload=payload):
                self.service._request = AsyncMock(return_value=payload)
                with self.assertRaises(RuntimeError) as error:
                    await self.service.reply_comment(
                        self.post.key, self.comment, "hello"
                    )
                self.assertTrue(error.exception.submission_unknown)
                self.service._request.assert_awaited_once()
        self.service._request = AsyncMock(side_effect=RuntimeError("请求超时"))
        with self.assertRaisesRegex(RuntimeError, "photo_reply") as error:
            await self.service.reply_comment(self.post.key, self.comment, "hello")
        self.assertTrue(error.exception.submission_unknown)

    async def test_viewer_conversion_preserves_topic_private_and_existing_thread(self):
        self.post.comments = [
            self.comment,
            self.module.QzoneComment(
                tid="43",
                uin=10001,
                content="已回评",
                parent_tid="41",
                reply_to_tid="41",
            ),
        ]
        self.service._request = AsyncMock(
            return_value=viewer_response(owner=20002, private=1)
        )
        post = await self.service.detail(self.post.key)
        root = next(comment for comment in post.comments if comment.tid == "41")
        self.assertEqual(root.uin, 30003)
        self.assertEqual(root.raw_fields["photo_topic_id"], "album-1_pic-1!!_0_0")
        self.assertEqual(root.raw_fields["photo_private"], 1)
        self.assertTrue(any(comment.parent_tid == "41" for comment in post.comments))


class AlbumAutoReplyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.module, self.models = _load_auto_comment_module()
        service_module = _load_qzone_service()
        self.service = _new_qzone_service(service_module)
        self.service.context = AsyncMock(
            return_value=service_module.QzoneContext(
                uin=10001, skey="dummy", p_skey="dummy"
            )
        )
        self.post = parse_feed(
            album_feed(
                uin=10001,
                photos=[{"albumId": "album-1", "picKey": "pic-1!!", "ownerUin": 10001}],
            )
        )
        friend = parse_feed(album_feed())
        self.service._remember_posts([self.post, friend])
        self.service.query_posts = AsyncMock(return_value=[])
        self.service.query_recent_posts = AsyncMock(return_value=[friend, self.post])

        async def request(method, url, **kwargs):
            if method == "GET":
                return viewer_response()
            return {"code": 0, "data": {"id": 43}}

        self.service._request = AsyncMock(side_effect=request)
        service = self.service

        class Manager(self.module.TaskQzoneAutoCommentService):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_reply": True,
                    "qzone_auto_reply_limit": 3,
                    "qzone_auto_interaction_active_hours": 0,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=service,
                    emit_dashboard_event=lambda *args, **kwargs: None,
                )
                self.generated_for = []

            async def _generate_qzone_auto_reply(self, post, comment, **kwargs):
                self.generated_for.append((post.key, comment.tid, comment.uin))
                return "像你"

        self.manager = Manager()

    async def run_task(self):
        with patch.object(self.module.asyncio, "sleep", new=AsyncMock()):
            return await self.manager.execute_qzone_auto_reply()

    async def test_scans_own_album_replies_once_and_deduplicates_changed_feed_key(self):
        first = await self.run_task()
        self.assertEqual(first["replied"], 1)
        self.assertEqual(first["failed"], 0)
        self.assertEqual(self.manager.generated_for, [(self.post.key, "41", 30003)])
        calls = self.service._request.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].args[:2], ("GET", self.service.PHOTO_VIEW_URL))
        self.assertEqual(calls[1].args[:2], ("POST", self.service.PHOTO_REPLY_URL))
        self.assertEqual(calls[1].kwargs["data"]["hostUin"], 10001)
        state = self.manager.db.state[self.module.QZONE_AUTO_REPLY_STATE_KEY]
        entry = state["processed"]["10001:photo:album-1:pic-1!!:41"]
        self.assertEqual(entry["action"], "replied")
        self.assertEqual(entry["submitted_transport"], "photo_reply")
        self.assertEqual(entry["submitted_comment_uin"], 30003)
        self.assertEqual(entry["submitted_reply_id"], "43")
        self.post.tid = "changed-feed-key"
        self.service._remember_posts([self.post])
        second = await self.run_task()
        self.assertEqual(second["replied"], 0)
        self.assertEqual(len(self.manager.generated_for), 1)
        self.assertEqual(
            sum(
                call.args[0] == "POST" for call in self.service._request.call_args_list
            ),
            1,
        )

    async def test_album_discovery_failure_does_not_abort_mood_scan(self):
        self.service.query_recent_posts.side_effect = RuntimeError("recent unavailable")
        result = await self.run_task()
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["replied"], 0)
        self.service.query_posts.assert_awaited_once()

    async def test_mood_scan_failure_does_not_abort_available_album(self):
        self.service.query_posts.side_effect = RuntimeError("mood unavailable")
        result = await self.run_task()
        self.assertEqual(result["replied"], 1)
        self.assertEqual(result["failed"], 0)

    async def test_unresolved_private_or_foreign_topic_skips_model_and_post(self):
        for response in (
            viewer_response(private=1),
            viewer_response(topic="other-photo"),
        ):
            with self.subTest(response=response):
                self.service._post_detail_cache_at.clear()
                self.service._request = AsyncMock(return_value=response)
                result = await self.run_task()
                self.assertEqual(result["replied"], 0)
                self.assertEqual(self.manager.generated_for, [])
                self.assertTrue(
                    all(
                        call.args[0] == "GET"
                        for call in self.service._request.call_args_list
                    )
                )
        self.post.photo_targets = []
        self.service._request.reset_mock()
        await self.run_task()
        self.service._request.assert_not_awaited()

    async def test_unknown_submission_is_persisted_and_not_retried_next_run(self):
        async def request(method, url, **kwargs):
            return (
                viewer_response()
                if method == "GET"
                else {"code": -1, "_http_status": 200, "_raw_blank": True}
            )

        self.service._request.side_effect = request
        first = await self.run_task()
        self.assertEqual(first["replied"], 0)
        self.assertGreaterEqual(first["skipped"], 1)
        entry = self.manager.db.state[self.module.QZONE_AUTO_REPLY_STATE_KEY][
            "processed"
        ]["10001:photo:album-1:pic-1!!:41"]
        self.assertTrue(entry["submission_unknown"])
        self.assertEqual(entry["action"], "skipped")
        await self.run_task()
        self.assertEqual(
            sum(
                call.args[0] == "POST" for call in self.service._request.call_args_list
            ),
            1,
        )

    async def test_nested_targets_are_not_enabled_as_root_replies(self):
        self.post.comments = [
            self.models.QzoneComment(
                tid="51",
                uin=30003,
                content="继续聊",
                parent_tid="41",
                reply_to_tid="41",
            )
        ]
        response = viewer_response()
        response["data"]["single"]["comments"] = []
        self.service._request.return_value = response
        self.service._request.side_effect = None
        result = await self.run_task()
        self.assertEqual(result["replied"], 0)
        self.assertEqual(self.manager.generated_for, [])

    async def test_duplicate_photo_candidate_keys_are_collapsed(self):
        candidate_module = sys.modules[f"{self.module.__package__}.interact.candidate"]
        comment = self.models.QzoneComment(tid="41", uin=30003, content="hello")
        self.post.comments = [comment]
        duplicate = self.models.QzonePost(
            uin=self.post.uin,
            tid="another-feed",
            appid=4,
            photo_targets=self.post.photo_targets,
            comments=[comment],
        )
        result = {"scanned": 0, "skipped": 0}
        candidates = candidate_module._qzone_self_reply_candidates(
            self.manager,
            [self.post, duplicate],
            self_uin=10001,
            processed={},
            result=result,
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].item_key, "10001:photo:album-1:pic-1!!:41")

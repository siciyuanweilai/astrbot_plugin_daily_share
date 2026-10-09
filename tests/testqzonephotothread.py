"""使用虚拟身份验证照片查看器的对话抓包，不执行真实写入。"""

import copy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from .testqzone import _load_qzone_service, _new_qzone_service, _parser
from .testqzonecomment import FakeDb, _load_auto_comment_module
from .testqzonephotoauto import PhotoResponseSession, album_feed, parse_feed


def viewer_capture(*, answered=True):
    text = (
        Path(__file__).parent / "fixtures/qzone_album_thread_viewer.jsonp"
    ).read_text()
    payload = _parser().parse_qzone_response(text)
    if not answered:
        payload["data"]["single"]["comments"][0]["replies"].pop()
    return payload


def multi_author_capture(*, answered=True):
    text = (
        Path(__file__).parent / "fixtures/qzone_album_multiauthor_viewer.jsonp"
    ).read_text()
    payload = _parser().parse_qzone_response(text)
    if not answered:
        payload["data"]["single"]["comments"][0]["replies"].pop()
    return payload


class PhotoThreadTests(unittest.IsolatedAsyncioTestCase):
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
        self.post = parse_feed(album_feed())
        self.service._remember_posts([self.post])
        self.task_module, _ = _load_auto_comment_module()
        service = self.service

        class Manager(self.task_module.TaskQzoneAutoCommentService):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_comment": True,
                    "qzone_auto_comment_limit": 1,
                    "qzone_auto_interaction_active_hours": 0,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=service,
                    emit_dashboard_event=lambda *args, **kwargs: None,
                )
                self.generated_for = []

            async def _generate_qzone_auto_reply_thread(
                self, post, parent, comment, **kwargs
            ):
                self.generated_for.append((parent.tid, comment.tid, comment.uin))
                return "Thanks!"

        self.manager = Manager()
        self.service.query_mention_posts = AsyncMock(return_value=[])

        async def recent(**kwargs):
            return [await self.service.detail(self.post.key)]

        self.service.query_recent_posts = AsyncMock(side_effect=recent)

    async def detail(self, payload):
        self.service._post_detail_cache_at.clear()
        self.service._request = AsyncMock(return_value=payload)
        return await self.service.detail(self.post.key)

    def candidates(self, posts=None):
        candidate = sys.modules[f"{self.task_module.__package__}.interact.candidate"]
        return candidate._qzone_friend_thread_comment_candidates(
            self.manager,
            posts or [self.post],
            self_uin=10001,
            processed={},
        )

    async def run_task(self):
        with patch("asyncio.sleep", new=AsyncMock()):
            return await self.manager.execute_qzone_auto_comment()

    def mock_thread_submissions(self, payload):
        submitted = 0

        async def request(method, url, **kwargs):
            nonlocal submitted
            if method == "GET":
                return copy.deepcopy(payload)
            self.assertEqual(url, self.service.PHOTO_REPLY_URL)
            submitted += 1
            reply_id = 1790998100 + submitted
            root = next(
                root
                for root in payload["data"]["single"]["comments"]
                if str(root["id"]) == kwargs["data"]["commentId"]
            )
            root["replies"].append(
                {
                    "id": reply_id,
                    "postTime": reply_id,
                    "poster": {"id": 10001, "name": "Bot"},
                    "content": kwargs["data"]["content"],
                }
            )
            return {"code": 0, "subcode": 0, "data": {"id": reply_id}}

        self.service._request = AsyncMock(side_effect=request)

    async def test_multi_author_capture_keeps_unanswered_photo_owner(self):
        await self.detail(multi_author_capture())
        root, friend, other, bot = self.post.comments
        self.assertEqual(friend.reply_to_uin, 10001)
        self.assertEqual(friend.reply_to_tid_source, "photo_mention")
        self.assertEqual(bot.reply_to_tid, other.tid)
        self.assertEqual(bot.reply_to_uin, 30003)
        self.assertEqual([item.comment.tid for item in self.candidates()], [friend.tid])
        self.assertEqual(friend.parent_tid, root.tid)

    async def test_unanswered_people_in_one_photo_thread_are_independent_candidates(
        self,
    ):
        await self.detail(multi_author_capture(answered=False))
        candidates = self.candidates()
        self.assertEqual(
            [(item.comment.raw_tid, item.comment.uin) for item in candidates],
            [("1790997908", 30003), ("1790997849", 20002)],
        )
        self.assertEqual(len({item.item_key for item in candidates}), 2)

    async def test_captured_owner_reply_submits_correct_mention_and_never_repeats(self):
        payload = multi_author_capture()
        self.mock_thread_submissions(payload)
        result = await self.run_task()
        self.assertEqual((result["commented"], result["failed"]), (1, 0))
        self.assertEqual(
            self.manager.generated_for, [("41", "41_r_1790997849_20002", 20002)]
        )
        writes = [
            call
            for call in self.service._request.call_args_list
            if call.args[0] == "POST"
        ]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0].kwargs["data"]["topicId"], "album-1_pic-1!!_0_0")
        self.assertEqual(writes[0].kwargs["data"]["commentId"], "41")
        self.assertEqual(writes[0].kwargs["data"]["commentUin"], 10001)
        self.assertEqual(
            writes[0].kwargs["data"]["content"],
            "@{uin:20002,nick:Friend,auto:1} Thanks!",
        )
        state = self.manager.db.state[self.task_module.QZONE_AUTO_COMMENT_STATE_KEY][
            "processed"
        ]
        entry = state["20002:photo:album-1:pic-1!!:41_r_1790997849_20002"]
        self.assertEqual(entry["verification_status"], "confirmed")
        self.assertEqual(entry["verified_reply_to_uin"], 20002)
        self.manager.db = FakeDb()
        self.assertEqual((await self.run_task())["commented"], 0)
        self.assertEqual(len(self.manager.generated_for), 1)
        self.assertEqual(
            sum(
                call.args[0] == "POST" for call in self.service._request.call_args_list
            ),
            1,
        )

    async def test_limit_one_replies_to_people_across_runs_without_losing_older_turn(
        self,
    ):
        payload = multi_author_capture(answered=False)
        self.mock_thread_submissions(payload)
        self.assertEqual((await self.run_task())["commented"], 1)
        self.assertEqual(self.manager.generated_for[0][2], 30003)
        self.assertEqual((await self.run_task())["commented"], 1)
        self.assertEqual(self.manager.generated_for[1][2], 20002)
        self.assertEqual((await self.run_task())["commented"], 0)
        writes = [
            call
            for call in self.service._request.call_args_list
            if call.args[0] == "POST"
        ]
        self.assertEqual(len(writes), 2)
        self.assertEqual(
            [call.kwargs["data"]["content"] for call in writes],
            [
                "@{uin:30003,nick:Other,auto:1} Thanks!",
                "@{uin:20002,nick:Friend,auto:1} Thanks!",
            ],
        )

    async def test_same_author_to_bot_coalesces_only_latest_turn(self):
        payload = multi_author_capture(answered=False)
        payload["data"]["single"]["comments"][0]["replies"][1]["poster"] = {
            "id": 20002,
            "name": "Friend",
        }
        await self.detail(payload)
        self.assertEqual(
            [item.comment.raw_tid for item in self.candidates()], ["1790997908"]
        )

    async def test_same_author_in_different_root_threads_keeps_both_candidates(self):
        payload = multi_author_capture(answered=False)
        root = payload["data"]["single"]["comments"][0]
        root["replies"] = root["replies"][:1]
        other_root = copy.deepcopy(root)
        other_root["id"] = 42
        other_root["replies"][0].update(id=1790997908, postTime=1790997908)
        payload["data"]["single"]["comments"].append(other_root)
        await self.detail(payload)
        self.assertEqual(
            [(item.parent_comment.tid, item.comment.uin) for item in self.candidates()],
            [("42", 20002), ("41", 20002)],
        )

    async def test_same_author_latest_turn_submits_once_not_once_per_message(self):
        payload = multi_author_capture(answered=False)
        payload["data"]["single"]["comments"][0]["replies"][1]["poster"] = {
            "id": 20002,
            "name": "Friend",
        }
        self.mock_thread_submissions(payload)
        self.assertEqual((await self.run_task())["commented"], 1)
        self.assertEqual(
            self.manager.generated_for, [("41", "41_r_1790997908_20002", 20002)]
        )
        self.manager.db = FakeDb()
        self.assertEqual((await self.run_task())["commented"], 0)
        self.assertEqual(
            sum(
                call.args[0] == "POST" for call in self.service._request.call_args_list
            ),
            1,
        )

    async def test_own_photo_multi_author_reply_does_not_lose_unanswered_person(self):
        payload = multi_author_capture()
        root = payload["data"]["single"]["comments"][0]
        root["poster"] = {"id": 40004, "name": "Root author"}
        root["replies"].insert(
            0,
            {
                "id": 1790997800,
                "postTime": 1790997800,
                "poster": {"id": 10001, "name": "Bot"},
                "content": "@{uin:40004,nick:Root author,auto:1} Thanks!",
            },
        )
        payload["data"]["photos"][0]["ownerUin"] = 10001
        payload["data"]["topic"]["ownerUin"] = 10001
        self.post.uin = 10001
        self.post.photo_targets[0].owner_uin = 10001
        self.service._remember_posts([self.post])
        self.manager.qzone_conf.update(
            qzone_enable_auto_reply=True, qzone_auto_reply_limit=1
        )
        self.service.query_posts = AsyncMock(return_value=[])
        self.mock_thread_submissions(payload)
        with patch("asyncio.sleep", new=AsyncMock()):
            result = await self.manager.execute_qzone_auto_reply()
        self.assertEqual((result["replied"], result["failed"]), (1, 0))
        self.assertEqual(
            self.manager.generated_for, [("41", "41_r_1790997849_20002", 20002)]
        )
        writes = [
            call
            for call in self.service._request.call_args_list
            if call.args[0] == "POST"
        ]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0].kwargs["data"]["commentId"], "41")
        self.assertEqual(writes[0].kwargs["data"]["commentUin"], 40004)
        self.assertEqual(
            writes[0].kwargs["data"]["content"],
            "@{uin:20002,nick:Friend,auto:1} Thanks!",
        )
        state = self.manager.db.state[self.task_module.QZONE_AUTO_REPLY_STATE_KEY][
            "processed"
        ]
        entry = state["10001:photo:album-1:pic-1!!:41_r_1790997849_20002"]
        self.assertEqual(entry["verification_status"], "confirmed")
        self.assertEqual(entry["verified_reply_to_uin"], 20002)
        self.manager.db = FakeDb()
        with patch("asyncio.sleep", new=AsyncMock()):
            result = await self.manager.execute_qzone_auto_reply()
        self.assertEqual(result["replied"], 0)
        self.assertEqual(
            sum(
                call.args[0] == "POST" for call in self.service._request.call_args_list
            ),
            1,
        )

    async def test_same_author_reply_to_someone_else_does_not_supersede_bot_turn(self):
        payload = multi_author_capture(answered=False)
        root = payload["data"]["single"]["comments"][0]
        root["poster"] = {"id": 30003, "name": "Other"}
        root["replies"].insert(
            0,
            {
                "id": 1790997800,
                "postTime": 1790997800,
                "poster": {"id": 10001, "name": "Bot"},
                "content": "@{uin:30003,nick:Other,auto:1} Nice!",
            },
        )
        root["replies"][-1].update(
            poster={"id": 20002, "name": "Friend"},
            content="@{uin:30003,nick:Other,auto:1} Hi!",
        )
        self.post.uin = 10001
        self.post.photo_targets[0].owner_uin = 10001
        payload["data"]["photos"][0]["ownerUin"] = 10001
        payload["data"]["topic"]["ownerUin"] = 10001
        self.service._remember_posts([self.post])
        await self.detail(payload)
        candidate = sys.modules[f"{self.task_module.__package__}.interact.candidate"]
        candidates = candidate._qzone_self_reply_candidates(
            self.manager,
            [self.post],
            self_uin=10001,
            processed={},
            result={"scanned": 0, "skipped": 0},
        )
        self.assertEqual([item.comment.raw_tid for item in candidates], ["1790997849"])

    async def test_private_or_invalid_later_turn_cannot_hide_valid_public_bot_reply(
        self,
    ):
        for change in (
            {"private": 1},
            {"postTime": 0},
            {"topicId": "other-photo"},
            {"id": 0},
            {
                "content": "@{uin:10001,nick:Bot,auto:1} @{uin:30003,nick:Other,auto:1} Hi"
            },
        ):
            with self.subTest(change=change):
                self.post.comments = []
                payload = multi_author_capture(answered=False)
                later = payload["data"]["single"]["comments"][0]["replies"][1]
                later["poster"] = {"id": 20002, "name": "Friend"}
                later.update(change)
                await self.detail(payload)
                self.assertEqual(
                    [item.comment.raw_tid for item in self.candidates()], ["1790997849"]
                )

    async def test_reversed_and_duplicate_multi_author_rows_keep_unanswered_identity(
        self,
    ):
        payload = multi_author_capture()
        replies = payload["data"]["single"]["comments"][0]["replies"]
        replies[:] = [replies[2], replies[1], replies[0], replies[0]]
        await self.detail(payload)
        self.assertEqual(len(self.post.comments), 4)
        self.assertEqual(
            [item.comment.raw_tid for item in self.candidates()], ["1790997849"]
        )

    async def test_viewer_parses_root_and_children_without_changing_root_count(self):
        await self.detail(viewer_capture())
        self.assertEqual(self.post.photo_targets[0].comment_total, 1)
        self.assertEqual(len(self.post.photo_targets[0].comments), 1)
        root, friend, bot = self.post.comments
        self.assertEqual(root.tid, "41")
        self.assertEqual(friend.tid, "41_r_1790957204_20002")
        self.assertEqual(friend.raw_tid, "1790957204")
        self.assertEqual(friend.parent_tid, "41")
        self.assertEqual(friend.reply_to_tid, root.tid)
        self.assertEqual(bot.reply_to_tid, friend.tid)
        self.assertEqual(bot.reply_to_uin, 20002)
        self.assertEqual(friend.raw_fields["photo_root_uin"], 10001)
        self.assertEqual(friend.raw_fields["photo_topic_id"], "album-1_pic-1!!_0_0")

    async def test_capture_already_answered_skips_generation_and_network_write(self):
        self.service._request = AsyncMock(return_value=viewer_capture())
        result = await self.run_task()
        self.assertEqual(result["commented"], 0)
        self.assertEqual(self.manager.generated_for, [])
        self.assertTrue(
            all(call.args[0] == "GET" for call in self.service._request.call_args_list)
        )

    async def test_unanswered_friend_reply_submits_root_identity_mentions_child_and_runs_once(
        self,
    ):
        payload = viewer_capture(answered=False)

        async def request(method, url, **kwargs):
            if method == "GET":
                return copy.deepcopy(payload)
            payload["data"]["single"]["comments"][0]["replies"].append(
                {
                    "id": 1790958140,
                    "postTime": 1790958140,
                    "poster": {"id": 10001, "name": "Bot"},
                    "content": kwargs["data"]["content"],
                }
            )
            return {"code": 0, "subcode": 0, "data": {"id": 1790958140}}

        self.service._request = AsyncMock(side_effect=request)
        result = await self.run_task()
        self.assertEqual(result["commented"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(
            self.manager.generated_for, [("41", "41_r_1790957204_20002", 20002)]
        )
        writes = [
            call
            for call in self.service._request.call_args_list
            if call.args[0] == "POST"
        ]
        self.assertEqual(len(writes), 1)
        call = writes[0]
        self.assertEqual(call.args[1], self.service.PHOTO_REPLY_URL)
        data = call.kwargs["data"]
        self.assertEqual(
            (data["uin"], data["hostUin"], data["commentId"], data["commentUin"]),
            (10001, 20002, "41", 10001),
        )
        self.assertEqual(data["content"], "@{uin:20002,nick:Friend,auto:1} Thanks!")
        self.assertEqual(data["ref"], "photo")
        self.assertNotIn("feedsType", data)
        entry = self.manager.db.state[self.task_module.QZONE_AUTO_COMMENT_STATE_KEY][
            "processed"
        ]["20002:photo:album-1:pic-1!!:41_r_1790957204_20002"]
        self.assertEqual(entry["action"], "thread_commented")
        self.assertEqual(entry["verification_status"], "confirmed")
        self.assertEqual(entry["submitted_comment_uin"], 10001)
        self.assertEqual(entry["verified_reply_to_uin"], 20002)
        self.assertEqual(entry["submitted_reply_id"], "1790958140")
        # 模拟重启后的空本地状态，仍可从查看器数据中识别机器人已有回复。
        self.manager.db = FakeDb()
        self.post.tid = "changed-feed-key"
        self.service._remember_posts([self.post])
        result = await self.run_task()
        self.assertEqual(result["commented"], 0)
        self.assertEqual(len(self.manager.generated_for), 1)
        self.assertEqual(
            sum(
                call.args[0] == "POST" for call in self.service._request.call_args_list
            ),
            1,
        )

    async def test_wrong_mentions_private_missing_time_or_foreign_topic_have_no_candidates(
        self,
    ):
        for change in (
            {"content": "No explicit recipient"},
            {"content": "@{uin:30003,nick:Third,auto:1} Hi"},
            {
                "content": "@{uin:10001,nick:Bot,auto:1} @{uin:30003,nick:Third,auto:1} Hi"
            },
            {"private": 1},
            {"private": "invalid"},
            {"topicId": "other-photo"},
            {"postTime": 0},
        ):
            with self.subTest(change=change):
                self.post.comments = []
                payload = viewer_capture(answered=False)
                payload["data"]["single"]["comments"][0]["replies"][0].update(change)
                await self.detail(payload)
                self.assertEqual(self.candidates(), [])

    async def test_reversed_viewer_order_and_duplicate_rows_keep_stable_keys(self):
        payload = viewer_capture()
        replies = payload["data"]["single"]["comments"][0]["replies"]
        replies[:] = [replies[1], replies[0], replies[0]]
        await self.detail(payload)
        self.assertEqual(len(self.post.comments), 3)
        self.assertEqual(self.candidates(), [])

    async def test_changed_html_identity_is_replaced_by_authoritative_viewer_binding(
        self,
    ):
        self.post.comments = [
            self.module.QzoneComment(
                tid="html-child",
                raw_tid="1790957204",
                submit_tid="1790957204",
                uin=20002,
                parent_tid="41",
                reply_to_tid="html-wrong-target",
            )
        ]
        await self.detail(viewer_capture(answered=False))
        self.assertEqual(len(self.candidates()), 1)
        self.assertEqual(self.candidates()[0].comment.tid, "41_r_1790957204_20002")

    async def test_photo_aliases_do_not_generate_duplicate_candidates(self):
        await self.detail(viewer_capture(answered=False))
        other = self.module.QzonePost(
            uin=20002,
            tid="other-feed",
            appid=4,
            photo_targets=self.post.photo_targets,
            comments=self.post.comments,
        )
        self.assertEqual(len(self.candidates([self.post, other])), 1)

    async def test_new_friend_reply_after_previous_bot_answer_continues_same_root(self):
        payload = viewer_capture()
        payload["data"]["single"]["comments"][0]["replies"].append(
            {
                "id": 1790959000,
                "postTime": 1790959000,
                "poster": {"id": 20002, "name": "Friend"},
                "content": "@{uin:10001,nick:Bot,auto:1} See you!",
            }
        )

        async def request(method, url, **kwargs):
            if method == "GET":
                return copy.deepcopy(payload)
            payload["data"]["single"]["comments"][0]["replies"].append(
                {
                    "id": 1790960000,
                    "postTime": 1790960000,
                    "poster": {"id": 10001, "name": "Bot"},
                    "content": kwargs["data"]["content"],
                }
            )
            return {"code": 0, "data": {"id": 1790960000}}

        self.service._request = AsyncMock(side_effect=request)
        result = await self.run_task()
        self.assertEqual(result["commented"], 1)
        self.assertEqual(
            self.manager.generated_for, [("41", "41_r_1790959000_20002", 20002)]
        )
        writes = [
            call
            for call in self.service._request.call_args_list
            if call.args[0] == "POST"
        ]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0].kwargs["data"]["commentId"], "41")
        self.assertEqual(writes[0].kwargs["data"]["commentUin"], 10001)
        self.assertEqual(
            writes[0].kwargs["data"]["content"],
            "@{uin:20002,nick:Friend,auto:1} Thanks!",
        )

    async def test_own_photo_accepts_new_reply_in_thread_with_prior_bot_participation(
        self,
    ):
        payload = viewer_capture()
        payload["data"]["photos"][0]["ownerUin"] = 10001
        payload["data"]["topic"]["ownerUin"] = 10001
        raw = payload["data"]["single"]["comments"][0]
        raw["poster"] = {"id": 30003, "name": "Tester"}
        raw["replies"][0].update(
            poster={"id": 10001, "name": "Bot"},
            content="@{uin:30003,nick:Tester,auto:1} Thanks!",
        )
        raw["replies"][1].update(
            poster={"id": 30003, "name": "Tester"},
            content="@{uin:10001,nick:Bot,auto:1} Welcome!",
        )
        self.post.uin = 10001
        self.post.photo_targets[0].owner_uin = 10001
        self.service._remember_posts([self.post])
        await self.detail(payload)
        candidate = sys.modules[f"{self.task_module.__package__}.interact.candidate"]
        candidates = candidate._qzone_self_reply_candidates(
            self.manager,
            [self.post],
            self_uin=10001,
            processed={},
            result={"scanned": 0, "skipped": 0},
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].comment.tid, "41_r_1790958140_30003")
        self.assertEqual(candidates[0].parent_comment.uin, 30003)

    async def test_later_bot_reply_with_ambiguous_recipient_suppresses_old_candidate(
        self,
    ):
        payload = viewer_capture()
        payload["data"]["single"]["comments"][0]["replies"][1]["content"] = (
            "Already answered"
        )
        await self.detail(payload)
        self.assertEqual(self.candidates(), [])

    async def test_unknown_submit_is_saved_without_readback_or_repeated_post(self):
        async def request(method, url, **kwargs):
            if method == "GET":
                return viewer_capture(answered=False)
            raise RuntimeError("timeout")

        self.service._request = AsyncMock(side_effect=request)
        result = await self.run_task()
        self.assertEqual(result["commented"], 0)
        entry = self.manager.db.state[self.task_module.QZONE_AUTO_COMMENT_STATE_KEY][
            "processed"
        ]["20002:photo:album-1:pic-1!!:41_r_1790957204_20002"]
        self.assertTrue(entry["submission_unknown"])
        await self.run_task()
        self.assertEqual(
            sum(
                call.args[0] == "POST" for call in self.service._request.call_args_list
            ),
            1,
        )

    async def test_wrong_target_or_unavailable_readback_never_reposts_or_deletes(self):
        for failure in ("wrong_target", "detail_failed"):
            with self.subTest(failure=failure):
                self.manager.db = FakeDb()
                self.post.comments = []
                self.service._post_detail_cache_at.clear()
                submitted = False
                payload = viewer_capture(answered=False)

                async def request(method, url, **kwargs):
                    nonlocal submitted
                    if method == "POST":
                        submitted = True
                        payload["data"]["single"]["comments"][0]["replies"].append(
                            {
                                "id": 1790958140,
                                "postTime": 1790958140,
                                "poster": {"id": 10001, "name": "Bot"},
                                "content": "@{uin:30003,nick:Wrong,auto:1} Thanks!",
                            }
                        )
                        return {"code": 0, "data": {"id": 1790958140}}
                    if submitted and failure == "detail_failed":
                        raise RuntimeError("viewer unavailable")
                    return copy.deepcopy(payload)

                self.service._request = AsyncMock(side_effect=request)
                result = await self.run_task()
                self.assertEqual(result["commented"], 0)
                entry = self.manager.db.state[
                    self.task_module.QZONE_AUTO_COMMENT_STATE_KEY
                ]["processed"]["20002:photo:album-1:pic-1!!:41_r_1790957204_20002"]
                self.assertEqual(entry["verification_status"], failure)
                self.assertIn("reply_id=1790958140", entry["reason"])
                await self.run_task()
                writes = [
                    call
                    for call in self.service._request.call_args_list
                    if call.args[0] == "POST"
                ]
                self.assertEqual(len(writes), 1)
                self.assertEqual(writes[0].args[1], self.service.PHOTO_REPLY_URL)

    async def test_bad_root_binding_or_outgoing_mention_rejected_before_write(self):
        await self.detail(viewer_capture(answered=False))
        root, child = self.post.comments
        self.service._request.reset_mock()
        with self.assertRaisesRegex(RuntimeError, "正文 @"):
            await self.service.reply_comment(
                self.post.key,
                child,
                "@{uin:30003,nick:Wrong,auto:1} Hi",
                parent_comment=root,
            )
        child.raw_fields["photo_root_uin"] = 30003
        with self.assertRaisesRegex(RuntimeError, "不能猜测"):
            await self.service.reply_comment(
                self.post.key, child, "Hi", parent_comment=root
            )
        self.service._request.assert_not_awaited()

    async def test_unconfirmed_write_is_not_counted_or_automatically_resubmitted(self):
        payload = viewer_capture(answered=False)

        async def request(method, url, **kwargs):
            return (
                payload if method == "GET" else {"code": 0, "data": {"id": 1790958140}}
            )

        self.service._request = AsyncMock(side_effect=request)
        result = await self.run_task()
        self.assertEqual(result["commented"], 0)
        self.assertGreaterEqual(result["skipped"], 1)
        entry = self.manager.db.state[self.task_module.QZONE_AUTO_COMMENT_STATE_KEY][
            "processed"
        ]["20002:photo:album-1:pic-1!!:41_r_1790957204_20002"]
        self.assertEqual(entry["verification_status"], "not_found")
        await self.run_task()
        self.assertEqual(
            sum(
                call.args[0] == "POST" for call in self.service._request.call_args_list
            ),
            1,
        )

    async def test_nested_submit_uses_real_html_decoder_and_viewer_readback(self):
        await self.detail(viewer_capture(answered=False))
        root, child = self.post.comments
        html = '<script>frameElement.callback({"code":0,"subcode":0,"data":{"id":1790958140}});</script>'
        viewer_text = (
            Path(__file__).parent / "fixtures/qzone_album_thread_viewer.jsonp"
        ).read_text()
        session = PhotoResponseSession(html, viewer_text)
        del self.service._request
        self.service._http = AsyncMock(return_value=session)
        result = await self.service.reply_comment(
            self.post.key, child, "Thanks!", parent_comment=root
        )
        self.assertEqual(result["verification_status"], "confirmed")
        self.assertEqual([call["method"] for call in session.calls], ["POST", "GET"])
        self.assertEqual(session.calls[0]["data"]["commentUin"], 10001)
        self.assertEqual(session.calls[1]["params"]["uin"], 10001)
        self.assertEqual(session.calls[1]["params"]["hostUin"], 20002)

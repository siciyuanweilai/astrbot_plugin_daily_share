"""局部评论编号下的第三方续评：提交楼层、对象与落点核验。"""

import unittest
from dataclasses import replace
from unittest.mock import AsyncMock

from .testqzone import _load_qzone_service, _new_qzone_service


class ThirdPartyThreadTargetTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.module = _load_qzone_service()
        self.service = _new_qzone_service(self.module)
        self.ctx = self.module.QzoneContext(10001, "skey", "p_skey")
        self.parent = self.module.QzoneComment(
            uin=20002, tid="2", submit_tid="2", raw_tid="2", content="原评论"
        )
        self.bot_reply = self.module.QzoneComment(
            uin=10001,
            tid="2_r_1_10001",
            submit_tid="1",
            raw_tid="1",
            parent_tid="2",
            reply_to_tid="2",
            reply_to_uin=20002,
            content="已参与这层讨论",
        )
        self.followup = self.module.QzoneComment(
            uin=20002,
            nickname="评论人",
            tid="2_r_2_20002",
            submit_tid="2",
            raw_tid="2",
            parent_tid="2",
            reply_to_tid="2_r_1_10001",
            reply_to_uin=10001,
            content="@{uin:10001,nick:Bot,auto:1} 下次一起？",
        )
        self.post = self.module.QzonePost(
            uin=30003,
            tid="friend-post",
            comments=[self.parent, self.bot_reply, self.followup],
        )

    async def test_third_party_short_id_submit_and_verification(self):
        for target_uin in (20002, 40004):
            with self.subTest(target_uin=target_uin):
                target = replace(
                    self.followup, uin=target_uin, tid=f"2_r_2_{target_uin}"
                )
                post = replace(
                    self.post, comments=[self.parent, self.bot_reply, target]
                )
                self.service._post_cache[post.key] = post
                confirmed = self.module.QzoneComment(
                    uin=10001,
                    tid="2_r_3_10001",
                    submit_tid="3",
                    raw_tid="3",
                    parent_tid="2",
                    reply_to_tid="2",
                    reply_to_uin=target_uin,
                    content=f"@{{uin:{target_uin},nick:评论人,auto:1}} 好呀",
                    create_time=2000000000,
                )
                self.service.context = AsyncMock(return_value=self.ctx)
                self.service._request = AsyncMock(return_value={"code": 0})
                self.service.detail = AsyncMock(
                    return_value=replace(post, comments=[*post.comments, confirmed])
                )

                self.assertTrue(
                    self.service.has_thread_reply_submit_plan(
                        post, target, parent_comment=self.parent, self_uin=self.ctx.uin
                    )
                )
                result = await self.service.reply_comment(
                    post.key, target, "好呀", parent_comment=self.parent
                )

                self.assertEqual(result["transport"], "addreply_ugc")
                self.assertEqual(result["verification_status"], "confirmed")
                self.assertEqual(result["verified_reply_to_uin"], target_uin)
                self.service._request.assert_awaited_once()
                request = self.service._request.call_args
                self.assertEqual(request.args[1], self.service.ADD_REPLY_UGC_URL)
                data = request.kwargs["data"]
                self.assertEqual(data["topicId"], "30003_friend-post")
                self.assertEqual(data["commentId"], "2")
                self.assertEqual(data["commentUin"], target_uin)
                self.assertEqual(data["content"], confirmed.content)
                self.assertNotIn("_r_", str(data))
                self.service.detail.assert_awaited_once_with(post.key)

    async def test_unresolved_thread_targets_do_not_submit(self):
        cases = (
            ("no_prior_participation", [], self.followup),
            (
                "bot_in_another_floor",
                [replace(self.bot_reply, parent_tid="7")],
                self.followup,
            ),
            (
                "unknown_reply_reference",
                [self.bot_reply],
                replace(self.followup, reply_to_tid="unknown-reference"),
            ),
            (
                "recipient_mismatch",
                [self.bot_reply],
                replace(self.followup, reply_to_uin=40004),
            ),
        )
        for label, prior, target in cases:
            with self.subTest(label=label):
                post = replace(self.post, comments=[self.parent, *prior, target])
                self.service._post_cache[post.key] = post
                self.service.context = AsyncMock(return_value=self.ctx)
                self.service._request = AsyncMock()
                self.assertFalse(
                    self.service.has_thread_reply_submit_plan(
                        post, target, parent_comment=self.parent, self_uin=self.ctx.uin
                    )
                )
                with self.assertRaises(RuntimeError):
                    await self.service.reply_comment(
                        post.key, target, "好呀", parent_comment=self.parent
                    )
                self.service._request.assert_not_awaited()

    async def test_h5_preflight_matches_actual_submit_for_bot_parent(self):
        parent = replace(self.parent, uin=10001)
        target = replace(self.followup, reply_to_tid="unavailable-previous-reply")
        post = replace(self.post, comments=[parent, target])
        self.service._post_cache[post.key] = post
        self.service._ctx = self.ctx
        self.service.context = AsyncMock(return_value=self.ctx)
        self.service._request = AsyncMock(return_value={"code": 0})
        self.service._verify_thread_reply_submission = AsyncMock(
            return_value={"status": "confirmed"}
        )

        for identity in ({}, {"self_uin": self.ctx.uin}):
            self.assertTrue(
                self.service.has_thread_reply_submit_plan(
                    post, target, parent_comment=parent, **identity
                )
            )
        result = await self.service.reply_comment(
            post.key, target, "好呀", parent_comment=parent
        )

        self.assertEqual(result["transport"], "h5_re_feeds_parent")
        self.service._request.assert_awaited_once()
        request = self.service._request.call_args
        self.assertEqual(request.args[1], self.service.H5_COMMENT_URL)
        self.assertEqual(request.kwargs["data"]["commentId"], parent.tid)
        self.assertEqual(request.kwargs["data"]["commentUin"], self.ctx.uin)
        self.service._verify_thread_reply_submission.assert_awaited_once()

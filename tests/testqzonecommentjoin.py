"""好友说说/相册中的第三方评论回评：概率、落点、防重和重试。"""

import importlib
import time
import types
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, patch

from .testqzonecomment import _interaction_args, _load_auto_comment_module


class FriendCommentReplyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.module, self.models = _load_auto_comment_module()
        self.discuss = importlib.import_module(
            f"{self.module.__package__}.interact.executors.discuss"
        )
        self.comment = self.models.QzoneComment(
            uin=4, nickname="访客", tid="42", content="这家书店在哪？"
        )
        self.post = self.models.QzonePost(
            uin=3, tid="new", name="朋友", text="今天去了书店", comments=[self.comment]
        )
        self.service = types.SimpleNamespace(
            context=AsyncMock(return_value=types.SimpleNamespace(uin=1)),
            query_mention_posts=AsyncMock(return_value=[]),
            query_recent_posts=AsyncMock(return_value=[self.post]),
            comment=AsyncMock(),
            reply_comment=AsyncMock(
                return_value={"comment_id": "42", "comment_uin": 4}
            ),
        )
        self.manager = self.module.TaskQzoneAutoCommentService(
            *_interaction_args(self.module)
        )
        self.manager.config.qzone = {
            "enable_qzone": True,
            "qzone_enable_auto_comment": True,
            "qzone_auto_comment_limit": 1,
            "qzone_auto_comment_reply_probability": 100,
        }
        self.manager.runtime = replace(
            self.manager.runtime,
            plugin=types.SimpleNamespace(
                _is_terminated=False,
                qzone_service=self.service,
                call_llm=AsyncMock(return_value="我也想去看看"),
                emit_dashboard_event=lambda *args: None,
            ),
        )
        self.manager.generate_qzone_auto_comment = AsyncMock(return_value="听起来不错")
        self.manager._generate_qzone_auto_reply = AsyncMock(return_value="我也想去看看")
        self.sleep_patch = patch.object(self.module.asyncio, "sleep", new=AsyncMock())
        self.sleep_patch.start()
        self.addCleanup(self.sleep_patch.stop)

    @property
    def processed(self):
        return self.manager.db.state[self.module.QZONE_AUTO_COMMENT_STATE_KEY][
            "processed"
        ]

    async def run_task(self):
        return await self.manager.execute_qzone_auto_comment()

    async def test_direct_reply_after_own_comment_and_dedup_on_next_scan(self):
        self.post.comments.insert(
            0, self.models.QzoneComment(uin=1, tid="bot", content="下次也想去")
        )
        self.manager.db.state[self.module.QZONE_AUTO_COMMENT_STATE_KEY] = {
            "processed": {
                self.post.key: {"at": int(time.time()), "action": "commented"}
            }
        }
        first = await self.run_task()
        self.post.comments.append(
            self.models.QzoneComment(uin=5, tid="43", content="看着好棒")
        )
        second = await self.run_task()
        self.assertEqual((first["commented"], second["commented"]), (1, 0))
        self.service.comment.assert_not_awaited()
        self.service.reply_comment.assert_awaited_once_with(
            self.post.key, self.comment, "我也想去看看", parent_comment=None
        )
        self.assertEqual(self.processed[self.post.key]["action"], "comment_replied")
        self.assertEqual(self.processed["3:new:42"]["action"], "comment_replied")
        self.assertFalse(
            self.manager._generate_qzone_auto_reply.call_args.kwargs["as_post_owner"]
        )
        self.assertEqual(
            self.manager._generate_qzone_auto_reply.call_args.kwargs["self_uin"], 1
        )

    async def test_real_feed_reply_buttons_do_not_hide_other_users_root_comments(self):
        parser = importlib.import_module(f"{self.models.__package__}.parser")
        # 好友动态 HTML 的回复按钮指向当前评论，不表示当前评论正在回复自己。
        html = """
        <li class="comments-item" data-type="commentroot" data-tid="1"
            data-uin="89761500" data-nick="四次元未来">
          <div class="comments-content">没啥好吃的，建议别吃了，还能省钱</div>
          <a class="reply" data-param="t2_uin=89761500&amp;t2_tid=1">回复</a>
        </li>
        <li class="comments-item" data-type="commentroot" data-tid="2"
            data-uin="188852752" data-nick="李知恬">
          <div class="comments-content">路口那家转角肠粉好像还没收摊 要不去看一眼</div>
          <a class="reply" data-param="t2_uin=188852752&amp;t2_tid=2">回复</a>
          <div class="mod-comments-sub">
            <li class="comments-item" data-type="replyroot" data-tid="1"
                data-uin="89761500" data-nick="四次元未来">
              <div class="comments-content">你请我吃的话，我就去看下</div>
              <a class="reply" data-param="t2_uin=188852752&amp;t2_tid=2">回复</a>
            </li>
            <li class="comments-item" data-type="replyroot" data-tid="2"
                data-uin="188852752" data-nick="李知恬">
              <div class="comments-content">想得倒美 肠粉没有 白开水管够</div>
              <a class="reply" data-param="t2_uin=89761500&amp;t2_tid=1">回复</a>
            </li>
          </div>
        </li>
        """
        self.post = parser.parse_feed_item(
            {
                "uin": 897537513,
                "tid": "e9557f35912fd76a28380700",
                "content": "今晚吃啥好呢？大家有推荐吗？",
                "html": html,
            }
        )
        self.service.context.return_value.uin = 188852752
        self.service.query_recent_posts.return_value = [self.post]
        self.manager.db.state[self.module.QZONE_AUTO_COMMENT_STATE_KEY] = {
            "processed": {
                self.post.key: {"at": int(time.time()), "action": "commented"},
                f"{self.post.key}:2_r_1_89761500": {
                    "at": int(time.time()),
                    "action": "skipped",
                },
            }
        }
        root = self.post.comments[0]
        self.assertEqual(
            (root.parent_tid, root.reply_to_tid, root.reply_to_uin), ("", "", 0)
        )
        result = await self.run_task()
        self.assertEqual(result["commented"], 1)
        self.service.comment.assert_not_awaited()
        self.service.reply_comment.assert_awaited_once_with(
            self.post.key, root, "我也想去看看", parent_comment=None
        )
        self.assertEqual(
            self.processed[f"{self.post.key}:1"]["action"], "comment_replied"
        )

    async def test_probability_zero_and_miss_keep_main_comment(self):
        for probability, roll in ((0, 0), (30, 0.30)):
            with self.subTest(probability=probability):
                self.manager.db.state.clear()
                self.service.comment.reset_mock()
                self.manager.config.qzone["qzone_auto_comment_reply_probability"] = (
                    probability
                )
                with patch.object(self.discuss.random, "random", return_value=roll):
                    result = await self.run_task()
                self.assertEqual(result["commented"], 1)
                self.service.comment.assert_awaited_once_with(
                    self.post.key, "听起来不错"
                )
        self.service.reply_comment.assert_not_awaited()
        self.manager._generate_qzone_auto_reply.assert_not_awaited()

    async def test_probability_hit_uses_one_reply_within_comment_limit(self):
        self.manager.config.qzone["qzone_auto_comment_reply_probability"] = 30
        self.service.query_recent_posts.return_value.append(
            replace(self.post, tid="another")
        )
        with patch.object(self.discuss.random, "random", return_value=0.29):
            result = await self.run_task()
        self.assertEqual(result["commented"], 1)
        self.service.reply_comment.assert_awaited_once()
        self.service.comment.assert_not_awaited()

    async def test_rate_limit_reuses_cached_reply_and_target_without_reroll(self):
        self.service.reply_comment.side_effect = RuntimeError(
            "操作过于频繁，请稍后再试"
        )
        first = await self.run_task()
        self.assertEqual(first["commented"], 0)
        self.assertEqual(self.processed["3:new:42"]["action"], "retry_later")
        self.manager.config.qzone["qzone_auto_comment_reply_probability"] = 0
        self.post.comments.append(
            self.models.QzoneComment(
                uin=5, tid="43", content="更新的评论", create_time=1
            )
        )
        self.service.reply_comment.side_effect = None
        with patch.object(self.discuss.random, "random", side_effect=AssertionError):
            second = await self.run_task()
        self.assertEqual(second["commented"], 1)
        self.manager._generate_qzone_auto_reply.assert_awaited_once()
        self.assertEqual(self.service.reply_comment.await_count, 2)
        self.assertIs(self.service.reply_comment.call_args.args[1], self.comment)
        self.service.comment.assert_not_awaited()

    async def test_nested_self_missing_id_and_replied_comments_are_excluded(self):
        cases = [
            replace(self.comment, uin=1),
            replace(self.comment, tid=""),
            replace(self.comment, parent_tid="parent"),
            replace(self.comment, reply_to_tid="parent"),
            replace(self.comment, content=""),
        ]
        for comment in cases:
            with self.subTest(comment=comment):
                self.assertFalse(
                    self.manager._qzone_auto_comment_reply_candidate(
                        self.post, comment, self_uin=1, processed={}
                    )
                )
        self.comment.submit_tid = "alias"
        self.post.comments.append(
            self.models.QzoneComment(
                uin=1, tid="bot", parent_tid="alias", content="答过了"
            )
        )
        self.assertFalse(
            self.manager._qzone_auto_comment_reply_candidate(
                self.post, self.comment, self_uin=1, processed={}
            )
        )

    async def test_prompt_uses_friend_author_and_participant_role(self):
        self.manager._qzone_auto_life_context_prompt = AsyncMock(return_value="")
        await self.manager.dialogue._generate_qzone_auto_reply(
            self.post, self.comment, as_post_owner=False
        )
        kwargs = self.manager.plugin.call_llm.call_args.kwargs
        self.assertIn("朋友（QQ：3）的说说", kwargs["prompt"])
        self.assertIn("这家书店在哪", kwargs["prompt"])
        self.assertIn("以评论参与者的身份", kwargs["system_prompt"])
        self.assertNotIn("以空间主人的身份", kwargs["system_prompt"])
        self.assertNotIn("我的说说", kwargs["prompt"])

    async def test_joined_third_party_thread_continues_only_when_addressed_to_bot(self):
        await self.run_task()
        self.manager._generate_qzone_auto_reply_thread = AsyncMock(return_value="好呀")
        followup = self.models.QzoneComment(
            uin=4,
            tid="43",
            submit_tid="43",
            raw_tid="43",
            parent_tid="42",
            reply_to_uin=1,
            content="@{uin:1,nick:Bot,auto:1} 下次一起去？",
        )
        self.post.comments.append(followup)
        result = await self.run_task()
        self.assertEqual(result["commented"], 1)
        self.assertEqual(self.service.reply_comment.await_count, 2)
        self.service.reply_comment.assert_awaited_with(
            self.post.key, followup, "好呀", parent_comment=self.comment
        )
        second = await self.run_task()
        self.assertEqual(second["commented"], 0)
        unrelated = replace(followup, tid="44", reply_to_uin=5, content="和别人聊天")
        self.assertEqual(
            self.manager._qzone_friend_comment_thread_skip_reason(
                self.post, self.comment, unrelated, self_uin=1, processed=self.processed
            ),
            "reply_not_to_bot",
        )

    def test_third_party_thread_requires_previous_bot_participation(self):
        followup = self.models.QzoneComment(
            uin=4, tid="43", parent_tid="42", reply_to_uin=1, content="你好"
        )
        self.assertEqual(
            self.manager._qzone_friend_comment_thread_skip_reason(
                self.post, self.comment, followup, self_uin=1, processed={}
            ),
            "missing_self_thread_reply",
        )

    async def test_thread_rate_limit_stops_other_comment_submissions(self):
        await self.run_task()
        self.manager._generate_qzone_auto_reply_thread = AsyncMock(return_value="好呀")
        self.post.comments.append(
            self.models.QzoneComment(
                uin=4, tid="43", parent_tid="42", reply_to_uin=1, content="一起去？"
            )
        )
        self.service.query_recent_posts.return_value.append(
            replace(self.post, tid="another", comments=[self.comment])
        )
        self.service.reply_comment.reset_mock()
        self.manager._generate_qzone_auto_reply.reset_mock()
        self.service.reply_comment.side_effect = RuntimeError(
            "操作过于频繁，请稍后再试"
        )
        result = await self.run_task()
        self.assertTrue(result["rate_limited"])
        self.assertEqual(result["commented"], 0)
        self.service.reply_comment.assert_awaited_once()
        self.manager._generate_qzone_auto_reply.assert_not_awaited()
        self.service.comment.assert_not_awaited()

    def album_posts(self):
        return [
            replace(
                self.post,
                tid=f"photo-{number}",
                appid=4,
                photo_targets=[
                    self.models.QzonePhoto(
                        owner_uin=3, album_id="album", pic_key=f"pic{number}"
                    )
                ],
                photo_batch_key="3:photo-batch:album:batch",
                comments=[] if number == 1 else [self.comment],
            )
            for number in (1, 2)
        ]

    async def test_album_second_photo_comment_uses_real_photo_reply_transport(self):
        from .testqzone import _load_qzone_service, _new_qzone_service

        posts = self.album_posts()
        module = _load_qzone_service()
        service = _new_qzone_service(module)
        service.context = AsyncMock(
            return_value=module.QzoneContext(uin=1, skey="dummy", p_skey="dummy")
        )
        service.query_recent_posts = AsyncMock(return_value=posts)
        service.query_mention_posts = AsyncMock(return_value=[])
        service._request = AsyncMock(return_value={"code": 0, "data": {"id": 43}})
        service._remember_posts(posts)
        self.manager.plugin.qzone_service = service
        processed = {}
        self.module._mark_qzone_post_processed(processed, posts[0], "commented")
        self.manager.db.state[self.module.QZONE_AUTO_COMMENT_STATE_KEY] = {
            "processed": processed
        }
        first = await self.run_task()
        posts[0].comments.append(replace(self.comment, tid="44", uin=5))
        second = await self.run_task()
        self.assertEqual((first["commented"], second["commented"]), (1, 0))
        service._request.assert_awaited_once()
        request = service._request.call_args
        self.assertEqual(request.args[:2], ("POST", service.PHOTO_REPLY_URL))
        data = request.kwargs["data"]
        self.assertEqual(
            (data["topicId"], data["commentId"], data["commentUin"]),
            ("album_pic2_0_0", "42", 4),
        )
        self.assertEqual(data["ref"], "photo")
        self.manager.generate_qzone_auto_comment.assert_not_awaited()

    async def test_album_unknown_submission_stops_entire_batch_retry(self):
        posts = self.album_posts()
        self.service.query_recent_posts.return_value = posts
        error = RuntimeError("提交状态未知")
        error.submission_unknown = True
        self.service.reply_comment.side_effect = error
        first = await self.run_task()
        posts[0].comments.append(replace(self.comment, tid="43", uin=5))
        second = await self.run_task()
        self.assertEqual((first["commented"], second["commented"]), (0, 0))
        self.service.reply_comment.assert_awaited_once()
        self.service.comment.assert_not_awaited()

    def test_album_private_or_wrong_photo_comments_are_excluded(self):
        post = self.album_posts()[1]
        for fields in ({"photo_private": 1}, {"photo_topic_id": "album_pic1_0_0"}):
            with self.subTest(fields=fields):
                comment = replace(self.comment, raw_fields=fields)
                self.assertFalse(
                    self.manager._qzone_auto_comment_reply_candidate(
                        post, comment, self_uin=1, processed={}
                    )
                )

"""发布自己的说说后的后台点赞、自评与持久化防重。所有提交均为替身。"""

import asyncio
import importlib
import types
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, Mock, patch

from .testqzone import _load_qzone_service, _new_qzone_service
from .testqzonecomment import FakeDb, _interaction_args, _load_auto_comment_module


class SelfPostTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.module = _load_qzone_service()
        self.post = self.module.QzonePost(
            tid="self-post-1", uin=10001, name="测试 Bot", text="终于把房间收拾好了"
        )
        self.conf = {
            "qzone_trigger_mode": "llm_smart",
            "qzone_auto_like_own_post": True,
            "qzone_self_comment_probability": 100,
            "qzone_enable_auto_interaction": False,
        }
        self.interaction = types.SimpleNamespace(
            wants_interaction=AsyncMock(return_value=True),
            interaction_state=AsyncMock(return_value={"decision": "skip"}),
            interaction_ready=AsyncMock(return_value=True),
            generate_qzone_self_comment=AsyncMock(
                return_value="维持整洁就看明天的我了"
            ),
            record_qzone_self_comment=AsyncMock(),
        )
        self.plugin = types.SimpleNamespace(
            qzone_conf=self.conf,
            _is_terminated=False,
            db=FakeDb(),
            task_manager=types.SimpleNamespace(qzone_interaction=self.interaction),
            track_task=Mock(),
        )
        self.service = _new_qzone_service(self.module, self.plugin)
        self.service.context = AsyncMock(
            return_value=self.module.QzoneContext(10001, "dummy", "dummy")
        )
        self.service.like = AsyncMock()
        self.service.comment = AsyncMock()
        self.self_post = self.service.self_post
        self.self_module = importlib.import_module(self.self_post.__module__)
        self.state_key = self.self_module.SELF_POST_STATE_KEY

    @property
    def entry(self):
        return self.plugin.db.state[self.state_key][self.post.key]

    async def test_like_then_comment_independent_of_friend_interaction_switch(self):
        calls = []
        self.service.like.side_effect = lambda *args: calls.append("like")
        self.interaction.generate_qzone_self_comment.side_effect = (
            lambda *args, **kwargs: calls.append("generate") or "维持整洁就看明天的我了"
        )
        self.service.comment.side_effect = lambda *args: calls.append("comment")
        await self.self_post.run(self.post, image_count=2)
        self.assertEqual(calls, ["like", "generate", "comment"])
        self.assertEqual(self.entry["comment"], "commented")
        self.interaction.generate_qzone_self_comment.assert_awaited_once_with(
            self.post, image_count=2
        )
        self.interaction.record_qzone_self_comment.assert_awaited_once()

    async def test_cleaned_self_comment_matches_submission_and_memory(self):
        clean = AsyncMock(return_value="清洗后的正文")
        self.plugin.daily_life_bridge = types.SimpleNamespace(
            clean_expression_punctuation=clean
        )
        await self.self_post.run(self.post)
        clean.assert_awaited_once_with("维持整洁就看明天的我了", scene="qzone_comment")
        self.assertEqual(self.entry["content"], "清洗后的正文")
        self.service.comment.assert_awaited_once_with(self.post.key, "清洗后的正文")
        self.interaction.record_qzone_self_comment.assert_awaited_once_with(
            self.post, "清洗后的正文"
        )

    async def test_empty_cleaned_self_comment_is_never_submitted(self):
        self.plugin.daily_life_bridge = types.SimpleNamespace(
            clean_expression_punctuation=AsyncMock(return_value=" ")
        )
        await self.self_post.run(self.post)
        self.service.comment.assert_not_awaited()
        self.interaction.record_qzone_self_comment.assert_not_awaited()

    async def test_default_living_settings_delegate_like_and_comment_to_intent(self):
        self.conf.clear()
        with patch.object(self.self_module.random, "random") as roll:
            await self.self_post.run(self.post)
        roll.assert_not_called()
        self.assertEqual(self.interaction.wants_interaction.await_count, 2)
        self.service.like.assert_awaited_once()
        self.service.comment.assert_awaited_once()

    async def test_probability_miss_does_not_call_model_or_reroll(self):
        self.conf["qzone_self_comment_probability"] = 30
        with patch.object(self.self_module.random, "random", return_value=0.3) as roll:
            await self.self_post.run(self.post)
            await self.self_post.run(self.post)
        roll.assert_called_once()
        self.interaction.generate_qzone_self_comment.assert_not_awaited()
        self.service.like.assert_awaited_once()
        self.assertEqual(self.entry["comment"], "skipped")

    async def test_living_skips_like_and_comment_without_intent_and_does_not_reroll(
        self,
    ):
        self.conf["qzone_trigger_mode"] = "life_driven"
        self.interaction.wants_interaction.return_value = False
        await self.self_post.run(self.post)
        await self.self_post.run(self.post)
        self.assertEqual(self.interaction.wants_interaction.await_count, 2)
        self.service.like.assert_not_awaited()
        self.service.comment.assert_not_awaited()
        self.interaction.generate_qzone_self_comment.assert_not_awaited()
        self.assertEqual(self.entry["like"], "skipped")
        self.assertEqual(self.entry["comment"], "skipped")

    async def test_living_uses_intent_instead_of_probability_roll(self):
        self.conf.update(
            qzone_trigger_mode="life_driven", qzone_self_comment_probability=1
        )
        with patch.object(self.self_module.random, "random") as roll:
            await self.self_post.run(self.post)
        roll.assert_not_called()
        self.assertEqual(
            [
                call.args[0]
                for call in self.interaction.wants_interaction.await_args_list
            ],
            ["self_like", "self_comment"],
        )
        self.service.like.assert_awaited_once()
        self.service.comment.assert_awaited_once()

    async def test_living_sleep_after_generation_stops_comment_submission(self):
        self.conf.update(
            qzone_trigger_mode="life_driven", qzone_auto_like_own_post=False
        )

        async def generate(*args, **kwargs):
            self.interaction.interaction_ready.return_value = False
            return "明天再慢慢收拾"

        self.interaction.interaction_state.return_value = {
            "decision": "act",
            "status": "preparing",
        }
        self.interaction.generate_qzone_self_comment.side_effect = generate
        await self.self_post.run(self.post)
        self.service.comment.assert_not_awaited()
        self.interaction.record_qzone_self_comment.assert_not_awaited()
        self.assertEqual(self.entry["comment"], "waiting")

    async def test_wait_survives_restart_and_only_submits_once(self):
        self.conf["qzone_trigger_mode"] = "life_driven"
        self.interaction.wants_interaction.return_value = False
        self.interaction.interaction_state.return_value = {
            "decision": "wait",
            "review_at": 0,
        }
        await self.self_post.run(self.post, image_count=2)
        self.assertEqual(self.entry["comment"], "waiting")
        self.service.comment.assert_not_awaited()
        self.entry["review"] = {"like": 0, "comment": 0}
        self.interaction.wants_interaction.return_value = True
        restarted = self.self_module.QzoneSelfPostService(self.service, self.plugin)
        await restarted.review_pending()
        await restarted.review_pending()
        self.service.like.assert_awaited_once()
        self.service.comment.assert_awaited_once()
        self.interaction.generate_qzone_self_comment.assert_awaited_once()
        call = self.interaction.generate_qzone_self_comment.await_args
        self.assertEqual(call.args[0].key, self.post.key)
        self.assertEqual(call.kwargs["image_count"], 2)

    async def test_review_during_sleep_does_not_consume_wait_checks(self):
        self.conf["qzone_trigger_mode"] = "life_driven"
        self.interaction.wants_interaction.return_value = False
        self.interaction.interaction_state.return_value = {"decision": "wait"}
        await self.self_post.run(self.post)
        self.entry["review"] = {"like": 0, "comment": 0}
        checks = dict(self.entry["checks"])
        self.interaction.interaction_ready.return_value = False
        await self.self_post.review_pending()
        self.assertEqual(self.entry["checks"], checks)

    async def test_wait_expires_and_unknown_submission_is_never_reopened(self):
        self.conf["qzone_trigger_mode"] = "life_driven"
        self.interaction.wants_interaction.return_value = False
        self.interaction.interaction_state.return_value = {"decision": "wait"}
        await self.self_post.run(self.post)
        self.entry["at"] -= 7 * 3600
        self.entry["like"] = "submitting"
        self.entry["review"]["comment"] = 0
        await self.self_post.review_pending()
        self.assertEqual(self.entry["like"], "submitting")
        self.assertEqual(self.entry["comment"], "expired")
        self.service.like.assert_not_awaited()
        self.service.comment.assert_not_awaited()

    async def test_preparation_failures_have_a_finite_retry_budget(self):
        self.conf.update(
            qzone_trigger_mode="life_driven", qzone_auto_like_own_post=False
        )
        self.interaction.generate_qzone_self_comment.side_effect = RuntimeError(
            "模型暂时不可用"
        )
        for _ in range(5):
            if self.post.key in self.plugin.db.state.get(self.state_key, {}):
                self.entry["review"]["comment"] = 0
            await self.self_post.run(self.post)
        self.assertEqual(self.interaction.generate_qzone_self_comment.await_count, 3)
        self.assertEqual(self.entry["comment"], "exhausted")
        self.service.comment.assert_not_awaited()

    async def test_zero_probability_only_likes_without_rng_or_model(self):
        self.conf["qzone_self_comment_probability"] = 0
        with patch.object(self.self_module.random, "random") as roll:
            await self.self_post.run(self.post)
        roll.assert_not_called()
        self.interaction.generate_qzone_self_comment.assert_not_awaited()
        self.service.like.assert_awaited_once()

    async def test_hundred_percent_only_comments_when_like_disabled(self):
        self.conf["qzone_auto_like_own_post"] = False
        with patch.object(self.self_module.random, "random") as roll:
            await self.self_post.run(self.post)
        roll.assert_not_called()
        self.service.like.assert_not_awaited()
        self.service.comment.assert_awaited_once()

    async def test_disabled_settings_do_not_start_background_task(self):
        self.conf.update(
            qzone_auto_like_own_post=False, qzone_self_comment_probability=0
        )
        self.self_post.schedule(self.post)
        self.plugin.track_task.assert_not_called()

    async def test_same_post_concurrent_callbacks_only_act_once(self):
        await asyncio.gather(*(self.self_post.run(self.post) for _ in range(3)))
        self.service.like.assert_awaited_once()
        self.service.comment.assert_awaited_once()

    async def test_new_service_reuses_persisted_dedup_state(self):
        await self.self_post.run(self.post)
        restarted = self.self_module.QzoneSelfPostService(self.service, self.plugin)
        await restarted.run(self.post)
        self.service.comment.assert_awaited_once()

    async def test_failure_to_persist_claim_prevents_all_actions(self):
        self.plugin.db.merge_cache_entries = AsyncMock(
            side_effect=RuntimeError("db busy")
        )
        await self.self_post.run(self.post)
        self.service.like.assert_not_awaited()
        self.interaction.generate_qzone_self_comment.assert_not_awaited()

    async def test_like_failure_does_not_disable_comment(self):
        self.service.like.side_effect = RuntimeError("点赞失败")
        await self.self_post.run(self.post)
        self.assertEqual(self.entry["like"], "failed")
        self.service.comment.assert_awaited_once()

    async def test_generation_failure_keeps_like_and_does_not_retry(self):
        self.interaction.generate_qzone_self_comment.side_effect = RuntimeError(
            "模型超时"
        )
        await self.self_post.run(self.post)
        await self.self_post.run(self.post)
        self.service.like.assert_awaited_once()
        self.interaction.generate_qzone_self_comment.assert_awaited_once()
        self.service.comment.assert_not_awaited()

    async def test_unknown_comment_submission_does_not_retry(self):
        self.service.comment.side_effect = RuntimeError("提交状态未知")
        await self.self_post.run(self.post)
        await self.self_post.run(self.post)
        self.assertEqual(self.entry["comment"], "unconfirmed")
        self.service.comment.assert_awaited_once()
        self.interaction.record_qzone_self_comment.assert_not_awaited()

    async def test_cancel_during_submit_keeps_persisted_submission_marker(self):
        started = asyncio.Event()

        async def submit(*args):
            self.assertEqual(self.entry["comment"], "submitting")
            started.set()
            await asyncio.Event().wait()

        self.service.comment.side_effect = submit
        task = asyncio.create_task(self.self_post.run(self.post))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await self.self_post.run(self.post)
        self.service.comment.assert_awaited_once()

    async def test_disable_during_generation_prevents_comment(self):
        async def generate(*args, **kwargs):
            self.conf["qzone_self_comment_probability"] = 0
            return "明天继续努力"

        self.interaction.generate_qzone_self_comment.side_effect = generate
        await self.self_post.run(self.post)
        self.service.comment.assert_not_awaited()
        self.assertEqual(self.entry["comment"], "cancelled")

    async def test_shutdown_during_generation_prevents_comment(self):
        async def generate(*args, **kwargs):
            self.plugin._is_terminated = True
            return "明天继续努力"

        self.interaction.generate_qzone_self_comment.side_effect = generate
        await self.self_post.run(self.post)
        self.service.comment.assert_not_awaited()

    async def test_wrong_account_missing_id_and_album_do_not_act(self):
        for post in (
            replace(self.post, uin=10002),
            replace(self.post, tid=""),
            replace(self.post, appid=4),
        ):
            await self.self_post.run(post)
        self.service.like.assert_not_awaited()
        self.service.comment.assert_not_awaited()

    async def test_state_has_bounded_capacity(self):
        limit = self.self_module.SELF_POST_STATE_LIMIT
        self.plugin.db.state[self.state_key] = {str(i): {} for i in range(limit)}
        await self.self_post.run(self.post)
        state = self.plugin.db.state[self.state_key]
        self.assertEqual(len(state), limit)
        self.assertIn(self.post.key, state)

    async def test_publish_returns_while_self_comment_generation_is_pending(self):
        started = asyncio.Event()
        release = asyncio.Event()
        tasks = []

        async def generate(*args, **kwargs):
            started.set()
            await release.wait()
            return "维持整洁就看明天的我了"

        self.interaction.generate_qzone_self_comment.side_effect = generate
        self.plugin.track_task.side_effect = lambda coro: tasks.append(
            asyncio.create_task(coro)
        )
        self.service._submit_post = AsyncMock(
            return_value={"code": 0, "tid": self.post.tid}
        )
        published = await asyncio.wait_for(
            self.service.publish_post(text=self.post.text), 1
        )
        await asyncio.wait_for(started.wait(), 1)
        self.assertEqual(published.tid, self.post.tid)
        self.assertFalse(tasks[0].done())
        release.set()
        await asyncio.gather(*tasks)
        self.service.comment.assert_awaited_once()

    async def test_background_start_failure_does_not_make_publish_fail(self):
        self.plugin.track_task.side_effect = RuntimeError("Cookie 失效测试")
        self.service._submit_post = AsyncMock(
            return_value={"code": 0, "tid": "published"}
        )
        post = await self.service.publish_post(text="测试发布")
        self.assertEqual(post.tid, "published")
        self.service._submit_post.assert_awaited_once()

    async def test_timeout_confirmed_publication_schedules_once(self):
        self.service._submit_post = AsyncMock(side_effect=RuntimeError("timeout"))
        self.service._confirm_ambiguous_publish = AsyncMock(return_value=self.post)
        self.plugin.track_task.side_effect = lambda coro: coro.close()
        with patch.object(self.module.asyncio, "sleep", new=AsyncMock()):
            post = await self.service.publish_post(text=self.post.text)
        self.assertIs(post, self.post)
        self.plugin.track_task.assert_called_once()
        self.service._submit_post.assert_awaited_once()

    async def test_unconfirmed_publication_does_not_schedule(self):
        self.service._submit_post = AsyncMock(side_effect=RuntimeError("timeout"))
        self.service._confirm_ambiguous_publish = AsyncMock(return_value=None)
        with patch.object(self.module.asyncio, "sleep", new=AsyncMock()):
            with self.assertRaises(self.module.QzonePublishUnknownError):
                await self.service.publish_post(text=self.post.text)
        self.plugin.track_task.assert_not_called()

    async def test_success_without_post_id_does_not_schedule(self):
        self.service._submit_post = AsyncMock(return_value={"code": 0})
        await self.service.publish_post(text=self.post.text)
        self.plugin.track_task.assert_not_called()

    def test_probability_normalization(self):
        for value, expected in (
            (-10, 0),
            (150, 100),
            ("25", 25),
            (None, 30),
            ("bad", 30),
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    self.self_module.self_comment_probability(
                        {"qzone_self_comment_probability": value}
                    ),
                    expected,
                )


class SelfCommentPromptTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.module, self.models = _load_auto_comment_module()
        runtime, config, state = _interaction_args(self.module)
        self.plugin = runtime.plugin
        self.plugin.call_llm = AsyncMock(return_value="维持整洁就看明天的我了")
        self.plugin.content_service = types.SimpleNamespace(
            get_persona_info=AsyncMock(return_value={"prompt": "你是测试人设"}),
            get_qzone_chat_style_prompt=AsyncMock(return_value="自然口语，简短接话"),
        )
        self.owner = self.module.TaskQzoneAutoCommentService(runtime, config, state)
        self.post = self.models.QzonePost(
            tid="self-1", uin=10001, text="终于把房间收拾好了"
        )

    async def test_prompt_uses_own_author_identity_original_text_and_persona(self):
        result = await self.owner.generate_qzone_self_comment(self.post, image_count=2)
        self.assertEqual(result, "维持整洁就看明天的我了")
        args = self.plugin.call_llm.await_args.kwargs
        self.assertIn(self.post.text, args["prompt"])
        self.assertIn("配图数量：2", args["prompt"])
        self.assertIn("你本人刚发布", args["system_prompt"])
        self.assertIn("自嘲", args["system_prompt"])
        self.assertIn("你是测试人设", args["system_prompt"])
        self.assertIn("自然口语", args["system_prompt"])
        self.plugin.call_llm.assert_awaited_once()

    async def test_prompt_uses_public_life_context_and_related_memory(self):
        context = AsyncMock(
            return_value={
                "life_context": "最近状态：收拾完房间后有点累",
                "continuity_context": "【已确认生活连续性】\n已有整理房间的记录",
                "body_context": "【当前身体状态】\n疲劳适中",
                "relationship_context": "仅限好友私聊的关系资料",
            }
        )
        self.owner.runtime = replace(
            self.owner.runtime,
            ctx_service=types.SimpleNamespace(
                get_qzone_interaction_context=context,
            ),
        )
        memory = AsyncMock(
            return_value="【本地相关记忆，仅作背景】\n之前也提到过整理房间"
        )
        self.plugin.daily_life_bridge = types.SimpleNamespace(
            related_memory_prompt=memory,
        )

        await self.owner.generate_qzone_self_comment(self.post)

        args = self.plugin.call_llm.await_args.kwargs
        self.assertIn("最近状态：收拾完房间后有点累", args["prompt"])
        self.assertIn("已有整理房间的记录", args["prompt"])
        self.assertIn("当前身体状态", args["prompt"])
        self.assertIn("之前也提到过整理房间", args["prompt"])
        self.assertNotIn("仅限好友私聊的关系资料", args["prompt"])
        context.assert_awaited_once_with("qzone_broadcast")
        memory.assert_awaited_once_with(self.post.text, "qzone_broadcast")

    async def test_daily_life_failures_fall_back_to_persona_only_prompt(self):
        self.owner.runtime = replace(
            self.owner.runtime,
            ctx_service=types.SimpleNamespace(
                get_qzone_interaction_context=AsyncMock(
                    side_effect=RuntimeError("生活快照暂不可用")
                ),
            ),
        )
        self.plugin.daily_life_bridge = types.SimpleNamespace(
            related_memory_prompt=AsyncMock(
                side_effect=RuntimeError("记忆检索暂不可用")
            ),
        )

        result = await self.owner.generate_qzone_self_comment(self.post)

        self.assertEqual(result, "维持整洁就看明天的我了")
        args = self.plugin.call_llm.await_args.kwargs
        self.assertIn(self.post.text, args["prompt"])
        self.assertNotIn("生活快照暂不可用", args["prompt"])
        self.assertNotIn("记忆检索暂不可用", args["prompt"])
        self.plugin.call_llm.assert_awaited_once()

    async def test_empty_generation_does_not_produce_a_comment(self):
        self.plugin.call_llm.return_value = ""
        with self.assertRaisesRegex(RuntimeError, "有效内容"):
            await self.owner.generate_qzone_self_comment(self.post)

    async def test_repeated_post_text_is_rejected_without_second_model_call(self):
        self.plugin.call_llm.return_value = self.post.text
        with self.assertRaisesRegex(RuntimeError, "重复"):
            await self.owner.generate_qzone_self_comment(self.post)
        self.plugin.call_llm.assert_awaited_once()

    async def test_image_only_post_does_not_invent_image_observation(self):
        self.post.text = ""
        await self.owner.generate_qzone_self_comment(self.post, image_count=1)
        args = self.plugin.call_llm.await_args.kwargs
        self.assertIn("仅发布了图片", args["prompt"])
        self.assertIn("未提供画面资料", args["prompt"])
        self.assertIn("不编造", args["system_prompt"])


if __name__ == "__main__":
    unittest.main()

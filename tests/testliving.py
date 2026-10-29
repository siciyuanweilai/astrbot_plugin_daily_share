"""生活分享与空间意愿的端到端调度边界；所有模型及发送调用均为替身。"""

import copy
import importlib
import json
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from . import testfailure as fixtures


class LivingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.module = fixtures._load_tasks_module()
        prefix = fixtures.TASKS_MODULE_NAME
        self.material = importlib.import_module(prefix + ".opportunity")
        self.intent = importlib.import_module(prefix + ".interact.intent")
        self.living_module = importlib.import_module(prefix + ".scheduler.living")
        self.submission = importlib.import_module(
            fixtures.CORE_PACKAGE_NAME + ".submission"
        )
        self.plugin = fixtures._Plugin()
        self.plugin.config["enable_auto_share"] = True
        self.plugin.basic_conf.update(
            trigger_mode="life_driven", smart_schedule_quiet_hours=[]
        )
        self.plugin.qzone_conf.update(
            enable_qzone=True,
            qzone_trigger_mode="life_driven",
            qzone_smart_schedule_quiet_hours=[],
            qzone_enable_auto_interaction=True,
            qzone_enable_auto_like=True,
            qzone_enable_auto_comment=True,
        )
        self.manager = fixtures._new_manager(self.module, self.plugin)
        self.plugin.task_manager = self.manager
        self.living = self.manager.schedule.living
        self.target = fixtures.USER_TARGET_1
        now = datetime.now(self.material.SHANGHAI)
        self.data = {
            "current_facts": {
                "valid": True,
                "date": now.date().isoformat(),
                "current_action": {
                    "status": "running",
                    "observation_state": "observed",
                    "action_id": "cooking-1",
                    "activity": "试着做一道新菜",
                    "observed_at": now.isoformat(),
                },
            },
            "subject": {"sleep_depth": "awake", "can_interrupt_default": True},
            "state": {"mood": "有些期待"},
            "conversation_timing": {"last_sent_at": "before-decision"},
        }
        self.bridge = self.plugin.daily_life_bridge = types.SimpleNamespace(
            get_share_context=AsyncMock(
                side_effect=lambda _target: copy.deepcopy(self.data)
            )
        )
        self.plugin.content_service.get_persona_info = AsyncMock(
            return_value={"prompt": "角色的人设"}
        )
        self.plugin.ctx_service.get_qzone_interaction_context = AsyncMock(
            return_value={
                "life_context": "正在做菜",
                "relationship_context": "熟悉的朋友",
            }
        )
        self.plugin.call_llm = AsyncMock(return_value='{"decision":"skip"}')
        self.manager.share.execute_share = AsyncMock(return_value=True)
        self.manager.qzone_share.execute_qzone_share = AsyncMock(return_value=True)
        self.owner = self.manager.qzone_interaction
        self.post = types.SimpleNamespace(
            key="20002:post-1", text="周末去了海边", name="朋友", uin=20002, images=[]
        )
        self.plugin.qzone_service = types.SimpleNamespace(
            relationship_target=lambda uin: "qq:FriendMessage:" + uin
        )

    async def consider(self):
        await self.living.consider(
            self.target, generation=self.manager.schedule._build_generation
        )

    def share_decision(self):
        rows = self.material.share_material(
            self.data, datetime.now(self.material.SHANGHAI)
        )
        return json.dumps(
            {"decision": "share", "evidence_ids": [rows[0]["id"]], "share_type": "mood"}
        )

    def state(self):
        return self.plugin.db.state[self.living_module._STATE][self.target]

    def expire_share_backoff(self):
        self.state().update(review_at=0, error_until=0)

    def expire_interaction_backoff(self):
        for state in self.plugin.db.state.get(self.intent._STATE, {}).values():
            state["review_at"] = 0

    async def test_no_material_does_not_call_model_or_send(self):
        self.data["current_facts"]["current_action"] = {}
        await self.consider()
        self.plugin.call_llm.assert_not_awaited()
        self.manager.share.execute_share.assert_not_awaited()

    async def test_plans_and_body_number_changes_are_not_new_experiences(self):
        self.data["current_facts"]["current_action"] = {}
        self.data["current_facts"]["body"] = {"energy": 76, "fatigue": 17}
        self.data["timeline"] = [
            {"activity": "今晚去看海", "execution_state": "pending"}
        ]
        self.data["continuity"] = {
            "activities": [
                {
                    "title": "明天爬山",
                    "state": "planned",
                    "at": datetime.now(self.material.SHANGHAI).isoformat(),
                }
            ]
        }
        await self.consider()
        self.data["current_facts"]["body"]["energy"] = 75
        await self.consider()
        self.plugin.call_llm.assert_not_awaited()

    async def test_invalid_or_future_observation_is_not_shareable(self):
        now = datetime.now(self.material.SHANGHAI)
        for valid, at in (
            (False, now),
            (True, now + timedelta(hours=1)),
            (True, now - timedelta(hours=7)),
        ):
            self.data["current_facts"]["valid"] = valid
            self.data["current_facts"]["current_action"]["observed_at"] = at.isoformat()
            await self.consider()
        self.plugin.call_llm.assert_not_awaited()

    async def test_skip_survives_manager_rebuild(self):
        await self.consider()
        self.manager = fixtures._new_manager(self.module, self.plugin)
        self.living = self.manager.schedule.living
        await self.consider()
        self.plugin.call_llm.assert_awaited_once()

    async def test_wait_only_reviews_without_scheduling_publication(self):
        self.plugin.call_llm.return_value = (
            '{"decision":"wait","reconsider_after_minutes":45}'
        )
        await self.consider()
        await self.consider()
        self.plugin.call_llm.assert_awaited_once()
        self.assertEqual(self.plugin.scheduler.jobs, [])
        self.manager.share.execute_share.assert_not_awaited()

    async def test_selected_facts_reach_only_the_intended_generator(self):
        self.plugin.call_llm.return_value = self.share_decision()
        captured = []

        async def generate(**kwargs):
            captured.append(self.material.opportunity_prompt(self.target))
            self.assertEqual(self.material.opportunity_prompt("another-target"), "")

        self.manager.share.execute_share.side_effect = generate
        await self.consider()
        self.assertIn("试着做一道新菜", captured[0])
        self.assertEqual(self.material.opportunity_prompt(self.target), "")
        self.assertEqual(
            self.manager.share.execute_share.await_args.kwargs["source_type"],
            "life_driven",
        )

    async def test_living_decision_uses_llm_target_parameter(self):
        await self.consider()
        kwargs = self.plugin.call_llm.await_args.kwargs
        self.assertEqual(kwargs["umo"], self.target)
        self.assertNotIn("target_umo", kwargs)

    async def test_preparation_failure_keeps_material_with_backoff(self):
        self.plugin.call_llm.return_value = self.share_decision()
        self.manager.share.execute_share.side_effect = RuntimeError("结果未确认")
        with self.assertRaises(RuntimeError):
            await self.consider()
        await self.consider()
        self.assertEqual(self.state()["attempts"], 1)
        self.assertEqual(self.state().get("seen", []), [])
        self.manager.share.execute_share.assert_awaited_once()
        self.assertEqual(self.material.opportunity_prompt(self.target), "")
        self.expire_share_backoff()
        self.manager.share.execute_share.side_effect = None
        await self.consider()
        self.assertEqual(self.manager.share.execute_share.await_count, 2)
        self.assertTrue(self.state()["seen"])

    async def test_false_before_submission_recovers_but_stops_after_three_attempts(
        self,
    ):
        self.plugin.basic_conf["smart_schedule_max_count"] = 6
        self.plugin.call_llm.return_value = self.share_decision()
        self.manager.share.execute_share.return_value = False
        for _ in range(5):
            await self.consider()
            self.expire_share_backoff()
        self.assertEqual(self.manager.share.execute_share.await_count, 3)
        self.assertEqual(self.state().get("seen", []), [])

    async def test_unknown_submission_survives_rebuild_without_resend(self):
        self.plugin.call_llm.return_value = self.share_decision()

        async def unknown(**kwargs):
            await self.submission.mark_submission()
            raise TimeoutError("平台回执超时")

        self.manager.share.execute_share.side_effect = unknown
        with self.assertRaises(TimeoutError):
            await self.consider()
        self.assertEqual(self.state()["reservation"]["status"], "submitting")
        self.assertTrue(self.state()["seen"])
        self.expire_share_backoff()
        rebuilt = fixtures._new_manager(self.module, self.plugin)
        rebuilt.share.execute_share = AsyncMock()
        await rebuilt.schedule.living.consider(self.target, generation=0)
        rebuilt.share.execute_share.assert_not_awaited()
        self.plugin.call_llm.assert_awaited_once()

    async def test_deferred_media_owns_the_opportunity(self):
        self.plugin.call_llm.return_value = self.share_decision()

        async def pending(**kwargs):
            await self.submission.mark_submission("deferred")
            return False

        self.manager.share.execute_share.side_effect = pending
        await self.consider()
        self.expire_share_backoff()
        await self.consider()
        self.assertEqual(self.state()["reservation"]["status"], "deferred")
        self.manager.share.execute_share.assert_awaited_once()

    async def test_retry_rechecks_sleep_and_material_freshness(self):
        self.plugin.call_llm.return_value = self.share_decision()
        self.manager.share.execute_share.return_value = False
        await self.consider()
        self.expire_share_backoff()
        self.data["subject"]["sleep_depth"] = "deep_sleep"
        await self.consider()
        self.data["subject"]["sleep_depth"] = "awake"
        self.data["current_facts"]["current_action"]["observed_at"] = (
            datetime.now(self.material.SHANGHAI) - timedelta(hours=7)
        ).isoformat()
        await self.consider()
        self.manager.share.execute_share.assert_awaited_once()

    async def test_route_failure_does_not_consume_share_material(self):
        self.plugin.call_llm.return_value = self.share_decision()

        async def send(**kwargs):
            await self.manager.delivery.chains.send_message_chain(self.target, object())

        self.manager.share.execute_share.side_effect = send
        with patch.object(
            self.manager.targets,
            "ensure_target_platform_routable",
            side_effect=ValueError("实例暂未就绪"),
        ):
            with self.assertRaises(ValueError):
                await self.consider()
        self.assertEqual(self.state().get("seen", []), [])

    async def test_actual_platform_call_is_guarded_before_timeout(self):
        self.plugin.call_llm.return_value = self.share_decision()
        chain_module = importlib.import_module(
            fixtures.TASKS_MODULE_NAME + ".transmit.chain"
        )

        async def platform_send(*args):
            self.assertTrue(self.state()["seen"])
            self.assertEqual(self.state()["reservation"]["status"], "submitting")
            raise TimeoutError("回执未知")

        async def send(**kwargs):
            await self.manager.delivery.chains.send_message_chain(self.target, object())

        self.plugin.context.send_message = AsyncMock(side_effect=platform_send)
        self.manager.share.execute_share.side_effect = send
        with (
            patch.object(
                self.manager.targets,
                "ensure_target_platform_routable",
                return_value=types.SimpleNamespace(shared_id=False),
            ),
            patch.object(chain_module, "ensure_qq_official_background_send"),
        ):
            with self.assertRaises(TimeoutError):
                await self.consider()
        self.expire_share_backoff()
        await self.consider()
        self.plugin.context.send_message.assert_awaited_once()

    async def test_submission_checkpoint_failure_prevents_platform_call(self):
        calls = AsyncMock()

        async def checkpoint(phase):
            raise OSError("状态写入失败")

        token = self.submission.current_submission.set({"checkpoint": checkpoint})
        try:
            with self.assertRaises(OSError):
                await self.submission.mark_submission()
                await calls()
        finally:
            self.submission.current_submission.reset(token)
        calls.assert_not_awaited()

    async def test_daily_limit_is_a_ceiling_and_not_a_fill_target(self):
        self.plugin.basic_conf["smart_schedule_max_count"] = 1
        self.plugin.call_llm.return_value = self.share_decision()
        await self.consider()
        self.data["current_facts"]["current_action"]["action_id"] = "new-activity"
        await self.consider()
        self.plugin.call_llm.assert_awaited_once()
        self.manager.share.execute_share.assert_awaited_once()

    async def test_shared_contact_pressure_blocks_model_and_share(self):
        self.data["contact_rhythm"] = {
            "ready": False,
            "retry_after": 300,
            "willingness": 0.85,
        }
        await self.consider()
        self.plugin.call_llm.assert_not_awaited()
        self.manager.share.execute_share.assert_not_awaited()

    async def test_contact_during_decision_cancels_old_share(self):
        decision = self.share_decision()

        async def decide(**kwargs):
            self.data["contact_rhythm"] = {"ready": False, "retry_after": 180}
            return decision

        self.plugin.call_llm.side_effect = decide
        await self.consider()
        self.manager.share.execute_share.assert_not_awaited()
        self.assertEqual(self.state()["attempts"], 0)

    async def test_life_mode_can_use_a_limit_above_six(self):
        self.plugin.basic_conf["smart_schedule_max_count"] = 12
        await self.plugin.db.update_share_state(
            self.living_module._STATE,
            {
                self.target: {
                    "date": datetime.now(self.material.SHANGHAI).date().isoformat(),
                    "attempts": 6,
                }
            },
        )
        self.data["contact_rhythm"] = {"willingness": 0.85, "ready": True}
        self.plugin.call_llm.return_value = self.share_decision()
        await self.consider()
        self.manager.share.execute_share.assert_awaited_once()
        self.assertEqual(self.state()["attempts"], 7)
        self.assertIn(
            '"willingness": 0.85', self.plugin.call_llm.await_args.kwargs["prompt"]
        )

    async def test_sleep_and_non_interruptible_activity_block_evaluation(self):
        for subject in (
            {"sleep_depth": "deep_sleep"},
            {"can_interrupt_default": False},
        ):
            self.data["subject"] = subject
            await self.consider()
        self.plugin.call_llm.assert_not_awaited()

    async def test_sleep_during_decision_blocks_send(self):
        decision = self.share_decision()

        async def decide(**kwargs):
            self.data["subject"]["sleep_depth"] = "deep_sleep"
            return decision

        self.plugin.call_llm.side_effect = decide
        await self.consider()
        self.manager.share.execute_share.assert_not_awaited()

    async def test_conversation_changed_during_decision_blocks_send(self):
        decision = self.share_decision()

        async def decide(**kwargs):
            self.data["conversation_timing"]["last_sent_at"] = "new-reply"
            return decision

        self.plugin.call_llm.side_effect = decide
        await self.consider()
        self.manager.share.execute_share.assert_not_awaited()

    async def test_bad_model_output_uses_backoff_even_with_new_material(self):
        self.plugin.call_llm.return_value = "broken JSON"
        with self.assertRaises(ValueError):
            await self.consider()
        self.data["current_facts"]["current_action"]["action_id"] = "another"
        await self.consider()
        self.plugin.call_llm.assert_awaited_once()
        self.manager.share.execute_share.assert_not_awaited()

    async def test_invented_material_id_never_sends(self):
        self.plugin.call_llm.return_value = (
            '{"decision":"share","evidence_ids":["invented"],"share_type":"mood"}'
        )
        await self.consider()
        self.manager.share.execute_share.assert_not_awaited()

    async def test_disabled_or_stale_generation_does_not_evaluate(self):
        await self.living.consider(self.target, generation=-1)
        self.plugin.config["enable_auto_share"] = False
        await self.consider()
        self.plugin.call_llm.assert_not_awaited()

    async def test_public_and_private_materials_have_separate_decisions(self):
        await self.consider()
        await self.living.consider("qzone_broadcast", generation=0)
        self.assertEqual(self.plugin.call_llm.await_count, 2)

    async def test_space_sleep_prevents_query_and_decision(self):
        self.data["subject"]["sleep_depth"] = "deep_sleep"
        result = await self.owner.execute_qzone_auto_interaction()
        self.assertEqual(result["scanned"], 0)
        self.plugin.call_llm.assert_not_awaited()

    async def test_space_skip_is_not_rerolled_by_polling(self):
        self.assertFalse(
            await self.intent.wants_interaction(self.owner, "comment", self.post)
        )
        kwargs = self.plugin.call_llm.await_args.kwargs
        self.assertEqual(kwargs["umo"], "qzone_broadcast")
        self.assertNotIn("target_umo", kwargs)
        self.assertFalse(
            await self.intent.wants_interaction(self.owner, "comment", self.post)
        )
        self.plugin.call_llm.assert_awaited_once()
        # 持久决定已命中，后续轮询不再重复导出生活档案。
        self.bridge.get_share_context.assert_awaited_once()

    async def test_space_act_reserves_then_allows_bounded_preparation_retry(self):
        self.plugin.call_llm.return_value = '{"decision":"act"}'
        self.assertTrue(
            await self.intent.wants_interaction(self.owner, "like", self.post)
        )
        self.assertFalse(
            await self.intent.wants_interaction(self.owner, "like", self.post)
        )
        self.assertTrue(
            await self.intent.wants_interaction(self.owner, "comment", self.post)
        )
        self.assertEqual(self.plugin.call_llm.await_count, 2)
        for expected in (True, True, False):
            self.expire_interaction_backoff()
            self.assertEqual(
                await self.intent.wants_interaction(self.owner, "like", self.post),
                expected,
            )

    async def test_space_unknown_submission_never_expires_into_retry(self):
        self.plugin.call_llm.return_value = '{"decision":"act"}'
        await self.intent.wants_interaction(self.owner, "like", self.post)
        await self.intent.mark_interaction_submission(self.owner, "like", self.post)
        self.expire_interaction_backoff()
        self.assertFalse(
            await self.intent.wants_interaction(self.owner, "like", self.post)
        )
        self.plugin.call_llm.assert_awaited_once()

    async def test_legacy_act_stays_protected_on_upgrade(self):
        key = self.intent.interaction_key("like", self.post)
        self.plugin.db.state[self.intent._STATE] = {key: {"decision": "act"}}
        self.assertFalse(
            await self.intent.wants_interaction(self.owner, "like", self.post)
        )
        self.plugin.call_llm.assert_not_awaited()

    async def test_reply_generation_failure_recovers_before_platform_submission(self):
        discuss = importlib.import_module(
            fixtures.TASKS_MODULE_NAME + ".interact.executors.discuss"
        )
        self.plugin.call_llm.return_value = '{"decision":"act"}'
        self.owner._generate_qzone_auto_reply = AsyncMock(
            side_effect=TypeError("生成失败")
        )
        self.owner._qzone_send_auto_reply_result = AsyncMock()
        comment = types.SimpleNamespace(tid="reply-1", content="做得怎么样", uin=20002)
        result = {"skipped": 0, "failed": 0, "generation_failed": 0}
        for _ in range(2):
            await discuss._execute_qzone_auto_comment_reply(
                self.owner,
                self.post,
                comment,
                "reply-1",
                {},
                {},
                result,
                self_uin=10001,
            )
        self.owner._generate_qzone_auto_reply.assert_awaited_once()
        self.owner._qzone_send_auto_reply_result.assert_not_awaited()
        self.expire_interaction_backoff()
        self.owner._generate_qzone_auto_reply.side_effect = None
        self.owner._generate_qzone_auto_reply.return_value = "味道还不错"
        await discuss._execute_qzone_auto_comment_reply(
            self.owner, self.post, comment, "reply-1", {}, {}, result, self_uin=10001
        )
        self.assertEqual(self.owner._generate_qzone_auto_reply.await_count, 2)
        self.owner._qzone_send_auto_reply_result.assert_awaited_once()

    async def test_space_new_reply_has_its_own_identity(self):
        self.plugin.call_llm.return_value = '{"decision":"act"}'
        for tid in ("reply-1", "reply-2"):
            comment = types.SimpleNamespace(tid=tid, content="谢谢", uin=20002)
            self.assertTrue(
                await self.intent.wants_interaction(
                    self.owner, "reply", self.post, comment
                )
            )

    async def test_space_reply_decision_reads_actual_comment_and_parent_models(self):
        models = importlib.import_module(fixtures.CORE_PACKAGE_NAME + ".space.models")
        comment = models.QzoneComment(
            tid="child-1", uin=20002, nickname="朋友", content="你后来有去吗"
        )
        parent = models.QzoneComment(
            tid="parent-1", uin=10001, nickname="自己", content="改天想沿着海边走走"
        )
        await self.intent.wants_interaction(
            self.owner, "reply", self.post, comment, parent
        )
        prompt = self.plugin.call_llm.await_args.kwargs["prompt"]
        self.assertIn("你后来有去吗", prompt)
        self.assertIn("改天想沿着海边走走", prompt)
        self.assertIn('"comment_author_id": "20002"', prompt)
        self.assertIn('"parent_id": "parent-1"', prompt)

    async def test_space_malformed_output_fails_closed_and_backs_off(self):
        self.plugin.call_llm.return_value = "模型出错"
        for _ in range(2):
            self.assertFalse(
                await self.intent.wants_interaction(self.owner, "reply", self.post)
            )
        self.plugin.call_llm.assert_awaited_once()

    async def test_space_wait_is_not_an_action_or_a_scheduled_reply(self):
        self.plugin.call_llm.return_value = (
            '{"decision":"wait","reconsider_after_minutes":90}'
        )
        for _ in range(2):
            self.assertFalse(
                await self.intent.wants_interaction(self.owner, "comment", self.post)
            )
        self.plugin.call_llm.assert_awaited_once()
        self.assertEqual(self.plugin.scheduler.jobs, [])

    async def test_space_sleep_during_decision_prevents_action(self):
        async def decide(**kwargs):
            self.data["subject"]["sleep_depth"] = "deep_sleep"
            return '{"decision":"act"}'

        self.plugin.call_llm.side_effect = decide
        self.assertFalse(
            await self.intent.wants_interaction(self.owner, "comment", self.post)
        )

        self.data["subject"]["sleep_depth"] = "awake"
        self.plugin.call_llm.side_effect = None
        self.plugin.call_llm.return_value = '{"decision":"act"}'
        self.expire_interaction_backoff()
        self.assertTrue(
            await self.intent.wants_interaction(self.owner, "comment", self.post)
        )

    async def test_space_mode_change_during_decision_prevents_action(self):
        async def decide(**kwargs):
            self.plugin.qzone_conf["qzone_trigger_mode"] = "cron"
            return '{"decision":"act"}'

        self.plugin.call_llm.side_effect = decide
        self.assertFalse(
            await self.intent.wants_interaction(self.owner, "comment", self.post)
        )

    async def test_observers_do_not_create_calendar_publication_times(self):
        self.manager.schedule.auto.setup_qzone_auto_interaction_cron()
        jobs = {job["kwargs"]["id"]: job for job in self.plugin.scheduler.jobs}
        self.assertEqual(jobs["life_qzone_observer"]["trigger"], "interval")
        self.assertNotIn("qzone_auto_interaction", jobs)

    async def test_processed_decisions_survive_actual_database_reopen(self):
        db_module = importlib.import_module(fixtures.CORE_PACKAGE_NAME + ".db")
        with tempfile.TemporaryDirectory() as folder:
            first = db_module.DatabaseManager(Path(folder))
            # 真实 SQLite，而非进程内缓存。
            from dataclasses import replace

            self.manager.schedule.runtime = replace(
                self.manager.schedule.runtime, db=first
            )
            self.owner.runtime = replace(self.owner.runtime, db=first)
            self.plugin.db = first
            try:
                await self.consider()
                await self.intent.wants_interaction(self.owner, "comment", self.post)
            finally:
                await first.close()
            second = db_module.DatabaseManager(Path(folder))
            self.plugin.db = second
            self.manager.schedule.runtime = replace(
                self.manager.schedule.runtime, db=second
            )
            self.owner.runtime = replace(self.owner.runtime, db=second)
            try:
                await self.consider()
                await self.intent.wants_interaction(self.owner, "comment", self.post)
                self.assertEqual(self.plugin.call_llm.await_count, 2)
            finally:
                await second.close()

    async def test_preparation_and_unknown_submission_survive_sqlite_reopen(self):
        from dataclasses import replace

        db_module = importlib.import_module(fixtures.CORE_PACKAGE_NAME + ".db")

        def use_database(database):
            self.plugin.db = database
            self.manager.schedule.runtime = replace(
                self.manager.schedule.runtime, db=database
            )
            self.owner.runtime = replace(self.owner.runtime, db=database)

        async def expire(database):
            states = await database.get_share_state(self.living_module._STATE, {})
            states[self.target].update(review_at=0, error_until=0)
            await database.update_share_state(self.living_module._STATE, states)
            intents = await database.get_qzone_state(self.intent._STATE, {})
            for state in intents.values():
                state["review_at"] = 0
            await database.merge_cache_entries(
                "qzone", self.intent._STATE, intents, max_items=512
            )

        with tempfile.TemporaryDirectory() as folder:
            first = db_module.DatabaseManager(Path(folder))
            use_database(first)
            try:
                self.plugin.call_llm.return_value = self.share_decision()
                self.manager.share.execute_share.return_value = False
                await self.consider()
                self.plugin.call_llm.return_value = '{"decision":"act"}'
                self.assertTrue(
                    await self.intent.wants_interaction(
                        self.owner, "comment", self.post
                    )
                )
            finally:
                await first.close()

            second = db_module.DatabaseManager(Path(folder))
            use_database(second)
            try:
                await expire(second)

                async def unknown(**kwargs):
                    await self.submission.mark_submission()
                    raise TimeoutError("回执未知")

                self.manager.share.execute_share.side_effect = unknown
                self.plugin.call_llm.return_value = self.share_decision()
                with self.assertRaises(TimeoutError):
                    await self.consider()
                self.plugin.call_llm.return_value = '{"decision":"act"}'
                self.assertTrue(
                    await self.intent.wants_interaction(
                        self.owner, "comment", self.post
                    )
                )
                await self.intent.mark_interaction_submission(
                    self.owner, "comment", self.post
                )
            finally:
                await second.close()

            third = db_module.DatabaseManager(Path(folder))
            use_database(third)
            try:
                await expire(third)
                await self.consider()
                self.assertFalse(
                    await self.intent.wants_interaction(
                        self.owner, "comment", self.post
                    )
                )
                self.assertEqual(self.manager.share.execute_share.await_count, 2)
                self.assertEqual(self.plugin.call_llm.await_count, 4)
            finally:
                await third.close()


if __name__ == "__main__":
    unittest.main()

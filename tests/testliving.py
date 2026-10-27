"""生活分享与空间意愿的端到端调度边界；所有模型及发送调用均为替身。"""

import copy
import importlib
import json
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

from . import testfailure as fixtures


class LivingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.module = fixtures._load_tasks_module()
        prefix = fixtures.TASKS_MODULE_NAME
        self.material = importlib.import_module(prefix + ".opportunity")
        self.intent = importlib.import_module(prefix + ".interact.intent")
        self.living_module = importlib.import_module(prefix + ".scheduler.living")
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

    async def test_failure_consumes_attempt_without_repeating_material(self):
        self.plugin.call_llm.return_value = self.share_decision()
        self.manager.share.execute_share.side_effect = RuntimeError("结果未确认")
        with self.assertRaises(RuntimeError):
            await self.consider()
        await self.consider()
        self.assertEqual(self.state()["attempts"], 1)
        self.manager.share.execute_share.assert_awaited_once()
        self.assertEqual(self.material.opportunity_prompt(self.target), "")

    async def test_daily_limit_is_a_ceiling_and_not_a_fill_target(self):
        self.plugin.basic_conf["smart_schedule_max_count"] = 1
        self.plugin.call_llm.return_value = self.share_decision()
        await self.consider()
        self.data["current_facts"]["current_action"]["action_id"] = "new-activity"
        await self.consider()
        self.plugin.call_llm.assert_awaited_once()
        self.manager.share.execute_share.assert_awaited_once()

    async def test_shared_contact_pressure_blocks_model_and_share(self):
        self.data["contact_rhythm"] = {"ready": False, "retry_after": 300, "willingness": 0.85}
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
        await self.plugin.db.update_share_state(self.living_module._STATE, {
            self.target: {"date": datetime.now(self.material.SHANGHAI).date().isoformat(), "attempts": 6}
        })
        self.data["contact_rhythm"] = {"willingness": 0.85, "ready": True}
        self.plugin.call_llm.return_value = self.share_decision()
        await self.consider()
        self.manager.share.execute_share.assert_awaited_once()
        self.assertEqual(self.state()["attempts"], 7)
        self.assertIn('"willingness": 0.85', self.plugin.call_llm.await_args.kwargs["prompt"])

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
        self.assertFalse(
            await self.intent.wants_interaction(self.owner, "comment", self.post)
        )
        self.plugin.call_llm.assert_awaited_once()

    async def test_space_act_is_consumed_before_submission(self):
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


if __name__ == "__main__":
    unittest.main()

"""复现密集发布、真实发送边界与重启续接；所有外发均为替身。"""

import asyncio
import importlib
import json
import time
import tempfile
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

from tests import testfailure as fixtures
from tests import testliving as living_fixtures
from tests import testreconsider as review_fixtures


class PacingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        fixtures._load_tasks_module()
        self.module = importlib.import_module(fixtures.TASKS_MODULE_NAME + ".pacing")
        self.material = importlib.import_module(
            fixtures.TASKS_MODULE_NAME + ".opportunity"
        )
        self.continuation = importlib.import_module(
            fixtures.TASKS_MODULE_NAME + ".continuation"
        )
        self.plugin = fixtures._Plugin()
        self.plugin.daily_life_bridge = types.SimpleNamespace(
            get_share_context=AsyncMock(
                return_value={"contact_rhythm": {"last_received_at": 0}}
            ),
            coordinate_contact=AsyncMock(
                return_value={"allowed": True, "snapshot": "current"}
            ),
        )
        self.service = self.continuation.ShareContinuationService(self.plugin)
        self.pacing = self.service.pacing
        self.target = fixtures.USER_TARGET_1
        self.public = "qzone_broadcast"
        self.now = float(int(time.time()))

    def job(
        self,
        target=None,
        *,
        source="life_driven",
        identity="original",
        episode="episode",
    ):
        return {
            "id": identity,
            "kind": "chat",
            "status": "ready",
            "service": self.service,
            "params": {"uid": target or self.target, "history_source": source},
            "pacing_episodes": [episode] if episode else [],
        }

    async def record(self, target=None, *, age=0, **kwargs):
        target = target or self.target
        job = self.job(target, **kwargs)
        await self.pacing.record(target, job, now=self.now - age)
        return job

    async def test_yesterday_public_bursts_and_new_material_cannot_bypass_interval(
        self,
    ):
        for seconds in (174, 312, 25 * 60, 35 * 60, 89 * 60):
            await self.record(self.public, age=seconds)
            gate = await self.pacing.check(
                self.public, selected=["new-episode"], now=self.now
            )
            self.assertFalse(gate["ready"])
        await self.record(self.public, age=90 * 60)
        self.assertTrue((await self.pacing.check(self.public, now=self.now))["ready"])

    async def test_private_unanswered_shares_slow_down_then_real_reply_restores_base(
        self,
    ):
        await self.record(age=45 * 60)
        self.assertFalse((await self.pacing.check(self.target, now=self.now))["ready"])
        replied = {"contact_rhythm": {"last_received_at": self.now - 60}}
        self.assertTrue(
            (await self.pacing.check(self.target, data=replied, now=self.now))["ready"]
        )
        await self.record(age=10 * 60)
        self.assertFalse(
            (await self.pacing.check(self.target, data=replied, now=self.now))["ready"]
        )

    async def test_two_unanswered_shares_need_six_hours_not_twenty_minutes(self):
        await self.record(age=4 * 3600, identity="first", episode=None)
        await self.record(age=2 * 3600, identity="second", episode=None)
        gate = await self.pacing.check(self.target, now=self.now)
        self.assertEqual(gate["retry_after"], 4 * 3600)
        later = await self.pacing.check(self.target, now=self.now + 4 * 3600)
        self.assertTrue(later["ready"])

    async def test_other_private_target_does_not_inherit_silence_or_episode(self):
        await self.record(age=60)
        gate = await self.pacing.check(
            "qq:FriendMessage:another-test-user", selected=["episode"], now=self.now
        )
        self.assertTrue(gate["ready"])

    async def test_cross_channel_suppresses_same_episode_only_and_saves_no_private_content(
        self,
    ):
        await self.record(age=60)
        self.assertFalse(
            (await self.pacing.check(self.public, selected=["episode"], now=self.now))[
                "ready"
            ]
        )
        self.assertTrue(
            (await self.pacing.check(self.public, selected=["another"], now=self.now))[
                "ready"
            ]
        )
        kept = await self.pacing.filter_materials(
            self.public,
            [{"id": "new-version", "episode_id": "episode"}, {"id": "fresh"}],
            now=self.now,
        )
        self.assertEqual(kept, [{"id": "fresh"}])
        self.assertTrue(
            (
                await self.pacing.check(
                    self.public, selected=["episode"], now=self.now + 5400
                )
            )["ready"]
        )
        self.plugin.daily_life_bridge.get_share_context.assert_not_awaited()
        encoded = json.dumps(self.plugin.db.state[self.module.STATE_KEY])
        self.assertNotIn(self.target, encoded)
        self.assertNotIn("content", encoded)
        self.assertNotIn("relationships", encoded)

    async def test_public_then_private_same_experience_also_waits(self):
        await self.record(self.public, age=60)
        self.assertFalse(
            (await self.pacing.check(self.target, selected=["episode"], now=self.now))[
                "ready"
            ]
        )

    async def test_event_progress_uses_stable_episode_and_still_keeps_distinct_material_ids(
        self,
    ):
        now = datetime.now(self.material.SHANGHAI)
        row = {
            "event_id": "work-1",
            "title": "一道新菜",
            "state": "active",
            "detail": "准备食材",
            "at": now.isoformat(),
        }
        data = {
            "current_facts": {"valid": True, "date": now.date().isoformat()},
            "continuity": {"activities": [row]},
        }
        first = self.material.share_material(data, now)[0]
        row.update(detail="装盘完成", state="completed")
        second = self.material.share_material(data, now)[0]
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["episode_id"], second["episode_id"])
        await self.record(self.public, age=100 * 60, episode=first["episode_id"])
        self.assertEqual(
            await self.pacing.filter_materials(self.public, [second], now=self.now), []
        )
        self.assertEqual(
            await self.pacing.filter_materials(
                self.public, [second], now=self.now + 80 * 60
            ),
            [second],
        )

    async def test_running_to_completed_action_keeps_episode(self):
        now = datetime.now(self.material.SHANGHAI)
        data = {
            "current_facts": {
                "valid": True,
                "date": now.date().isoformat(),
                "current_action": {
                    "status": "running",
                    "observation_state": "observed",
                    "action_id": "a",
                    "activity": "做饭",
                    "observed_at": now.isoformat(),
                },
            },
            "timeline": [
                {
                    "execution_state": "completed",
                    "execution_evidence": "已完成",
                    "activity": "做饭",
                    "time": "12:00",
                    "execution_updated_at": now.isoformat(),
                }
            ],
        }
        rows = self.material.share_material(data, now)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["episode_id"], rows[1]["episode_id"])
        merged = await self.pacing.filter_materials(self.public, rows)
        self.assertEqual(merged, [rows[1]])

    async def test_upgrade_reads_successful_history_and_ignores_failure(self):
        history = [
            {
                "timestamp": datetime.fromtimestamp(self.now - 174).isoformat(),
                "source_type": "life_driven",
                "success": True,
            }
        ]
        self.plugin.db.get_recent_history_by_target = AsyncMock(return_value=history)
        self.assertFalse((await self.pacing.check(self.public, now=self.now))["ready"])
        history[0]["success"] = False
        self.assertTrue((await self.pacing.check(self.public, now=self.now))["ready"])

    async def test_history_and_submission_do_not_count_same_share_twice(self):
        await self.record(age=100 * 60)
        self.plugin.db.get_recent_history_by_target = AsyncMock(
            return_value=[
                {
                    "timestamp": datetime.fromtimestamp(self.now - 99 * 60).isoformat(),
                    "source_type": "life_driven",
                }
            ]
        )
        gate = await self.pacing.check(self.target, now=self.now)
        self.assertEqual(gate["retry_after"], 21 * 60)

    async def test_restart_retains_pacing_and_does_not_reset_on_day_boundary(self):
        await self.record(self.public, age=60)
        self.plugin.db.state = json.loads(json.dumps(self.plugin.db.state))
        reloaded = self.module.SharePacingService(self.plugin)
        self.assertFalse((await reloaded.check(self.public, now=self.now))["ready"])
        self.assertFalse(
            (await reloaded.check(self.public, now=self.now + 3600))["ready"]
        )

    async def test_sqlite_close_and_reopen_retains_real_submission_record(self):
        database = importlib.import_module(
            fixtures.CORE_PACKAGE_NAME + ".db"
        ).DatabaseManager
        with tempfile.TemporaryDirectory() as directory:
            self.plugin.db = database(Path(directory))
            try:
                await self.record(self.public, age=60)
            finally:
                await self.plugin.db.close()
            self.plugin.db = database(Path(directory))
            try:
                reloaded = self.module.SharePacingService(self.plugin)
                self.assertFalse(
                    (await reloaded.check(self.public, now=self.now))["ready"]
                )
                self.assertEqual(
                    await reloaded.filter_materials(
                        self.target,
                        [{"id": "new", "episode_id": "episode"}],
                        now=self.now,
                    ),
                    [],
                )
            finally:
                await self.plugin.db.close()

    async def test_manual_command_explicit_schedule_and_briefing_are_exempt(self):
        await self.record(age=1)
        for source in ("command", "manual", "scheduled", "", None):
            self.assertTrue(
                (await self.pacing.check(self.target, source=source, now=self.now))[
                    "ready"
                ]
            )
        self.assertFalse(
            (
                await self.pacing.check(
                    self.target, source="smart_schedule", now=self.now
                )
            )["ready"]
        )

    async def test_final_submission_gate_and_multi_part_original(self):
        first = self.job(episode=None)
        token = self.continuation.current_share_job.set(first)
        try:
            await self.service.mark_submitting()
            await self.service.mark_submitting()
        finally:
            self.continuation.current_share_job.reset(token)
        self.assertEqual(first["status"], "submitting")
        second = self.job(identity="second", episode=None)
        token = self.continuation.current_share_job.set(second)
        try:
            with self.assertRaises(self.continuation.ShareContactPending):
                await self.service.mark_submitting()
        finally:
            self.continuation.current_share_job.reset(token)
        self.assertTrue(second["needs_review"])
        self.assertNotIn("submitted_at", second)

    async def test_concurrent_first_submissions_cannot_both_pass(self):
        async def submit(identity):
            job = self.job(self.public, identity=identity, episode=None)
            token = self.continuation.current_share_job.set(job)
            try:
                await self.service.mark_submitting()
                return True
            except self.continuation.ShareContactPending:
                return False
            finally:
                self.continuation.current_share_job.reset(token)

        self.assertEqual(
            sorted(await asyncio.gather(submit("a"), submit("b"))), [False, True]
        )

    async def test_invalid_settings_fall_back_and_are_bounded(self):
        for value, expected in (
            (None, 45),
            ("bad", 45),
            (True, 45),
            (-1, 15),
            (999, 360),
            (60, 60),
        ):
            self.plugin.basic_conf["autonomous_share_interval_minutes"] = value
            self.assertEqual(self.pacing.interval(self.target), expected * 60)


class PacingIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_wait_decision_survives_new_material_without_calling_model_again(
        self,
    ):
        case = living_fixtures.LivingTests()
        await case.asyncSetUp()
        case.plugin.call_llm.return_value = (
            '{"decision":"wait","reconsider_after_minutes":45}'
        )
        await case.consider()
        case.data["current_facts"]["current_action"]["action_id"] = "another-action"
        await case.consider()
        case.plugin.call_llm.assert_awaited_once()
        case.manager.share.execute_share.assert_not_awaited()

    async def test_scheduler_gate_runs_before_model_and_media_generation(self):
        case = living_fixtures.LivingTests()
        await case.asyncSetUp()
        continuation = importlib.import_module(
            fixtures.TASKS_MODULE_NAME + ".continuation"
        )
        service = continuation.ShareContinuationService(case.plugin)
        case.plugin.share_continuations = service
        await service.pacing.record(
            case.target, {"id": "previous", "params": {"history_source": "life_driven"}}
        )
        await case.consider()
        case.plugin.call_llm.assert_not_awaited()
        case.manager.share.execute_share.assert_not_awaited()

    def review_case(self):
        case = review_fixtures.ReconsiderationTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.plugin.basic_conf.update(
            trigger_mode="life_driven", smart_schedule_quiet_hours=[]
        )
        return case

    async def test_waiting_asset_survives_restart_without_repeated_review_or_external_send(
        self,
    ):
        case = self.review_case()
        job = await case.job()
        job["params"]["history_source"] = "life_driven"
        await case.service.save(job)
        await case.service.pacing.record(
            fixtures.USER_TARGET_1,
            {"id": "recent", "params": {"history_source": "life_driven"}},
        )
        service = case.case.service_class(case.plugin)
        case.plugin.share_continuations = service
        await service.recover_once()
        await service.recover_once()
        stored = case.case.journal()
        self.assertEqual(stored["status"], "waiting_review")
        self.assertEqual(stored["prepared_media"], job["prepared_media"])
        self.assertNotIn("review_attempts", stored)
        self.assertEqual(case.case.sent, [])
        case.plugin.call_llm.assert_not_awaited()

    async def test_resumption_after_reply_rechecks_and_sends_original_once(self):
        case = self.review_case()
        job = await case.job()
        job["params"]["history_source"] = "life_driven"
        await case.service.save(job)
        now = time.time()
        await case.service.pacing.record(
            fixtures.USER_TARGET_1,
            {"id": "recent", "params": {"history_source": "life_driven"}},
            now=now - 3600,
        )
        await case.service.recover_once()
        self.assertEqual(case.case.sent, [])
        case.context.return_value["contact_rhythm"] = {"last_received_at": now - 30}
        case.case.journal()["review_after"] = 0
        await case.service.recover_once()
        self.assertEqual(case.case.journal()["status"], "completed")
        self.assertEqual(len(case.case.sent), 3)
        await case.service.recover_once()
        self.assertEqual(len(case.case.sent), 3)
        case.case.life.generate_share_image_task.assert_not_called()

    async def test_first_send_deferral_preserves_media_and_episode_identity(self):
        case = self.review_case()
        case.plugin.image_service.generate_image = AsyncMock(
            return_value=case.assets[0]
        )
        await case.service.pacing.record(
            fixtures.USER_TARGET_1,
            {"id": "recent", "params": {"history_source": "life_driven"}},
        )
        material = importlib.import_module(fixtures.TASKS_MODULE_NAME + ".opportunity")
        token = material.current_opportunity.set(
            {
                "target": fixtures.USER_TARGET_1,
                "materials": [{"id": "new-version", "episode_id": "stable"}],
            }
        )
        params = case.case.params(case.case.start_progress())
        params["history_source"] = "life_driven"
        try:
            self.assertFalse(
                await case.case.manager.share.send_prepared_chat_share(**params)
            )
        finally:
            material.current_opportunity.reset(token)
        job = next(iter(case.plugin.db.state["share_media_continuations"].values()))
        self.assertEqual(job["status"], "waiting_contact")
        self.assertTrue(job["needs_review"])
        self.assertEqual(job["pacing_episodes"], ["stable"])
        self.assertEqual(job["prepared_media"][0], case.assets[0])
        self.assertEqual(case.case.sent, [])


if __name__ == "__main__":
    unittest.main()

"""成品重评覆盖真实续接边界、媒体复用、上下文竞争和公开隔离。"""

import asyncio
import copy
import importlib
import json
import tempfile
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from tests import testmediarecovery as recovery
from tests import testfailure as fixtures


class ReconsiderationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.case = recovery.MediaRecoveryTests()
        self.case.setUp()
        self.case.enable_scheduled()
        self.plugin = self.case.plugin
        self.plugin.qzone_conf.update(enable_qzone=True, qzone_trigger_mode="fixed_time")
        self.case.manager.share.resolve_execute_share_targets = lambda *a, **kw: [fixtures.USER_TARGET_1, fixtures.GROUP_TARGET_1]
        self.service = self.case.service
        self.review = self.service.reconsider
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.assets = [str(Path(self.directory.name) / name) for name in ("original.png", "original.mp4", "original.wav")]
        for path in self.assets:
            Path(path).write_bytes(b"original-asset")
        self.coordinate = AsyncMock(return_value={"allowed": True, "snapshot": "current-facts"})
        self.plugin.daily_life_bridge.coordinate_contact = self.coordinate
        self.context = AsyncMock(return_value={"current_facts": {"valid": True}, "subject": {}})
        self.plugin.daily_life_bridge.get_share_context = self.context
        self.plugin.ctx_service = types.SimpleNamespace(
            get_chat_share_context=AsyncMock(return_value={"life_context": "现在已坐下吃饭", "post_context": "最新生活"}),
            get_qzone_share_context=AsyncMock(return_value={"life_context": "公开生活", "post_context": "公开事实"}),
            get_history_data=AsyncMock(return_value={"messages": []}),
            format_structured_history_context=Mock(return_value="最近双方的原话"),
        )
        self.plugin.content_service.get_persona_info = AsyncMock(return_value={"prompt": "自然积极地交流"})
        self.plugin.db.get_recent_history_by_target = AsyncMock(return_value=[])
        self.plugin.call_llm = AsyncMock(return_value=json.dumps({"decision": "keep", "media": "original"}))

    async def job(self):
        job = await self.case.job()
        job["params"]["history_source"] = "scheduled"
        job["params"]["content"] = "等你上来吃饭"
        job.update(
            status="waiting_review", needs_review=True, review_after=0,
            contact_snapshot="old-facts", delivery_prepared=True,
            prepared_media=[self.assets[0], self.assets[0], self.assets[1], self.assets[2], "桌上的饭菜"],
        )
        await self.service.save(job)
        return job

    async def test_keep_recovers_all_original_media_once_after_reload(self):
        job = await self.job()
        service = self.case.service_class(self.plugin)
        self.plugin.share_continuations = service
        await service.recover_once()
        sent = list(self.case.sent)
        self.assertEqual(self.case.journal()["status"], "completed")
        self.assertEqual(len(sent), 3)
        self.assertEqual(self.case.journal()["prepared_media"], job["prepared_media"])
        await service.recover_once()
        self.assertEqual(self.case.sent, sent)
        self.plugin.call_llm.assert_awaited_once()
        self.case.life.generate_share_image_task.assert_not_called()
        self.case.life.generate_share_video_task.assert_not_called()

    async def test_first_send_stale_check_preserves_completed_media_for_review(self):
        module = importlib.import_module(f"{fixtures.CORE_PACKAGE_NAME}.integrations.contact")
        self.plugin.image_service.generate_image = AsyncMock(return_value=self.assets[0])
        self.coordinate.return_value = {"allowed": False, "stale": True}
        params = self.case.params(self.case.start_progress())
        params["history_source"] = "scheduled"
        token = module.current_contact.set({"owner": "initial", "snapshot": "old"})
        try:
            self.assertFalse(await self.case.manager.share.send_prepared_chat_share(**params))
        finally:
            module.current_contact.reset(token)
        jobs = self.plugin.db.state["share_media_continuations"]
        self.assertEqual(len(jobs), 1)
        job = next(iter(jobs.values()))
        self.assertEqual(job["status"], "waiting_review")
        self.assertEqual(job["prepared_media"][0], self.assets[0])
        self.assertTrue(job["delivery_prepared"])
        self.assertEqual(self.case.sent, [])

    async def test_reframe_reuses_image_and_records_new_content_without_old_voice(self):
        job = await self.job()
        original = copy.deepcopy(job["prepared_media"])
        self.plugin.call_llm.return_value = json.dumps({"decision": "reframe", "content": "刚才那碗汤的照片 现在给你看看", "media": "image"})
        await self.service.recover_once()
        result = self.case.journal()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["prepared_media"], [self.assets[0], self.assets[0], None, None, "桌上的饭菜"])
        self.assertEqual(result["original_delivery"]["prepared_media"], original)
        self.assertEqual(result["original_delivery"]["params"]["content"], "等你上来吃饭")
        self.assertEqual(result["params"]["content"], "刚才那碗汤的照片 现在给你看看")
        self.assertEqual(self.plugin.db.history[-1][1]["content"], result["params"]["content"])
        self.assertEqual(len(self.case.sent), 2)
        self.assertTrue(all(Path(p).exists() for p in self.assets))

    async def test_past_video_requires_explicit_confirmation_and_never_reuses_voice(self):
        for context, expected in (("none", None), ("past_recording", self.assets[1])):
            job = await self.job()
            self.plugin.call_llm.return_value = json.dumps({"decision": "reframe", "content": "刚才拍的那一小段", "media": "original", "video_context": context})
            self.assertTrue(await self.review.review(job))
            self.assertEqual(job["prepared_media"][2], expected)
            self.assertIsNone(job["prepared_media"][3])

    async def test_review_changed_again_waits_with_original_params_and_media(self):
        job = await self.job()
        params, media = copy.deepcopy(job["params"]), list(job["prepared_media"])
        self.coordinate.side_effect = [{"allowed": True, "snapshot": "new"}, {"allowed": False, "stale": True}]
        self.assertFalse(await self.review.review(job))
        self.assertEqual(job["status"], "waiting_review")
        self.assertEqual(job["params"], params)
        self.assertEqual(job["prepared_media"], media)
        self.assertEqual(job["contact_snapshot"], "old-facts")
        self.assertEqual(self.case.sent, [])

    async def test_disable_during_model_review_cannot_submit(self):
        await self.job()
        async def disable(**kwargs):
            self.plugin.config["enable_auto_share"] = False
            return '{"decision":"keep","media":"original"}'
        self.plugin.call_llm.side_effect = disable
        await self.service.recover_once()
        self.assertEqual(self.case.journal()["status"], "cancelled")
        self.assertEqual(self.case.sent, [])

    async def test_change_at_final_submit_defers_without_losing_reframed_asset(self):
        await self.job()
        async def gate(*args, **kwargs):
            if kwargs.get("action") == "release":
                return {"allowed": True}
            if self.coordinate.await_count >= 3:
                return {"allowed": False, "stale": True}
            return {"allowed": True, "snapshot": "current-facts"}
        self.coordinate.side_effect = gate
        await self.service.recover_once()
        result = self.case.journal()
        self.assertEqual(result["status"], "waiting_review")
        self.assertNotIn("submitted_at", result)
        self.assertEqual(self.case.sent, [])

    async def test_sleep_busy_or_invalid_facts_do_not_consume_model_budget(self):
        for state in (
            {"current_facts": {"valid": False}},
            {"current_facts": {"valid": True}, "subject": {"sleep_depth": "deep_sleep"}},
            {"current_facts": {"valid": True}, "subject": {"can_interrupt_default": False}},
            {"current_facts": {"valid": True}, "contact_rhythm": {"ready": False}},
        ):
            job = await self.job()
            self.context.return_value = state
            self.assertFalse(await self.review.review(job))
            self.assertEqual(job["status"], "waiting_review")
            self.assertNotIn("review_attempts", job)
        self.plugin.call_llm.assert_not_called()

    async def test_missing_snapshot_or_contact_outage_waits_without_llm(self):
        for gate in ({"allowed": True}, {"allowed": False, "retryable": True}):
            job = await self.job()
            self.coordinate.return_value = gate
            self.assertFalse(await self.review.review(job))
            self.assertEqual(job["status"], "waiting_review")
        self.plugin.call_llm.assert_not_called()

    async def test_wait_backoff_survives_reload_and_does_not_poll_model(self):
        await self.job()
        self.plugin.call_llm.return_value = json.dumps({"decision": "wait", "reconsider_after_minutes": 5})
        await self.service.recover_once()
        result = self.case.journal()
        self.assertGreater(result["review_after"], datetime.now().timestamp() + 290)
        await self.case.service_class(self.plugin).recover_once()
        self.plugin.call_llm.assert_awaited_once()
        self.assertTrue(await self.service.has_pending_share(fixtures.USER_TARGET_1))

    async def test_model_failure_or_invalid_response_preserves_original_and_backs_off(self):
        for raw in ("not json", '[]', '{"decision":"reframe","content":"","media":"original"}', '{"decision":"keep","media":"new-file"}'):
            job = await self.job()
            original = list(job["prepared_media"])
            self.plugin.call_llm.return_value = raw
            self.assertFalse(await self.review.review(job))
            self.assertEqual(job["status"], "waiting_review")
            self.assertEqual(job["prepared_media"], original)
            self.assertGreater(job["review_after"], datetime.now().timestamp() + 290)
        job = await self.job()
        self.plugin.call_llm.side_effect = RuntimeError("provider unavailable")
        self.assertFalse(await self.review.review(job))
        self.assertEqual(job["status"], "waiting_review")

    async def test_explicit_archive_releases_target_without_sending(self):
        await self.job()
        self.plugin.call_llm.return_value = '{"decision":"archive"}'
        await self.service.recover_once()
        self.assertEqual(self.case.journal()["status"], "cancelled")
        self.assertFalse(await self.service.has_pending_share(fixtures.USER_TARGET_1))
        self.assertEqual(self.case.sent, [])

    async def test_review_limit_and_ttl_release_target(self):
        job = await self.job()
        job["review_attempts"] = 6
        await self.service.save(job)
        await self.service.recover_once()
        self.assertEqual(self.case.journal()["status"], "cancelled")
        job = await self.job()
        job["created_at"] -= 7201
        await self.service.save(job)
        await self.service.recover_once()
        self.assertEqual(self.case.journal()["status"], "cancelled")
        self.plugin.call_llm.assert_not_called()

    async def test_disabled_removed_target_and_quiet_hours_still_apply(self):
        job = await self.job()
        self.plugin.config["enable_auto_share"] = False
        await self.service.recover_once()
        self.assertEqual(self.case.journal()["status"], "cancelled")
        self.plugin.config["enable_auto_share"] = True
        job = await self.job()
        self.case.manager.share.resolve_execute_share_targets = lambda *a, **kw: []
        await self.service.recover_once()
        self.assertEqual(self.case.journal()["status"], "cancelled")
        self.case.manager.share.resolve_execute_share_targets = lambda *a, **kw: [fixtures.USER_TARGET_1]
        self.plugin.basic_conf["trigger_mode"] = "llm_smart"
        self.case.manager.schedule.smart.is_quiet_time = lambda *a: True
        job = await self.job()
        await self.service.recover_once()
        self.assertEqual(self.case.journal()["status"], "waiting_review")
        self.plugin.call_llm.assert_not_called()

    async def test_submitted_and_partial_completed_jobs_are_never_reviewed_or_resent(self):
        for status in ("submitting", "completed"):
            job = await self.job()
            job.update(status=status, submitted_at=datetime.now().timestamp())
            await self.service.save(job)
            await self.service.recover_once()
            await self.service.resume(job)
            self.assertEqual(self.case.journal()["status"], status)
        self.plugin.call_llm.assert_not_called()
        self.assertEqual(self.case.sent, [])

    async def test_public_review_never_reads_private_history_or_context(self):
        job = await self.job()
        job["kind"] = "qzone"
        job["params"].pop("uid")
        self.assertTrue(await self.review.review(job))
        ctx = self.plugin.ctx_service
        ctx.get_history_data.assert_not_called()
        ctx.get_chat_share_context.assert_not_called()
        ctx.get_qzone_share_context.assert_awaited_once()
        self.plugin.db.get_recent_history_by_target.assert_awaited_once_with("qzone_broadcast", limit=4)
        payload = json.loads(self.plugin.call_llm.await_args.kwargs["prompt"])
        self.assertEqual(payload["conversation"], "")
        self.assertEqual(payload["current_context"], "公开事实")

    async def test_group_review_uses_only_original_group_context_and_history(self):
        job = await self.job()
        job["params"]["uid"] = fixtures.GROUP_TARGET_1
        self.assertTrue(await self.review.review(job))
        self.plugin.ctx_service.get_history_data.assert_awaited_once_with(fixtures.GROUP_TARGET_1)
        self.plugin.ctx_service.get_chat_share_context.assert_awaited_once_with(fixtures.GROUP_TARGET_1)

    async def test_only_latest_recent_exact_stale_cancellation_migrates(self):
        module = importlib.import_module(f"{fixtures.CORE_PACKAGE_NAME}.tasks.reconsider")
        job = await self.job()
        job.update(status="cancelled", reason=module.STALE_REASON)
        older = copy.copy(job)
        older.update(id="older", created_at=job["created_at"] - 10)
        expired = copy.copy(job)
        expired.update(id="expired", created_at=job["created_at"] - 8000)
        cancelled = copy.copy(job)
        cancelled.update(id="explicit", reason="用户取消")
        jobs = {j["id"]: j for j in (job, older, expired, cancelled)}
        await self.review.migrate(jobs)
        self.assertEqual(job["status"], "waiting_review")
        self.assertEqual([j["status"] for j in (older, expired, cancelled)], ["cancelled"] * 3)
        self.assertEqual(self.case.sent, [])
        job["status"] = "completed"
        await self.review.migrate(jobs)
        self.assertEqual(older["status"], "cancelled")

    async def test_ambiguous_submission_blocks_legacy_revival_even_if_old(self):
        module = importlib.import_module(f"{fixtures.CORE_PACKAGE_NAME}.tasks.reconsider")
        job = await self.job()
        job.update(status="cancelled", reason=module.STALE_REASON)
        unknown = copy.copy(job)
        unknown.update(id="unknown", status="submitting", created_at=job["created_at"] - 8000)
        await self.review.migrate({job["id"]: job, "unknown": unknown})
        self.assertEqual(job["status"], "cancelled")

    async def test_shutdown_keeps_review_checkpoint_and_call_budget(self):
        await self.job()
        self.plugin.call_llm.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.service.recover_once()
        result = self.case.journal()
        self.assertEqual(result["status"], "waiting_review")
        self.assertEqual(result["review_attempts"], 1)
        self.assertEqual(self.service.active, set())

    async def test_command_media_returns_selected_asset_without_generating(self):
        job = await self.job()
        job["prepared_media"][2:4] = [None, None]
        media_module = importlib.import_module(f"{fixtures.CORE_PACKAGE_NAME}.tasks.command.manual.mediafile")
        owner = types.SimpleNamespace()
        media_service = media_module.TaskCommandLocalMediaService(owner)
        token = self.case.mediajob.current_share_job.set(job)
        try:
            media = await media_service._generate_command_media(
                progress_id="p", content="新正文", target_type_enum=self.case.mod.ShareType.MOOD,
                life_ctx="最新生活", target_umo=fixtures.USER_TARGET_1, period=self.case.mod.TimePeriod.NIGHT,
                event=None, need_image=True, need_video=True, need_voice=True,
            )
        finally:
            self.case.mediajob.current_share_job.reset(token)
        self.assertEqual(list(media), job["prepared_media"])

    async def test_qzone_selected_none_cannot_regenerate_old_image(self):
        job = await self.job()
        job["prepared_media"] = [None, None, None, None, ""]
        module = importlib.import_module(f"{fixtures.CORE_PACKAGE_NAME}.tasks.moments.pipeline")
        owner = types.SimpleNamespace(
            plugin=self.plugin,
            _generate_qzone_image=AsyncMock(),
            _prepare_qzone_publish_media=AsyncMock(return_value=[]),
            _publish_and_record_qzone_share=AsyncMock(),
            services=self.case.manager.services if hasattr(self.case.manager, "services") else self.case.manager,
        )
        owner.services = types.SimpleNamespace(progress=self.case.manager.progress)
        token = self.case.mediajob.current_share_job.set(job)
        try:
            self.assertTrue(await module.TaskQzoneFlowService(owner).send_prepared_qzone_share(
                stype=self.case.mod.ShareType.MOOD, content="公开新正文", life_ctx="公开生活", news_data=None,
                progress_id="p", history_source="scheduled",
            ))
        finally:
            self.case.mediajob.current_share_job.reset(token)
        owner._generate_qzone_image.assert_not_called()
        owner._prepare_qzone_publish_media.assert_awaited_once_with(target_local_img=None)
        self.assertEqual(owner._publish_and_record_qzone_share.await_args.kwargs["content"], "公开新正文")

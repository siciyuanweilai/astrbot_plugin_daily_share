"""持久化媒体恢复使用生活插件的公开接口契约，不重复提交任务。"""

import asyncio
import importlib
import json
import tempfile
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

from tests import testfailure as fixtures


class MediaRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mod = fixtures._load_tasks_module()
        root = fixtures.CORE_PACKAGE_NAME
        self.mediajob = importlib.import_module(f"{root}.integrations.mediajob")
        self.bridge_class = importlib.import_module(
            f"{root}.integrations.dailylife"
        ).DailyLifeBridge
        self.service_class = importlib.import_module(
            f"{root}.tasks.continuation"
        ).ShareContinuationService
        self.plugin = fixtures._Plugin()
        self.manager = fixtures._new_manager(self.mod, self.plugin)
        self.plugin.task_manager = self.manager
        self.plugin.runtime_service = types.SimpleNamespace(
            is_share_busy=lambda target: False,
            get_share_lock=self.plugin.get_share_lock,
        )
        self.service = self.service_class(self.plugin)
        self.plugin.share_continuations = self.service
        self.life = types.SimpleNamespace(
            generate_share_image_task=AsyncMock(return_value={"status": "pending"}),
            generate_share_video_task=AsyncMock(return_value={"status": "pending"}),
            get_share_image_task=AsyncMock(return_value={"status": "pending"}),
            get_share_video_task=AsyncMock(return_value={"status": "pending"}),
        )
        self.stars = [
            types.SimpleNamespace(
                root_dir_name="astrbot_plugin_daily_life",
                name="astrbot_plugin_daily_life",
                activated=True,
                star_cls=self.life,
            )
        ]
        self.bridge = self.bridge_class(
            types.SimpleNamespace(get_all_stars=lambda: self.stars)
        )
        self.plugin.daily_life_bridge = self.bridge
        self.sent = []

        async def send_chain(uid, chain, event=None):
            self.sent.append((uid, list(chain.items), event))

        async def image(*args, **kwargs):
            job = self.mediajob.current_share_job.get()
            if job.get("image_failed"):
                return None
            if job.get("image_path"):
                return job["image_path"]
            return await self.bridge.generate_image(None, "原配图提示词")

        async def video(*args, **kwargs):
            return await self.bridge.generate_video(
                None, "原视频提示词", reference_image=args[0]
            )

        self.manager.delivery.chains.send_message_chain = send_chain
        self.manager.delivery.random_sleep = lambda: asyncio.sleep(0)
        self.plugin.image_service.generate_image = image
        self.plugin.image_service.generate_video_from_image = video
        self.manager.update_configs(
            image={
                "enable_ai_image": True,
                "image_enabled_types": ["心情"],
                "separate_send": True,
                "enable_ai_video": False,
                "video_enabled_types": ["心情"],
            }
        )

    def progress(self):
        return self.manager.progress.get_share_progress_snapshot()

    def start_progress(self):
        return self.manager.progress.start_share_progress(
            source_type="command",
            target_id=fixtures.USER_TARGET_1,
        )

    def params(self, progress_id):
        return {
            "uid": fixtures.USER_TARGET_1,
            "stype": self.mod.ShareType.MOOD,
            "content": "保留原文案",
            "news_data": None,
            "life_ctx": "原生活快照",
            "period": self.mod.TimePeriod.NIGHT,
            "progress_id": progress_id,
            "history_source": "command",
        }

    async def job(self, *, kind="image", age=0):
        params = self.params(self.start_progress())
        params["stype"] = {"enum": "ShareType", "value": "mood"}
        params["period"] = {
            "enum": "TimePeriod",
            "value": self.mod.TimePeriod.NIGHT.value,
        }
        job = {
            "id": "original",
            "kind": "chat",
            "status": "pending",
            "params": params,
            "created_at": datetime.now().timestamp() - age,
            "pending_media": kind,
            "service": self.service,
        }
        self.manager.progress.update_share_progress(
            params["progress_id"], kind, message="等待原任务成品"
        )
        await self.service.save(job)
        return job

    def journal(self, key="original"):
        return self.plugin.db.state["share_media_continuations"][key]

    def enable_scheduled(self):
        self.plugin.config["enable_auto_share"] = True
        self.plugin.basic_conf["trigger_mode"] = "fixed_time"
        self.manager.update_configs(
            basic=self.plugin.basic_conf,
            receiver={"users": [fixtures.USER_TARGET_1], "groups": []},
        )

    async def test_contact_wait_survives_reload_and_reuses_all_finished_media_once(
        self,
    ):
        self.enable_scheduled()
        self.manager.update_configs(
            image={
                "enable_ai_image": True,
                "image_enabled_types": ["心情"],
                "enable_ai_video": True,
                "video_enabled_types": ["心情"],
            },
            tts={"enable_tts": True, "tts_enabled_types": ["心情"]},
        )
        coordinate = AsyncMock(
            side_effect=[
                {"allowed": True, "snapshot": "original-facts"},
                {
                    "allowed": False,
                    "retryable": True,
                    "reason": "该会话刚收到主动消息，稍后再联系",
                },
                {"allowed": True},  # 首次进入等待状态后释放预约。
            ]
        )
        self.life.coordinate_share_contact = coordinate
        with tempfile.TemporaryDirectory() as tmp:
            image, video, audio = [
                str(Path(tmp) / name)
                for name in ("original.png", "original.mp4", "original.wav")
            ]
            for path in (image, video, audio):
                Path(path).touch()
            self.life.generate_share_image_task.return_value = {
                "status": "ready",
                "path": image,
            }
            self.life.generate_share_video_task.return_value = {
                "status": "ready",
                "url": video,
            }
            speech = AsyncMock(return_value=audio)
            self.plugin.ctx_service.text_to_speech = speech
            params = self.params(self.start_progress())
            params["history_source"] = "scheduled"
            self.assertFalse(
                await self.manager.share.send_prepared_chat_share(**params)
            )
            key = next(iter(self.plugin.db.state["share_media_continuations"]))
            self.assertEqual(self.journal(key)["status"], "waiting_contact")
            self.assertTrue(
                await self.service.has_pending_share(fixtures.USER_TARGET_1)
            )
            self.assertIn("成品已保留", self.progress()["message"])
            self.assertEqual(self.sent, [])

            # 恢复时复核原事实快照，并发送已保存的媒体成品。
            self.plugin.db.state = json.loads(json.dumps(self.plugin.db.state))
            self.service = self.service_class(self.plugin)
            self.plugin.share_continuations = self.service
            coordinate.side_effect = None
            coordinate.return_value = {"allowed": True}
            await self.service.recover_once()
            await self.service.recover_once()

        speech.assert_awaited_once()
        self.life.generate_share_image_task.assert_awaited_once()
        self.life.generate_share_video_task.assert_awaited_once()
        self.life.get_share_image_task.assert_not_called()
        self.life.get_share_video_task.assert_not_called()
        self.assertEqual(self.journal(key)["status"], "completed")
        self.assertNotIn("reason", self.journal(key))
        self.assertEqual(len(self.plugin.db.history), 1)
        self.assertEqual(len(self.sent), 3)
        self.assertEqual(self.sent[0][1], ["保留原文案"])
        self.assertEqual(self.sent[1][1][0].file, audio)
        self.assertEqual(self.sent[2][1][0].source, ("file_video", video))
        check = [
            call
            for call in coordinate.await_args_list
            if call.kwargs.get("action") == "check"
        ]
        self.assertEqual(len(check), 2)
        self.assertTrue(
            all(call.kwargs["expected"] == "original-facts" for call in check)
        )

    async def test_waiting_contact_still_cancels_on_new_chat_without_resubmitting(self):
        self.enable_scheduled()
        job = await self.job()
        job.update(
            status="waiting_contact",
            prepared_media=[None, None, None, None, ""],
            contact_snapshot="original-facts",
        )
        job["params"]["history_source"] = "scheduled"
        await self.service.save(job)
        self.life.coordinate_share_contact = AsyncMock(
            return_value={
                "allowed": False,
                "stale": True,
                "retryable": True,
                "reason": "新消息",
            }
        )
        await self.service.recover_once()
        await self.service.recover_once()
        self.assertEqual(self.journal()["status"], "cancelled")
        self.assertEqual(self.journal()["reason"], "新消息")
        self.assertEqual(self.sent, [])
        self.life.get_share_image_task.assert_not_called()
        self.life.generate_share_image_task.assert_not_called()

    async def test_missing_saved_media_fails_without_regeneration(self):
        job = await self.job()
        job.update(
            status="waiting_contact",
            prepared_media=[None, None, None, "/nonexistent/original.wav", ""],
        )
        await self.service.save(job)
        await self.service.recover_once()
        self.assertEqual(self.journal()["status"], "failed")
        self.assertIn("原媒体成品文件不存在", self.journal()["reason"])
        self.assertEqual(self.sent, [])
        self.life.get_share_image_task.assert_not_called()
        self.life.generate_share_image_task.assert_not_called()

    async def test_terminal_recovery_ends_progress_without_sending_or_resubmitting(
        self,
    ):
        for kind, result, age, expected in (
            ("image", {"status": "missing"}, 0, "failed"),
            (
                "image",
                {"status": "ready", "path": "/nonexistent/original.png"},
                0,
                "failed",
            ),
            (
                "video",
                {"status": "ready", "url": "/nonexistent/original.mp4"},
                0,
                "failed",
            ),
            ("image", {"status": "pending"}, 86401, "cancelled"),
        ):
            with self.subTest(kind=kind, result=result, age=age):
                await self.job(kind=kind, age=age)
                getattr(self.life, f"get_share_{kind}_task").return_value = result
                await self.service.recover_once()
                await self.service.recover_once()
                self.assertEqual(self.journal()["status"], expected)
                self.assertEqual(self.progress()["status"], "error")
                self.assertEqual(self.progress()["message"], self.journal()["reason"])
                self.assertTrue(self.progress()["finished_at"])
                self.assertFalse(
                    await self.service.has_pending_share(fixtures.USER_TARGET_1)
                )
        self.assertEqual(self.sent, [])
        self.life.generate_share_image_task.assert_not_called()
        self.life.generate_share_video_task.assert_not_called()

    async def test_disabled_scheduled_share_is_cancelled_without_query(self):
        job = await self.job()
        job["params"]["history_source"] = "scheduled"
        await self.service.save(job)
        await self.service.recover_once()
        self.assertEqual(self.journal()["status"], "cancelled")
        self.assertEqual(self.progress()["status"], "error")
        self.life.get_share_image_task.assert_not_called()

    async def test_terminal_old_job_does_not_finish_newer_progress(self):
        await self.job()
        new_id = self.start_progress()
        self.life.get_share_image_task.return_value = {"status": "missing"}
        await self.service.recover_once()
        self.assertEqual(self.progress()["id"], new_id)
        self.assertEqual(self.progress()["status"], "running")

    async def test_progress_ids_do_not_collide_after_manager_restart(self):
        first = self.start_progress()
        manager = fixtures._new_manager(self.mod, self.plugin)
        second = manager.progress.start_share_progress(source_type="command")
        self.assertNotEqual(first, second)

    async def test_ambiguous_submission_stops_spinner_but_keeps_resend_guard(self):
        job = await self.job()
        job["status"] = "submitting"
        await self.service.save(job)
        await self.service.recover_once()
        self.assertEqual(self.journal()["status"], "submitting")
        self.assertEqual(self.progress()["status"], "error")
        self.assertIn("结果不明", self.progress()["message"])
        self.assertTrue(await self.service.has_pending_share(fixtures.USER_TARGET_1))
        self.assertEqual(self.sent, [])

    async def test_query_unavailable_and_unknown_result_keep_original_job_waiting(self):
        await self.job(age=125)
        for result in (
            None,
            {"status": "future-state"},
            {"status": "unavailable", "error": "生活插件正在重载"},
        ):
            self.life.get_share_image_task.return_value = result
            await self.service.recover_once()
            self.assertEqual(self.journal()["status"], "pending")
            self.assertEqual(self.progress()["status"], "running")
            self.assertIn("等待恢复", self.progress()["message"])
            self.assertIn("2 分钟", self.progress()["message"])
        self.life.get_share_image_task.side_effect = RuntimeError(
            "secret provider response"
        )
        await self.service.recover_once()
        self.assertIn("RuntimeError", self.progress()["message"])
        self.assertNotIn("secret", json.dumps(self.journal()))
        self.life.get_share_image_task.side_effect = None
        self.life.get_share_image_task.return_value = {"status": "pending"}
        await self.service.recover_once()
        self.assertIn("等待原任务成品", self.progress()["message"])
        self.assertEqual(self.journal()["media_results"]["image"], ["pending", ""])
        self.assertEqual(self.sent, [])
        self.life.generate_share_image_task.assert_not_called()

    async def test_reload_then_ready_sends_original_image_once(self):
        progress_id = self.start_progress()
        self.assertFalse(
            await self.manager.share.send_prepared_chat_share(
                **self.params(progress_id)
            )
        )
        key = next(iter(self.plugin.db.state["share_media_continuations"]))
        self.stars.clear()
        await self.service.recover_once()
        self.assertEqual(self.sent, [])
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "original.png")
            Path(path).touch()
            self.life.get_share_image_task.return_value = {
                "status": "ready",
                "path": path,
            }
            self.stars.append(
                types.SimpleNamespace(
                    root_dir_name="astrbot_plugin_daily_life",
                    name="astrbot_plugin_daily_life",
                    activated=True,
                    star_cls=self.life,
                )
            )
            # 从 JSON 任务记录重建桥接层和服务，模拟插件重载。
            self.plugin.db.state = json.loads(json.dumps(self.plugin.db.state))
            self.service = self.service_class(self.plugin)
            self.plugin.share_continuations = self.service
            self.bridge = self.bridge_class(
                types.SimpleNamespace(get_all_stars=lambda: self.stars)
            )
            self.plugin.daily_life_bridge = self.bridge
            await self.service.recover_once()
            await self.service.recover_once()
        self.life.generate_share_image_task.assert_awaited_once()
        self.assertEqual(
            self.life.generate_share_image_task.await_args.kwargs["task_key"],
            f"{key}:image",
        )
        self.assertEqual(
            self.life.generate_share_image_task.await_args.kwargs["target_umo"],
            fixtures.USER_TARGET_1,
        )
        self.assertEqual(
            self.sent,
            [
                (fixtures.USER_TARGET_1, ["保留原文案"], None),
                (fixtures.USER_TARGET_1, [("file_image", path)], None),
            ],
        )
        self.assertEqual(len(self.plugin.db.history), 1)
        self.assertEqual(self.journal(key)["status"], "completed")
        self.assertEqual(self.journal(key)["media_results"]["image"], ["ok", ""])

    async def test_confirmed_image_failure_survives_restart_as_degraded_history(self):
        job = await self.job()
        self.life.get_share_image_task.return_value = {
            "status": "failed",
            "error": "原通道返回 429，额度不足",
        }
        self.manager.state.share_progress = None
        await self.service.recover_once()
        await self.service.recover_once()
        self.assertEqual(self.sent, [(fixtures.USER_TARGET_1, ["保留原文案"], None)])
        self.assertEqual(self.journal()["status"], "completed")
        self.assertEqual(len(self.plugin.db.history), 1)
        history = self.plugin.db.history[0][1]
        self.assertTrue(history["success"])
        self.assertTrue(history["degraded"])
        self.assertIn("额度不足", history["degradation_reason"])
        self.assertTrue(self.journal()["image_failed"])
        self.life.generate_share_image_task.assert_not_called()
        self.assertEqual(job["params"]["content"], "保留原文案")

    async def test_video_pending_then_success_clears_old_status_without_resubmit(self):
        job = await self.job(kind="video")
        job.update(pending_media="", status="generating")
        token = self.mediajob.current_share_job.set(job)
        try:
            with self.assertRaises(self.mediajob.ShareMediaPending):
                await self.bridge.generate_video(
                    None, "原视频提示词", reference_image="original.png"
                )
            self.assertEqual(self.bridge.media_result("video"), ("pending", ""))
            self.life.get_share_video_task.return_value = {
                "status": "ready",
                "url": "https://example.invalid/original.mp4",
            }
            self.assertEqual(
                await self.bridge.generate_video(None, "不能重提"),
                "https://example.invalid/original.mp4",
            )
            self.assertEqual(self.bridge.media_result("video"), ("ok", ""))
            self.life.generate_share_video_task.assert_awaited_once()
        finally:
            self.mediajob.current_share_job.reset(token)

    async def test_video_failure_keeps_original_image_and_records_degradation_once(
        self,
    ):
        self.manager.update_configs(
            image={
                "enable_ai_image": True,
                "image_enabled_types": ["心情"],
                "enable_ai_video": True,
                "video_enabled_types": ["心情"],
                "separate_send": True,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "original.png")
            Path(path).touch()
            self.life.generate_share_image_task.return_value = {
                "status": "ready",
                "path": path,
            }
            self.assertFalse(
                await self.manager.share.send_prepared_chat_share(
                    **self.params(self.start_progress())
                )
            )
            self.life.get_share_video_task.return_value = {
                "status": "failed",
                "error": "视频任务已取消",
            }
            await self.service.recover_once()
            await self.service.recover_once()
        self.life.generate_share_image_task.assert_awaited_once()
        self.life.generate_share_video_task.assert_awaited_once()
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(self.sent[1][1], [("file_image", path)])
        self.assertIn(
            "视频任务已取消", self.plugin.db.history[0][1]["degradation_reason"]
        )
        self.assertEqual(self.progress()["status"], "done")

    async def test_video_recovery_delivers_video_not_first_frame_once(self):
        self.manager.update_configs(
            image={
                "enable_ai_image": True,
                "image_enabled_types": ["心情"],
                "enable_ai_video": True,
                "video_enabled_types": ["心情"],
                "separate_send": True,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "original.png")
            video_path = str(Path(tmp) / "original.mp4")
            Path(path).touch()
            Path(video_path).touch()
            self.life.generate_share_image_task.return_value = {
                "status": "ready",
                "path": path,
            }
            self.assertFalse(
                await self.manager.share.send_prepared_chat_share(
                    **self.params(self.start_progress())
                )
            )
            self.assertEqual(self.sent, [])
            self.life.get_share_video_task.return_value = {
                "status": "ready",
                "url": video_path,
            }
            await self.service.recover_once()
            await self.service.recover_once()
        self.life.generate_share_image_task.assert_awaited_once()
        self.life.generate_share_video_task.assert_awaited_once()
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(self.sent[0], (fixtures.USER_TARGET_1, ["保留原文案"], None))
        self.assertEqual(self.sent[1][1][0].source, ("file_video", video_path))
        self.assertEqual(len(self.plugin.db.history), 1)
        self.assertFalse(self.plugin.db.history[0][1]["degraded"])
        self.assertEqual(self.progress()["status"], "done")

    async def test_independent_job_cannot_inherit_previous_media_error(self):
        self.bridge._set_media_result("image", "error", "另一任务的失败原因")
        job = await self.job()
        token = self.mediajob.current_share_job.set(job)
        try:
            self.assertEqual(self.bridge.media_result("image"), ("", ""))
            self.assertEqual(
                self.manager.progress.share_progress_degradation_reason(
                    job["params"]["progress_id"]
                ),
                "",
            )
        finally:
            self.mediajob.current_share_job.reset(token)

    async def test_resume_preserves_delivery_failure_reason(self):
        job = await self.job()

        async def failed_delivery(**params):
            self.manager.progress.finish_share_progress(
                params["progress_id"], success=False, message="原目标已不可发送"
            )
            return False

        self.manager.share.send_prepared_chat_share = failed_delivery
        await self.service.resume(job)
        self.assertEqual(self.journal()["status"], "failed")
        self.assertEqual(self.journal()["reason"], "原目标已不可发送")
        self.assertEqual(self.progress()["message"], "原目标已不可发送")
        self.assertEqual(self.sent, [])

    async def test_task_submission_uncertainty_waits_for_query_not_new_submission(self):
        for kind in ("image", "video"):
            with self.subTest(kind=kind):
                job = await self.job(kind=kind)
                job.update(pending_media="", status="generating")
                submit = getattr(self.life, f"generate_share_{kind}_task")
                submit.side_effect = TimeoutError(
                    "request accepted but connection lost"
                )
                token = self.mediajob.current_share_job.set(job)
                try:
                    for _ in range(2):
                        with self.assertRaises(self.mediajob.ShareMediaPending):
                            await getattr(self.bridge, f"generate_{kind}")(
                                None, "原提示词"
                            )
                    submit.assert_awaited_once()
                    self.assertEqual(job["pending_media"], kind)
                finally:
                    self.mediajob.current_share_job.reset(token)

    async def test_failed_and_empty_ready_tasks_report_safe_errors(self):
        for kind in ("image", "video"):
            for result in (
                {
                    "status": "failed",
                    "error": '额度不足 api_key="hidden-key" Authorization: Bearer hidden-bearer https://private.invalid/file?token=hidden-url',
                },
                {"status": "ready"},
            ):
                with self.subTest(kind=kind, result=result):
                    job = await self.job(kind=kind)
                    job.update(pending_media="", status="generating")
                    getattr(
                        self.life, f"generate_share_{kind}_task"
                    ).return_value = result
                    token = self.mediajob.current_share_job.set(job)
                    try:
                        self.assertEqual(
                            await getattr(self.bridge, f"generate_{kind}")(
                                None, "提示词"
                            ),
                            "",
                        )
                        status, reason = self.bridge.media_result(kind)
                        self.assertEqual(status, "error")
                        self.assertIn(
                            "额度不足"
                            if result["status"] == "failed"
                            else "未返回有效成品",
                            reason,
                        )
                        for secret in (
                            "hidden-key",
                            "hidden-bearer",
                            "private.invalid",
                            "hidden-url",
                        ):
                            self.assertNotIn(
                                secret, json.dumps(self.journal(), ensure_ascii=False)
                            )
                    finally:
                        self.mediajob.current_share_job.reset(token)

    async def test_resume_exception_finishes_progress_and_releases_context(self):
        await self.job()
        self.life.get_share_image_task.return_value = {"status": "failed"}
        self.manager.share.send_prepared_chat_share = AsyncMock(
            side_effect=RuntimeError("test")
        )
        await self.service.recover_once()
        self.assertEqual(self.progress()["status"], "error")
        self.assertEqual(self.journal()["status"], "failed")
        self.assertIsNone(self.mediajob.current_share_job.get())
        self.assertEqual(self.service.active, set())


if __name__ == "__main__":
    unittest.main()

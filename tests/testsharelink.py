import asyncio
import copy
import time
import types
import unittest
from unittest.mock import AsyncMock

from astrbot_plugin_daily_share.core.config import ShareType
from astrbot_plugin_daily_share.core.context.daily.parser import ContextLifeParseService
from astrbot_plugin_daily_share.core.integrations.mediajob import (
    ShareMediaPending,
    current_share_job,
)
from astrbot_plugin_daily_share.core.tasks.continuation import (
    ShareContinuationService,
    preserve_share,
)

from .testintegration import DailyLifeBridge, _metadata


class _Database:
    def __init__(self):
        self.values = {}

    async def update_share_state(self, key, updates):
        self.values.setdefault(key, {}).update(copy.deepcopy(updates))

    async def get_share_state(self, key, default=None):
        return copy.deepcopy(self.values.get(key, default))

    async def set_share_state(self, key, value):
        self.values[key] = copy.deepcopy(value)

    update_context_state = update_share_state
    get_context_state = get_share_state
    set_context_state = set_share_state


class ShareLinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_receipt_outbox_survives_reload_and_flushes(self):
        db = _Database()
        context = types.SimpleNamespace(get_all_stars=lambda: [])
        first = DailyLifeBridge(context, db=db)
        receipt = {"event_id": "post-1", "scene": "qzone_post", "content": "随手发一条"}
        self.assertFalse(await first.record_public_activity(receipt))
        method = AsyncMock(return_value=True)
        context.get_all_stars = lambda: [
            _metadata(types.SimpleNamespace(record_public_activity=method))
        ]
        fresh = DailyLifeBridge(context, db=db)
        await fresh.flush_public_receipts()
        self.assertEqual(method.await_count, 1)
        self.assertEqual(db.values["public_activity_outbox"], {})

    async def test_pending_share_keeps_text_target_and_resumes_once(self):
        db = _Database()
        lock = asyncio.Lock()
        plugin = types.SimpleNamespace(
            db=db,
            _is_terminated=False,
            runtime_service=types.SimpleNamespace(
                is_share_busy=lambda target: False,
                get_share_lock=lambda target, **kwargs: lock,
            ),
        )
        life = types.SimpleNamespace(
            generate_share_image_task=AsyncMock(return_value={"status": "pending"}),
            get_share_image_task=AsyncMock(
                return_value={
                    "status": "ready",
                    "path": "https://cdn.example/original.png",
                }
            ),
        )
        plugin.daily_life_bridge = DailyLifeBridge(
            types.SimpleNamespace(get_all_stars=lambda: [_metadata(life)])
        )
        service = ShareContinuationService(plugin)
        plugin.share_continuations = service
        sent = []

        class Owner:
            services = types.SimpleNamespace(
                progress=types.SimpleNamespace(
                    update_share_progress=lambda *args, **kwargs: None
                )
            )

            @preserve_share("qzone")
            async def send_prepared_qzone_share(
                self, *, content, stype, history_source, progress_id, event=None
            ):
                job = current_share_job.get()
                path = job.get("image_path")
                if not path:
                    path = await self.plugin.daily_life_bridge.generate_image(
                        event, "one original prompt"
                    )
                await self.plugin.share_continuations.mark_submitting()
                sent.append((content, stype, path, event))
                return True

        owner = Owner()
        owner.plugin = plugin
        plugin.task_manager = types.SimpleNamespace(
            qzone_share=owner,
            share=types.SimpleNamespace(send_prepared_chat_share=None),
            command_share=types.SimpleNamespace(send_prepared_command_share=None),
        )
        original_event = object()
        result = await owner.send_prepared_qzone_share(
            content="保留原来的这句话",
            stype=ShareType.MOOD,
            history_source="command",
            progress_id="test-progress",
            event=original_event,
        )
        self.assertFalse(result)
        self.assertEqual(sent, [])
        self.assertIsNone(current_share_job.get())
        rows = db.values["share_media_continuations"]
        self.assertEqual(len(rows), 1)
        self.assertNotIn("event", next(iter(rows.values()))["params"])
        await service.recover_once()
        await service.recover_once()
        self.assertEqual(
            sent,
            [
                (
                    "保留原来的这句话",
                    ShareType.MOOD,
                    "https://cdn.example/original.png",
                    None,
                )
            ],
        )
        self.assertEqual(life.generate_share_image_task.await_count, 1)
        self.assertEqual(
            next(iter(db.values["share_media_continuations"].values()))["status"],
            "completed",
        )

    async def test_ambiguous_submissions_are_never_automatically_replayed(self):
        plugin = types.SimpleNamespace(
            db=_Database(),
            daily_life_bridge=types.SimpleNamespace(get_image_task=AsyncMock()),
        )
        service = ShareContinuationService(plugin)
        await service.save(
            {
                "id": "unknown-post",
                "kind": "qzone",
                "status": "submitting",
                "params": {},
                "service": service,
            }
        )
        await service.recover_once()
        plugin.daily_life_bridge.get_image_task.assert_not_awaited()

    async def test_video_pending_is_not_swallowed_or_treated_as_empty_result(self):
        life = types.SimpleNamespace(
            generate_share_video_task=AsyncMock(return_value={"status": "pending"})
        )
        bridge = DailyLifeBridge(
            types.SimpleNamespace(get_all_stars=lambda: [_metadata(life)])
        )
        job = {"id": "video-owner", "service": types.SimpleNamespace(save=AsyncMock())}
        token = current_share_job.set(job)
        try:
            with self.assertRaises(ShareMediaPending):
                await bridge.generate_video(
                    None, "locked motion", reference_image="/tmp/original.png"
                )
            self.assertEqual(job["pending_media"], "video")
            self.assertEqual(
                life.generate_share_video_task.await_args.kwargs["reference_image"],
                "/tmp/original.png",
            )
        finally:
            current_share_job.reset(token)

    def test_recovery_obeys_disabled_expired_and_smart_quiet_gates(self):
        smart = types.SimpleNamespace(is_quiet_time=lambda now, quiet: True)
        plugin = types.SimpleNamespace(
            qzone_conf={"enable_qzone": False, "qzone_trigger_mode": "llm_smart"},
            task_manager=types.SimpleNamespace(
                schedule=types.SimpleNamespace(smart=smart)
            ),
        )
        service = ShareContinuationService(plugin)
        job = {
            "id": "scheduled",
            "kind": "qzone",
            "created_at": time.time(),
            "params": {"history_source": "scheduled"},
        }
        self.assertEqual(service.recovery_allowed(job), (False, True))
        plugin.qzone_conf["enable_qzone"] = True
        self.assertEqual(service.recovery_allowed(job), (False, False))
        plugin.qzone_conf["qzone_trigger_mode"] = "fixed_time"
        self.assertEqual(service.recovery_allowed(job), (True, False))
        job["created_at"] -= 7201
        self.assertEqual(service.recovery_allowed(job), (False, True))
        job["params"]["history_source"] = "command"
        self.assertEqual(service.recovery_allowed(job), (True, False))
        job["created_at"] -= 86400
        self.assertEqual(service.recovery_allowed(job), (False, True))

    def test_public_snapshot_uses_actual_action_and_safe_expression_only(self):
        parser = ContextLifeParseService(
            types.SimpleNamespace(
                life_conf={"group_share_schedule": False},
                life_memory=types.SimpleNamespace(
                    _compact_life_text=lambda value, limit: str(value)[:limit]
                ),
            )
        )
        data = {
            "weather": "晴",
            "current_facts": {
                "valid": True,
                "current_action": {"activity": "练习摄影", "status": "paused"},
            },
            "timeline": [{"activity": "old-plan", "execution_state": "active"}],
            "chat_summaries": ["private-chat"],
            "share_guidance": {
                "expression": {
                    "habits": ["不用刻意反问"],
                    "temporary": ["private-temporary"],
                    "evidence": ["private-evidence"],
                }
            },
        }
        post = parser._parse_qzone_post_data(data)
        self.assertIn("已暂停，尚未完成", post)
        self.assertIn("不用刻意反问", post)
        for private in (
            "old-plan",
            "private-chat",
            "private-temporary",
            "private-evidence",
        ):
            self.assertNotIn(private, post)
        group = parser._parse_group_life_data(data)
        self.assertNotIn("old-plan", group)
        self.assertNotIn("private-chat", group)
        data["current_facts"]["valid"] = False
        self.assertNotIn("练习摄影", parser._parse_qzone_post_data(data))
        self.assertEqual(parser._parse_group_life_data(data), "")

    async def test_publication_success_is_not_retried_when_receipt_fails(self):
        from astrbot_plugin_daily_share.core.host.portal import PluginQzoneService

        service = types.SimpleNamespace(
            context=AsyncMock(return_value=types.SimpleNamespace(nickname="Me", uin=1)),
            publish_post=AsyncMock(
                return_value=types.SimpleNamespace(tid="t", key="1:t")
            ),
            invalidate=unittest.mock.Mock(),
        )
        plugin = types.SimpleNamespace(
            daily_life_bridge=types.SimpleNamespace(
                record_public_activity=AsyncMock(
                    side_effect=RuntimeError("Cookie receipt error")
                )
            )
        )
        host = PluginQzoneService(
            types.SimpleNamespace(plugin=plugin, qzone_service=service)
        )
        result = await host.publish_qzone("original")
        self.assertEqual(result.key, "1:t")
        self.assertEqual(service.publish_post.await_count, 1)
        service.invalidate.assert_not_called()

    async def test_completed_video_resumes_prepared_share_without_resubmission(self):
        db = _Database()
        handler = AsyncMock(return_value=True)
        plugin = types.SimpleNamespace(
            db=db,
            _is_terminated=False,
            runtime_service=types.SimpleNamespace(
                is_share_busy=lambda target: False,
                get_share_lock=lambda target, **kwargs: asyncio.Lock(),
            ),
            daily_life_bridge=types.SimpleNamespace(
                get_video_task=AsyncMock(
                    return_value={"status": "ready", "url": "https://cdn.example/v.mp4"}
                ),
                get_image_task=AsyncMock(),
            ),
            task_manager=types.SimpleNamespace(
                qzone_share=types.SimpleNamespace(send_prepared_qzone_share=handler),
                share=types.SimpleNamespace(send_prepared_chat_share=None),
                command_share=types.SimpleNamespace(send_prepared_command_share=None),
            ),
        )
        service = ShareContinuationService(plugin)
        await service.save(
            {
                "id": "video-a",
                "kind": "qzone",
                "status": "pending",
                "pending_media": "video",
                "video_started": True,
                "image_path": "/tmp/original.png",
                "params": {"content": "original"},
            }
        )
        await service.recover_once()
        handler.assert_awaited_once_with(content="original", event=None)
        plugin.daily_life_bridge.get_image_task.assert_not_awaited()
        saved = db.values["share_media_continuations"]["video-a"]
        self.assertEqual(saved["video_url"], "https://cdn.example/v.mp4")
        self.assertEqual(saved["image_path"], "/tmp/original.png")
        self.assertEqual(saved["status"], "completed")

    async def test_pending_target_blocks_scheduled_recreation_but_not_other_targets(
        self,
    ):
        plugin = types.SimpleNamespace(db=_Database())
        service = ShareContinuationService(plugin)
        await service.save(
            {
                "id": "waiting-a",
                "kind": "chat",
                "status": "pending",
                "created_at": time.time(),
                "params": {"uid": "one:FriendMessage:1", "history_source": "command"},
            }
        )
        self.assertTrue(await service.has_pending_share("one:FriendMessage:1"))
        self.assertFalse(await service.has_pending_share("one:FriendMessage:2"))

    async def test_submission_exception_preserves_ambiguous_journal(self):
        plugin = types.SimpleNamespace(db=_Database())
        plugin.share_continuations = ShareContinuationService(plugin)

        class Owner:
            @preserve_share("qzone")
            async def publish(self, *, content):
                await self.plugin.share_continuations.mark_submitting()
                raise TimeoutError("unknown publication outcome")

        owner = Owner()
        owner.plugin = plugin
        with self.assertRaises(TimeoutError):
            await owner.publish(content="original")
        row = next(iter(plugin.db.values["share_media_continuations"].values()))
        self.assertEqual(row["status"], "submitting")
        self.assertTrue(
            await plugin.share_continuations.has_pending_share("qzone_broadcast")
        )

    async def test_failed_original_image_can_degrade_without_regeneration(self):
        from astrbot_plugin_daily_share.core.image import ImageService

        plugin = types.SimpleNamespace(
            db=_Database(),
            _is_terminated=False,
            runtime_service=types.SimpleNamespace(
                is_share_busy=lambda target: False,
                get_share_lock=lambda target, **kwargs: asyncio.Lock(),
            ),
            daily_life_bridge=types.SimpleNamespace(
                get_image_task=AsyncMock(return_value={"status": "failed"}),
            ),
        )
        image = ImageService(
            None, {"image_conf": {"enable_ai_image": True}}, AsyncMock()
        )
        image._check_involves_self = AsyncMock()
        sent = []

        async def prepared(**kwargs):
            self.assertIsNone(
                await image.generate_image(kwargs["content"], ShareType.MOOD)
            )
            sent.append(kwargs["content"])
            return True

        plugin.task_manager = types.SimpleNamespace(
            qzone_share=types.SimpleNamespace(send_prepared_qzone_share=prepared),
            share=types.SimpleNamespace(send_prepared_chat_share=None),
            command_share=types.SimpleNamespace(send_prepared_command_share=None),
        )
        service = ShareContinuationService(plugin)
        await service.save(
            {
                "id": "failed-image",
                "kind": "qzone",
                "status": "pending",
                "pending_media": "image",
                "params": {"content": "original"},
            }
        )
        await service.recover_once()
        self.assertEqual(sent, ["original"])
        image._check_involves_self.assert_not_awaited()
        self.assertEqual(
            plugin.db.values["share_media_continuations"]["failed-image"]["status"],
            "completed",
        )


if __name__ == "__main__":
    unittest.main()

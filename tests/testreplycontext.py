import asyncio
import importlib
import types
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock

from .testqzonecomment import _interaction_args

from .testqzonecomment import CORE_PACKAGE_NAME, FakeDb, _load_auto_comment_module


class ReplyContextTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        module, self.models = _load_auto_comment_module()
        self.sight = importlib.import_module(
            f"{CORE_PACKAGE_NAME}.tasks.interact.sight"
        )
        self.model = importlib.import_module(f"{CORE_PACKAGE_NAME}.host.model")
        self.context = types.SimpleNamespace(
            get_config=lambda umo=None: {
                "agent_runner": {
                    "runner_type": "local",
                    "config": {"model": {"provider_id": "ai-config"}},
                }
            },
            get_all_providers=lambda: [
                types.SimpleNamespace(
                    meta=lambda: types.SimpleNamespace(id="first-chat")
                )
            ],
            get_current_chat_provider_id=AsyncMock(return_value="session-choice"),
            llm_generate=AsyncMock(
                return_value=types.SimpleNamespace(completion_text="湖面有栈道")
            ),
        )
        self.owner = module.TaskQzoneAutoCommentService(*_interaction_args(module))
        self.owner.config.qzone = {
            "qzone_enable_auto_comment_image_vision": True,
            "qzone_auto_comment_image_vision_limit": 3,
        }
        self.owner.runtime = replace(self.owner.runtime, db=FakeDb())
        self.owner.runtime = replace(
            self.owner.runtime,
            ctx_service=types.SimpleNamespace(
                get_qzone_interaction_context=AsyncMock(return_value={})
            ),
        )
        self.owner.runtime = replace(
            self.owner.runtime,
            plugin=types.SimpleNamespace(
                context=self.context,
                basic_conf={},
                call_llm=AsyncMock(return_value="湖面有栈道，刚才是在夸你的取景"),
                daily_life_bridge=types.SimpleNamespace(
                    describe_video=AsyncMock(
                        return_value={
                            "status": "ok",
                            "summary": "镜头从湖面移向林间栈道",
                            "details": "00:03：栈道上有人行走",
                        }
                    )
                ),
            ),
        )
        self.post = self.models.QzonePost(
            uin=2, tid="post", text="秋天散步", images=["https://example.com/lake.jpg"]
        )
        self.root = self.models.QzoneComment(
            uin=1, tid="c1", content="这水色拍得挺开阔"
        )
        self.question = self.models.QzoneComment(
            uin=2, tid="r1", parent_tid="c1", content="画面有啥？后半句啥意思？"
        )

    async def test_reply_and_thread_reuse_original_image_without_calling_vision(self):
        keys = self.sight._qzone_image_vision_cache_keys(
            self.post, self.post.images[0], index=1, total=1, scope="正文配图"
        )
        self.owner.db.state[self.sight.QZONE_AUTO_COMMENT_STATE_KEY] = {
            "processed": {"unrelated": "must not copy"},
            "image_vision_cache": {keys[0]: "湖边有黄色树叶和木栈道"},
        }
        for threaded in (False, True):
            state = {}
            if threaded:
                await self.owner._generate_qzone_auto_reply_thread(
                    self.post, self.root, self.question, state=state
                )
            else:
                await self.owner._generate_qzone_auto_reply(
                    self.post, self.question, state=state
                )
            request = self.owner.plugin.call_llm.await_args.kwargs
            self.assertIn("湖边有黄色树叶和木栈道", request["prompt"])
            self.assertIn(self.question.content, request["prompt"])
            self.assertIn("问到的要点说完整", request["system_prompt"])
            self.assertNotIn("processed", state)
        self.context.llm_generate.assert_not_awaited()

    async def test_thread_includes_video_timeline_and_both_questions(self):
        self.post.videos = ["https://example.com/a.mp4"]
        await self.owner._generate_qzone_auto_reply_thread(
            self.post, self.root, self.question, state={}
        )
        request = self.owner.plugin.call_llm.await_args.kwargs
        for text in (
            "镜头从湖面",
            "00:03",
            "原动态视频封面",
            "画面有啥？后半句啥意思？",
        ):
            self.assertIn(text, request["prompt"])
        self.owner.plugin.daily_life_bridge.describe_video.assert_awaited_once()

    async def test_pending_video_is_unknown_and_later_reply_reuses_ready_result(self):
        self.post.videos = ["https://example.com/a.mp4"]
        describe = self.owner.plugin.daily_life_bridge.describe_video
        describe.side_effect = [
            {"status": "pending"},
            {"status": "ok", "summary": "湖边栈道", "details": "00:04：有鸟鸣"},
        ]
        pending = await self.sight._qzone_video_context(self.owner, self.post)
        self.assertIn("仍在理解中", pending)
        self.assertIn("动作与声音未知", pending)
        self.assertNotIn("湖边栈道", pending)
        ready = await self.sight._qzone_video_context(self.owner, self.post)
        self.assertIn("湖边栈道", ready)
        self.assertIn("00:04：有鸟鸣", ready)
        self.assertNotIn("未知", ready)
        self.assertEqual(describe.await_count, 2)
        self.assertEqual(describe.await_args_list[0], describe.await_args_list[1])

    async def test_vision_switch_off_does_not_call_media(self):
        self.owner.qzone_conf["qzone_enable_auto_comment_image_vision"] = False
        self.post.videos = ["https://example.com/a.mp4"]
        await self.owner._generate_qzone_auto_reply(self.post, self.question, state={})
        self.context.llm_generate.assert_not_awaited()
        self.owner.plugin.daily_life_bridge.describe_video.assert_not_awaited()

    async def test_model_failure_order_for_transient_permanent_and_empty_results(self):
        for error in (
            RuntimeError("connection failed"),
            RuntimeError("401 invalid api key"),
            None,
        ):
            with self.subTest(error=error):
                failed = error if error else types.SimpleNamespace(completion_text="")
                self.context.llm_generate.reset_mock()
                self.context.llm_generate.side_effect = [
                    failed,
                    failed,
                    types.SimpleNamespace(completion_text="ok"),
                ]
                service = self.model.LlmService(
                    self.context, {"llm_provider_id": "selected"}, lambda: False
                )
                self.assertEqual(
                    await service.call("test", umo="qq:FriendMessage:2"), "ok"
                )
                self.assertEqual(
                    [
                        c.kwargs["chat_provider_id"]
                        for c in self.context.llm_generate.await_args_list
                    ],
                    ["selected", "ai-config", "first-chat"],
                )

    async def test_slow_models_leave_budget_for_last_fallback(self):
        async def generate(**kwargs):
            if kwargs["chat_provider_id"] != "first-chat":
                await asyncio.sleep(10)
            return types.SimpleNamespace(completion_text="ok")

        self.context.llm_generate.side_effect = generate
        service = self.model.LlmService(
            self.context, {"llm_provider_id": "selected"}, lambda: False
        )
        service._llm_config_timeout = lambda timeout: 0.08
        result = await asyncio.wait_for(service.call("test"), timeout=0.2)
        self.assertEqual(result, "ok")
        self.assertEqual(self.context.llm_generate.await_count, 3)

    async def test_duplicate_provider_is_skipped_and_blocked_content_stops(self):
        service = self.model.LlmService(
            self.context, {"llm_provider_id": "ai-config"}, lambda: False
        )
        self.context.llm_generate.side_effect = [
            RuntimeError("401"),
            types.SimpleNamespace(completion_text="ok"),
        ]
        self.assertEqual(await service.call("test"), "ok")
        self.assertEqual(
            [
                c.kwargs["chat_provider_id"]
                for c in self.context.llm_generate.await_args_list
            ],
            ["ai-config", "first-chat"],
        )
        self.context.llm_generate.reset_mock()
        self.context.llm_generate.side_effect = RuntimeError("PROHIBITED_CONTENT")
        self.assertIsNone(await service.call("test"))
        self.context.llm_generate.assert_awaited_once()

    async def test_vision_uses_ai_config_before_first_chat_not_session_override(self):
        self.owner.qzone_conf["qzone_auto_comment_image_vision_provider"] = "vision"
        self.context.llm_generate.side_effect = [
            RuntimeError("404"),
            RuntimeError("no image support"),
            types.SimpleNamespace(completion_text="湖面有栈道"),
        ]
        self.assertEqual(
            await self.sight._describe_qzone_image(
                self.owner, self.post.images[0], target_umo="session"
            ),
            "湖面有栈道",
        )
        self.assertEqual(
            [
                c.kwargs["chat_provider_id"]
                for c in self.context.llm_generate.await_args_list
            ],
            ["vision", "ai-config", "first-chat"],
        )

    async def test_photo_readback_accepts_mention_metadata_but_rejects_wrong_body_or_target(
        self,
    ):
        photos = importlib.import_module(f"{CORE_PACKAGE_NAME}.space.photos")
        root = types.SimpleNamespace(tid="root", uin=2)
        target = types.SimpleNamespace(tid="question", uin=3)
        reply = types.SimpleNamespace(comment_id="new", uin=1)
        item = types.SimpleNamespace(
            comment_id="new", uin=1, content="@{uin:3,nick:,who:1} 湖面有栈道"
        )
        service = types.SimpleNamespace(
            query_photo=AsyncMock(
                return_value=types.SimpleNamespace(
                    comments=[
                        types.SimpleNamespace(comment_id="root", uin=2, replies=[item])
                    ]
                )
            )
        )
        for content, expected in (
            (item.content, "confirmed"),
            ("@{uin:4,nick:,who:1} 湖面有栈道", "wrong_target"),
            ("@{uin:3,nick:,who:1} 另一段正文", "wrong_target"),
        ):
            item.content = content
            result = await photos._verify_photo_reply(
                service,
                owner=2,
                album="album",
                pic="pic",
                root=root,
                target=target,
                reply=reply,
                content="@{uin:3,nick:昵称,auto:1} 湖面有栈道",
            )
            self.assertEqual(result["verification_status"], expected)

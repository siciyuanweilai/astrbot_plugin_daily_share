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
            self.post,
            self.post.images[0],
            index=1,
            total=1,
            scope="正文配图",
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

    async def test_join_root_keeps_post_own_floor_and_bots_previous_conversation(self):
        comment = self.models.QzoneComment
        target = comment(
            uin=89761500,
            nickname="四次元未来",
            tid="1",
            raw_tid="1",
            raw_reply_to_tid="1",
            content="没啥好吃的，建议别吃了，还能省钱",
            create_time=100,
        )
        owner_reply = comment(
            uin=897537513,
            nickname="会好起来的",
            tid="1_r_1_897537513",
            raw_tid="1",
            parent_tid="1",
            reply_to_nickname="四次元未来",
            content="@{uin:89761500,nick:四次元未来,auto:1} 测试",
            create_time=500,
        )
        bot_root = comment(
            uin=188852752,
            nickname="李知恬",
            tid="2",
            raw_tid="2",
            raw_reply_to_tid="2",
            content="路口那家转角肠粉好像还没收摊 要不去看一眼",
            create_time=200,
        )
        visitor_reply = comment(
            uin=89761500,
            nickname="四次元未来",
            tid="2_r_1_89761500",
            raw_tid="1",
            parent_tid="2",
            reply_to_nickname="李知恬",
            content="@{uin:188852752,nick:李知恬,auto:1}你请我吃的话，我就去看下",
            create_time=300,
        )
        bot_reply = comment(
            uin=188852752,
            nickname="李知恬",
            tid="2_r_2_188852752",
            raw_tid="2",
            parent_tid="2",
            reply_to_nickname="四次元未来",
            content="@{uin:89761500,nick:四次元未来,auto:1} 想得倒美 肠粉没有 白开水管够",
            create_time=400,
        )
        unrelated = comment(uin=5, tid="3", content="这条不相关的楼不应混入")
        post = self.models.QzonePost(
            uin=897537513,
            name="会好起来的",
            tid="post",
            text="今晚吃啥好呢？大家有推荐吗？",
            comments=[
                target,
                owner_reply,
                bot_root,
                visitor_reply,
                bot_reply,
                unrelated,
            ],
        )
        await self.owner._generate_qzone_auto_reply(
            post, target, as_post_owner=False, self_uin=188852752
        )
        request = self.owner.plugin.call_llm.await_args.kwargs
        prompt = request["prompt"]
        for text in (
            post.text,
            "目标评论楼中已有对话",
            "回复 四次元未来",
            "测试",
            "同一动态的其他相关评论楼",
            "路口那家转角肠粉好像还没收摊",
            "你请我吃的话，我就去看下",
            "想得倒美",
            "肠粉没有",
            "白开水管够",
            "你（Bot）· 李知恬",
            f"对方评论：{target.content}",
        ):
            self.assertIn(text, prompt)
        self.assertNotIn(unrelated.content, prompt)
        self.assertNotIn("@{", prompt)
        own_floor, other_floors = prompt.split("同一动态的其他相关评论楼", 1)
        self.assertNotIn("转角肠粉", own_floor)
        self.assertIn("转角肠粉", other_floors)
        self.assertLess(prompt.index("白开水管够"), prompt.index("对方评论："))
        self.owner.plugin.call_llm.assert_awaited_once()
        self.context.llm_generate.assert_not_awaited()

    async def test_join_reply_preserves_author_situation_and_comment_addressee(self):
        comment = self.models.QzoneComment(
            uin=3,
            nickname="访客",
            tid="visitor",
            content="别睡了，建议直接通宵",
        )
        post = self.models.QzonePost(
            uin=2, name="朋友", tid="night", text="睡不着，咋办？", comments=[comment]
        )
        for appid in (311, 4):
            with self.subTest(appid=appid):
                post.appid = appid
                self.owner.plugin.call_llm.reset_mock()
                await self.owner._generate_qzone_auto_reply(
                    post,
                    comment,
                    as_post_owner=False,
                    self_uin=1,
                    state={
                        "processed": {
                            post.key: {
                                "action": "commented",
                                "content": "先躺一会儿，把手机放远点",
                            }
                        }
                    },
                )
                request = self.owner.plugin.call_llm.await_args.kwargs
                prompt = request["prompt"]
                self.assertIn("你的身份：评论参与者（Bot，QQ：1）", prompt)
                self.assertIn("原评论面向：动态作者 朋友（QQ：2）", prompt)
                self.assertIn("评论人：访客（QQ：3）", prompt)
                self.assertIn(post.text, prompt)
                self.assertIn(comment.content, prompt)
                self.assertIn("先躺一会儿，把手机放远点", prompt)
                self.assertIn(
                    "回应目标评论在当前话题中的意思", request["system_prompt"]
                )
                self.owner.plugin.call_llm.assert_awaited_once()
        self.context.llm_generate.assert_not_awaited()

    async def test_explicit_comment_addressee_overrides_default_post_author(self):
        comment = self.models.QzoneComment(
            uin=3,
            tid="visitor",
            content="你也还没睡？",
        )
        post = self.models.QzonePost(
            uin=2,
            name="朋友",
            tid="night",
            text="睡不着",
            comments=[self.models.QzoneComment(uin=4, nickname="另一位访客")],
        )
        for uin, name, expected in (
            (1, "Bot", "你（Bot，QQ：1）"),
            (2, "", "动态作者 朋友（QQ：2）"),
            (4, "", "另一位访客（QQ：4）"),
            (5, "指定访客", "指定访客（QQ：5）"),
            (0, "仅有昵称", "仅有昵称"),
        ):
            with self.subTest(uin=uin, name=name):
                comment.reply_to_uin = uin
                comment.reply_to_nickname = name
                await self.owner._generate_qzone_auto_reply(
                    post, comment, as_post_owner=False, self_uin=1
                )
                prompt = self.owner.plugin.call_llm.await_args.kwargs["prompt"]
                self.assertIn(f"原评论面向：{expected}", prompt)
                self.assertNotIn("顶层评论，未指定其他回复对象", prompt)

    async def test_post_authors_supplement_is_addressed_to_participants(self):
        comment = self.models.QzoneComment(uin=2, tid="update", content="终于有点困了")
        post = self.models.QzonePost(uin=2, name="朋友", tid="night", text="睡不着")
        await self.owner._generate_qzone_auto_reply(
            post, comment, as_post_owner=False, self_uin=1
        )
        prompt = self.owner.plugin.call_llm.await_args.kwargs["prompt"]
        self.assertIn("原评论面向：评论区参与者（动态作者的补充发言", prompt)
        self.assertNotIn("原评论面向：动态作者", prompt)

    async def test_unknown_nested_addressee_does_not_default_to_post_author(self):
        comment = self.models.QzoneComment(
            uin=3, tid="visitor", parent_tid="missing", content="你也还没睡？"
        )
        post = self.models.QzonePost(uin=2, name="朋友", tid="night", text="睡不着")
        await self.owner._generate_qzone_auto_reply(
            post, comment, as_post_owner=False, self_uin=1
        )
        prompt = self.owner.plugin.call_llm.await_args.kwargs["prompt"]
        self.assertIn("原评论面向：未确认，结合评论楼对话判断", prompt)
        self.assertNotIn("原评论面向：动态作者", prompt)

    async def test_reply_context_bounds_history_and_prioritizes_bot_with_target_user(
        self,
    ):
        comment = self.models.QzoneComment
        target = comment(uin=2, tid="target", content="目标问题")
        own_floor = [
            comment(
                uin=3,
                tid=f"reply{i}",
                parent_tid="target",
                content=f"同楼{i}：" + "长" * 300,
                create_time=i,
            )
            for i in range(10)
        ]
        bot_roots = [
            comment(uin=1, tid=f"bot{i}", content=f"本人楼{i}", create_time=i)
            for i in range(5)
        ]
        actor_reply = comment(
            uin=2, tid="actor", parent_tid="bot0", content="与目标用户的旧对话"
        )
        post = self.models.QzonePost(
            uin=9, tid="post", comments=[target, *own_floor, *bot_roots, actor_reply]
        )
        await self.owner._generate_qzone_auto_reply(
            post, target, as_post_owner=False, self_uin=1
        )
        prompt = self.owner.plugin.call_llm.await_args.kwargs["prompt"]
        self.assertNotIn("同楼3：", prompt)
        self.assertIn("同楼4：", prompt)
        self.assertIn("同楼9：", prompt)
        self.assertNotIn("长" * 121, prompt)
        self.assertEqual(prompt.count("同一动态的其他相关评论楼"), 2)
        self.assertIn("本人楼0", prompt)
        self.assertIn("与目标用户的旧对话", prompt)
        self.assertIn("本人楼4", prompt)
        self.assertNotIn("本人楼3", prompt)

    async def test_own_post_reply_infers_bot_identity_without_extra_queries(self):
        self.post.images = []
        self.post.uin = 1
        self.root.uin = 2
        self.question.uin = 1
        self.question.nickname = "Bot"
        self.post.comments = [self.root, self.question]
        await self.owner._generate_qzone_auto_reply(self.post, self.root)
        prompt = self.owner.plugin.call_llm.await_args.kwargs["prompt"]
        self.assertIn("我的说说", prompt)
        self.assertIn("你（Bot）· Bot", prompt)
        self.owner.plugin.call_llm.assert_awaited_once()

    async def test_album_reply_context_keeps_private_comments_out(self):
        comment = self.models.QzoneComment
        target = comment(uin=2, tid="42", content="照片中的这家店在哪里")
        private_root = comment(
            uin=1, tid="43", content="私密楼内容", raw_fields={"photo_private": 1}
        )
        private_child = comment(
            uin=3,
            tid="44",
            parent_tid="42",
            content="私密回复内容",
            raw_fields={"photo_private": "1"},
        )
        public_child = comment(
            uin=1, tid="45", parent_tid="42", content="之前发过的店名"
        )
        post = self.models.QzonePost(
            uin=9,
            tid="album",
            appid=4,
            comments=[target, private_root, private_child, public_child],
        )
        await self.owner._generate_qzone_auto_reply(
            post, target, as_post_owner=False, self_uin=1
        )
        prompt = self.owner.plugin.call_llm.await_args.kwargs["prompt"]
        self.assertIn("相册照片", prompt)
        self.assertIn(public_child.content, prompt)
        self.assertNotIn(private_root.content, prompt)
        self.assertNotIn(private_child.content, prompt)

    def test_thread_context_resolves_stable_ids_before_colliding_short_aliases(self):
        lineage = importlib.import_module(
            f"{CORE_PACKAGE_NAME}.tasks.interact.text.lineage"
        )
        comment = self.models.QzoneComment
        root1 = comment(tid="1", raw_tid="1", raw_reply_to_tid="1")
        root2 = comment(tid="2", raw_tid="2", raw_reply_to_tid="2")
        child1 = comment(tid="1_r_2_3", raw_tid="2", parent_tid="1")
        child2 = comment(tid="2_r_1_3", raw_tid="1", parent_tid="2")
        nested = comment(tid="nested", parent_tid=child1.tid)
        comments = [root1, child1, root2, child2, nested]
        result = lineage._qzone_same_thread_comments(comments, root1)
        self.assertEqual(
            [item.tid for _index, item in result], [child1.tid, nested.tid]
        )

    def test_thread_context_omits_ambiguous_aliases(self):
        lineage = importlib.import_module(
            f"{CORE_PACKAGE_NAME}.tasks.interact.text.lineage"
        )
        comment = self.models.QzoneComment
        root = comment(tid="root", raw_tid="1")
        other = comment(tid="other", raw_tid="1")
        unknown = comment(tid="child", parent_tid="1")
        self.assertEqual(
            lineage._qzone_same_thread_comments([root, other, unknown], root), []
        )

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
                topic="album_pic_0_0",
                payload={},
            )
            self.assertEqual(result["verification_status"], expected)

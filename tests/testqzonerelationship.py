import asyncio
import importlib
import sys
import types
import unittest
from unittest.mock import AsyncMock

if __package__:
    from .testqzonecomment import (
        CORE_PACKAGE_NAME,
        TASKS_PACKAGE_NAME,
        _load_auto_comment_module,
        _load_qzone_service_module,
    )
else:
    from testqzonecomment import (
        CORE_PACKAGE_NAME,
        TASKS_PACKAGE_NAME,
        _load_auto_comment_module,
        _load_qzone_service_module,
    )


class Platform:
    def __init__(self, name, client, kind="aiocqhttp"):
        self.name = name
        self.client = client
        self.kind = kind

    def meta(self):
        return types.SimpleNamespace(
            id=self.name, name=self.kind, support_proactive_message=True
        )

    def get_client(self):
        return self.client


def qzone_service(platforms, *, adapter="qq-test", cached="", bots=None):
    module, _ = _load_qzone_service_module()
    context = types.SimpleNamespace(
        platform_manager=types.SimpleNamespace(get_insts=lambda: platforms)
    )
    bots = bots if bots is not None else {item.name: item.client for item in platforms}
    ctx_service = types.SimpleNamespace(
        context=context,
        bot_map=bots,
        get_bot_instance=lambda key: bots.get(key),
        get_onebot_bot=lambda **kwargs: None,
        is_onebot_platform=lambda key: key in {"aiocqhttp", "onebot"},
    )
    plugin = types.SimpleNamespace(
        qzone_conf={"qzone_adapter_id": adapter},
        _cached_qq_adapter_id=cached,
        ctx_service=ctx_service,
    )
    return module.QzoneService(plugin)


class QzoneRelationshipRoutingTests(unittest.TestCase):
    def test_selected_client_overrides_cached_other_account(self):
        first, second = object(), object()
        service = qzone_service(
            [Platform("qq-test", first), Platform("qq-other", second)],
            cached="qq-other",
        )
        self.assertEqual(
            service.relationship_target("20002"), "qq-test:FriendMessage:20002"
        )

    def test_cached_and_single_client_routes_use_actual_platform_id(self):
        bot = object()
        service = qzone_service(
            [Platform("custom-qq", bot)], adapter="", cached="custom-qq"
        )
        self.assertEqual(
            service.relationship_target("20002"), "custom-qq:FriendMessage:20002"
        )
        service = qzone_service(
            [Platform("custom-qq", bot)], adapter="", bots={"aiocqhttp": bot}
        )
        self.assertEqual(
            service.relationship_target("20002"), "custom-qq:FriendMessage:20002"
        )

    def test_cross_platform_shared_name_uses_framework_id_not_internal_route(self):
        qq, weixin = object(), object()
        service = qzone_service(
            [Platform("shared", qq), Platform("shared", weixin, "weixin_oc")],
            adapter="aiocqhttp!shared",
            bots={"aiocqhttp!shared": qq, "weixin_oc!shared": weixin},
        )
        self.assertEqual(
            service.relationship_target("20002"), "shared:FriendMessage:20002"
        )

    def test_unavailable_conflicting_or_ambiguous_client_does_not_guess(self):
        bot = object()
        scenarios = [
            qzone_service([Platform("other", bot)]),
            qzone_service([Platform("qq-test", bot), Platform("qq-test", object())]),
            qzone_service([Platform("qq-test", bot), Platform("alias", bot)]),
            qzone_service([Platform("qq-test", bot, "weixin_oc")]),
            qzone_service(
                [Platform("first", bot), Platform("second", object())], adapter=""
            ),
        ]
        for service in scenarios:
            with self.subTest(service=service):
                self.assertEqual(service.relationship_target("20002"), "")

    def test_invalid_actor_id_is_rejected(self):
        service = qzone_service([Platform("qq-test", object())])
        for value in ("", "0", "-2", "abc", "２", "2:FriendMessage:3", "1" * 21):
            with self.subTest(value=value):
                self.assertEqual(service.relationship_target(value), "")


class QzoneRelationshipPromptTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        space = qzone_service([Platform("qq-test", object())])
        module, self.models = _load_auto_comment_module()
        context_module = importlib.import_module(f"{CORE_PACKAGE_NAME}.context")
        self.calls = []
        self.payloads = {
            "qq-test:FriendMessage:20002": self.payload("档案甲", "老朋友", "阿甲"),
            "qq-test:FriendMessage:30003": self.payload("档案乙", "同事", "阿乙"),
        }

        async def get_share_context(target):
            self.calls.append(target)
            await asyncio.sleep(0)
            return self.payloads.get(target, {"weather": "晴"})

        ctx = context_module.ContextService(
            types.SimpleNamespace(),
            {},
            types.SimpleNamespace(get_share_context=get_share_context),
        )
        self.owner = module.TaskQzoneAutoCommentService()
        self.owner.qzone_conf = {}
        self.owner.ctx_service = ctx
        self.owner.plugin = types.SimpleNamespace(
            qzone_service=space,
            call_llm=AsyncMock(return_value="测试回复"),
            basic_conf={},
        )
        self.post = self.models.QzonePost(
            uin=20002, tid="post", name="同名昵称", text="今天看书"
        )
        self.own_post = self.models.QzonePost(
            uin=10001, tid="own", name="我", text="今日随记"
        )
        self.parent = self.models.QzoneComment(
            uin=20002, tid="parent", nickname="同名昵称", content="不错"
        )
        self.child = self.models.QzoneComment(
            uin=30003,
            tid="child",
            parent_tid="parent",
            nickname="同名昵称",
            content="我也觉得",
        )

    @staticmethod
    def payload(name, relation, familiar_name):
        return {
            "weather": "晴" * 1800,
            "relationships": [
                {
                    "name": name,
                    "alias": familiar_name,
                    "subjective_name": familiar_name,
                    "persona_hint": relation,
                    "subjective_tags": [relation],
                    "relationship_story": f"明确关系是{relation}",
                    "notes": [{"content": "PRIVATE_NOTE"}],
                    "memory_points": [{"content": "PRIVATE_MEMORY"}],
                }
            ],
            "chat_summaries": [{"brief": "PRIVATE_CHAT"}],
            "memo": "PRIVATE_MEMO",
            "schedule": "PRIVATE_SCHEDULE",
            "commitments": [{"content": "PRIVATE_COMMITMENT"}],
            "share_guidance": {
                "terms": [{"term": "PRIVATE_TERM", "meaning": "私下称谓"}]
            },
        }

    async def test_all_generation_paths_use_actual_actor_not_triggering_session(self):
        trigger = "admin-bot:GroupMessage:99999"
        await self.owner.generate_qzone_auto_comment(self.post, target_umo=trigger)
        await self.owner._generate_qzone_auto_reply(
            self.own_post, self.child, target_umo=trigger
        )
        await self.owner._generate_qzone_auto_reply_thread(
            self.post, self.parent, self.child, target_umo=trigger
        )
        self.assertEqual(
            self.calls,
            [
                "qq-test:FriendMessage:20002",
                "qq-test:FriendMessage:30003",
                "qq-test:FriendMessage:30003",
            ],
        )
        for index, call in enumerate(self.owner.plugin.call_llm.await_args_list):
            prompt = call.kwargs["prompt"]
            expected, unexpected = (
                ("档案甲", "档案乙") if index == 0 else ("档案乙", "档案甲")
            )
            self.assertIn(expected, prompt)
            self.assertNotIn(unexpected, prompt)
            self.assertIn("【本次互动对象】", prompt)
            self.assertIn("【当前互动对象关系】", prompt)
            self.assertIn("熟悉称呼", prompt)
            self.assertNotIn("PRIVATE_", prompt)
            self.assertLess(
                prompt.index(expected), prompt.index("【当前生活状态参考】")
            )
            # 关系路由独立于用户主动选择的模型/视觉会话，不改变模型配置。
            self.assertEqual(call.kwargs["umo"], trigger)
            self.assertIn(
                "档案姓名与空间昵称不同仍是同一人", call.kwargs["system_prompt"]
            )

    async def test_reply_executor_without_triggering_session_uses_actual_actor(self):
        replyer = sys.modules[f"{TASKS_PACKAGE_NAME}.interact.executors.replyer"]
        task = sys.modules[f"{TASKS_PACKAGE_NAME}.interact.task"]
        self.owner._qzone_send_auto_reply_result = AsyncMock()
        candidates = [
            types.SimpleNamespace(
                post=self.own_post,
                comment=comment,
                parent_comment=self.parent if thread else None,
                item_key=f"test-{index}",
                is_thread_reply=thread,
            )
            for index, (comment, thread) in enumerate(
                [(self.parent, False), (self.child, True)]
            )
        ]
        result = task._qzone_auto_result(replied=0)
        await replyer._execute_qzone_auto_reply_candidates(
            self.owner, candidates, {}, {}, result, limit=2
        )
        self.assertEqual(
            self.calls, ["qq-test:FriendMessage:20002", "qq-test:FriendMessage:30003"]
        )
        self.assertEqual(self.owner._qzone_send_auto_reply_result.await_count, 2)
        self.assertEqual(result["generation_failed"], 0)

    async def test_thread_labels_disambiguate_author_parent_and_current_actor(self):
        self.parent.uin = 40004
        await self.owner._generate_qzone_auto_reply_thread(
            self.post, self.parent, self.child
        )
        prompt = self.owner.plugin.call_llm.await_args.kwargs["prompt"]
        self.assertIn("动态作者：同名昵称（QQ：20002）", prompt)
        self.assertIn("一级评论人：同名昵称（QQ：40004）", prompt)
        self.assertIn("新的二级回复人：同名昵称（QQ：30003）", prompt)
        self.assertNotIn("我的说说：", prompt)
        self.assertEqual(self.calls, ["qq-test:FriendMessage:30003"])

    async def test_missing_actor_id_does_not_reuse_triggering_users_relationship(self):
        self.child.uin = 0
        await self.owner._generate_qzone_auto_reply(
            self.own_post, self.child, target_umo="qq-test:FriendMessage:20002"
        )
        self.assertEqual(self.calls, ["qzone_broadcast"])
        prompt = self.owner.plugin.call_llm.await_args.kwargs["prompt"]
        self.assertIn("QQ：未确认", prompt)
        self.assertIn("未确认关系", prompt)
        self.assertNotIn("档案甲", prompt)

    async def test_concurrent_same_nickname_users_do_not_share_relationship_context(
        self,
    ):
        await asyncio.gather(
            self.owner.generate_qzone_auto_comment(self.post),
            self.owner._generate_qzone_auto_reply(self.own_post, self.child),
        )
        for call in self.owner.plugin.call_llm.await_args_list:
            prompt = call.kwargs["prompt"]
            if "QQ：20002" in prompt:
                self.assertIn("档案甲", prompt)
                self.assertNotIn("档案乙", prompt)
            else:
                self.assertIn("QQ：30003", prompt)
                self.assertIn("档案乙", prompt)
                self.assertNotIn("档案甲", prompt)

    async def test_unresolved_account_discards_broadcast_relationships(self):
        self.owner.plugin.qzone_service = qzone_service(
            [Platform("unrelated", object())]
        )
        self.payloads["qzone_broadcast"] = self.payload("不应使用", "陌生档案", "错人")
        await self.owner.generate_qzone_auto_comment(
            self.post, target_umo="qq-test:FriendMessage:20002"
        )
        self.assertEqual(self.calls, ["qzone_broadcast"])
        prompt = self.owner.plugin.call_llm.await_args.kwargs["prompt"]
        self.assertIn("未确认关系", prompt)
        self.assertNotIn("不应使用", prompt)

    async def test_missing_relationship_uses_neutral_fallback(self):
        self.child.uin = 40004
        await self.owner._generate_qzone_auto_reply(self.own_post, self.child)
        self.assertEqual(self.calls, ["qq-test:FriendMessage:40004"])
        self.assertIn(
            "未确认关系", self.owner.plugin.call_llm.await_args.kwargs["prompt"]
        )

    async def test_disabled_or_unavailable_life_context_does_not_block_reply(self):
        self.owner.ctx_service.life_conf["enable_life_context"] = False
        self.assertEqual(
            await self.owner.generate_qzone_auto_comment(self.post), "测试回复"
        )
        self.assertEqual(self.calls, [])
        self.owner.ctx_service.life_conf["enable_life_context"] = True
        self.owner.ctx_service.daily_life_bridge.get_share_context = AsyncMock(
            side_effect=RuntimeError("unavailable")
        )
        self.assertEqual(
            await self.owner._generate_qzone_auto_reply(self.own_post, self.child),
            "测试回复",
        )
        self.assertIn(
            "未确认关系", self.owner.plugin.call_llm.await_args.kwargs["prompt"]
        )

    async def test_group_or_empty_scope_never_requests_global_relationships(self):
        for target in ("", "qq-test:GroupMessage:123", "invalid"):
            self.payloads["qzone_broadcast"] = self.payload("不应使用", "错人", "错人")
            result = await self.owner.ctx_service.get_qzone_interaction_context(target)
            self.assertEqual(result["relationship_context"], "")
        self.assertEqual(self.calls, ["qzone_broadcast"] * 3)

    async def test_ambiguous_profiles_are_not_assigned_to_actor(self):
        payload = self.payloads["qq-test:FriendMessage:20002"]
        payload["relationships"].append({"name": "另一个人", "persona_hint": "同事"})
        await self.owner.generate_qzone_auto_comment(self.post)
        prompt = self.owner.plugin.call_llm.await_args.kwargs["prompt"]
        self.assertIn("未确认关系", prompt)
        self.assertNotIn("档案甲", prompt)

    async def test_relationship_fields_are_bounded_independently_of_life_context(self):
        relation = self.payloads["qq-test:FriendMessage:20002"]["relationships"][0]
        for key in (
            "name",
            "alias",
            "subjective_name",
            "persona_hint",
            "relationship_story",
        ):
            relation[key] = "x" * 10000
        relation["subjective_tags"] = ["x" * 10000] * 100
        result = await self.owner.ctx_service.get_qzone_interaction_context(
            "qq-test:FriendMessage:20002"
        )
        self.assertLess(len(result["relationship_context"]), 800)
        self.assertNotIn("PRIVATE_", str(result))

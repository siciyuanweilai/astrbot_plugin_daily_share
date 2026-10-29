import importlib.util
import time
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from . import testpermission, testqzonedashboard
from .testqzone import _load_qzone_host, _load_qzone_service, _new_qzone_service


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "daily_share_mentions_test", ROOT / "core" / "space" / "mentions.py"
)
MENTIONS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MENTIONS)
FRIENDS = [{"uin": "10001", "nick": "好友甲"}, {"uin": "10002", "nick": "好友 乙"}]
EXPECTED = "今天出游\n@{uin:10001,nick:好友甲} @{uin:10002,nick:好友 乙}"


class MentionTextTests(unittest.TestCase):
    def test_explicit_friends_are_appended_once_in_order(self):
        self.assertEqual(
            MENTIONS.qzone_publish_text("今天出游", FRIENDS + FRIENDS), EXPECTED
        )

    def test_without_mentions_preserves_text_exactly(self):
        content = "  正文\n@{uin:10001,nick:好友甲,who:1}  "
        self.assertEqual(MENTIONS.qzone_publish_text(content), content)
        self.assertEqual(MENTIONS.qzone_publish_text(content, []), content)

    def test_inline_mention_is_preserved_and_deduplicated_by_uin(self):
        content = "一起去 @{uin:10001,nick:旧昵称,who:1} 玩吧"
        self.assertEqual(
            MENTIONS.qzone_publish_text(content, FRIENDS),
            content + "\n@{uin:10002,nick:好友 乙}",
        )

    def test_mention_only_post_and_numeric_uin(self):
        self.assertEqual(
            MENTIONS.qzone_publish_text("", [{"uin": 10001, "nick": " 好友甲 "}]),
            "@{uin:10001,nick:好友甲}",
        )

    def test_plain_at_name_does_not_count_as_structured_mention(self):
        self.assertEqual(
            MENTIONS.qzone_publish_text("@好友甲", FRIENDS[:1]),
            "@好友甲\n@{uin:10001,nick:好友甲}",
        )

    def test_rejects_invalid_identity_and_marker_injection(self):
        invalid = [
            "10001 好友甲",
            {},
            ["10001 好友甲"],
            [{"uin": True, "nick": "好友甲"}],
            [{"uin": 1.1, "nick": "好友甲"}],
            [{"uin": "0", "nick": "好友甲"}],
            [{"uin": "010001", "nick": "好友甲"}],
            [{"uin": "１２３４５", "nick": "好友甲"}],
            [{"uin": "1" * 21, "nick": "好友甲"}],
            [{"uin": "10001", "nick": ""}],
            [{"uin": "10001", "nick": None}],
            [{"uin": "10001", "nick": "好友,who:1"}],
            [{"uin": "10001", "nick": "好友}@{uin:10002,nick:其他好友"}],
            [{"uin": "10001", "nick": "好友\n甲"}],
            [{"uin": "10001", "nick": "好友甲\x00"}],
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                MENTIONS.qzone_publish_text("测试", value)

    def test_confirmation_ignores_server_metadata_but_keeps_target(self):
        normalize = MENTIONS.normalized_qzone_publish_text
        rewritten = "今天出游\n@{uin:10001,nick:改名,who:1} @{uin:10002,nick:好友 乙,auto:1,who:1}"
        self.assertEqual(normalize(EXPECTED), normalize(rewritten))
        self.assertNotEqual(
            normalize(EXPECTED), normalize(rewritten.replace("uin:10002", "uin:10003"))
        )


class MentionPublishTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.module = _load_qzone_service()
        self.service = _new_qzone_service(self.module)
        self.service.context = AsyncMock(
            return_value=self.module.QzoneContext(100000001, "skey", "p_skey")
        )
        self.service._submit_post = AsyncMock(return_value={"code": 0, "tid": "test"})
        self.service._upload_image = AsyncMock(return_value=("picbo", "richval"))
        self.service.self_post.schedule = Mock()

    async def test_service_publishes_mentions_with_images_without_changing_visibility(
        self,
    ):
        post = await self.service.publish_post(
            text="今天出游", images=[b"image"], mentions=FRIENDS
        )
        data = self.service._submit_post.await_args.args[1]
        self.assertEqual(data["con"], EXPECTED)
        self.assertEqual(data["pic_bo"], "picbo")
        self.assertEqual(data["richval"], "richval")
        self.assertEqual(data["ugc_right"], "1")
        self.assertNotIn("allow_uins", data)
        self.assertEqual(post.text, EXPECTED)
        self.service._submit_post.assert_awaited_once()

    async def test_invalid_friend_fails_before_login_or_image_upload(self):
        with self.assertRaises(ValueError):
            await self.service.publish_post(
                text="测试", images=[b"image"], mentions=[{"uin": "10001"}]
            )
        self.service.context.assert_not_awaited()
        self.service._upload_image.assert_not_awaited()
        self.service._submit_post.assert_not_awaited()

    async def test_timeout_confirms_rewritten_marker_without_resubmitting(self):
        post = self.module.QzonePost(
            tid="existing",
            uin=100000001,
            text=EXPECTED.replace("nick:好友甲}", "nick:新昵称,who:1}"),
            create_time=int(time.time()),
        )
        self.service._submit_post.side_effect = RuntimeError("timeout")
        self.service.query_posts = AsyncMock(return_value=[post])
        with patch.object(self.module.asyncio, "sleep", new=AsyncMock()):
            result = await self.service.publish_post(text="今天出游", mentions=FRIENDS)
        self.assertIs(result, post)
        self.service._submit_post.assert_awaited_once()
        self.service.self_post.schedule.assert_called_once()

    async def test_timeout_does_not_accept_a_different_mentioned_friend(self):
        post = self.module.QzonePost(
            tid="other",
            uin=100000001,
            text=EXPECTED.replace("uin:10002", "uin:10003"),
            create_time=int(time.time()),
        )
        self.service._submit_post.side_effect = RuntimeError("timeout")
        self.service.query_posts = AsyncMock(return_value=[post])
        with patch.object(self.module.asyncio, "sleep", new=AsyncMock()):
            with self.assertRaises(self.module.QzonePublishUnknownError):
                await self.service.publish_post(text="今天出游", mentions=FRIENDS)
        self.service._submit_post.assert_awaited_once()
        self.service.self_post.schedule.assert_not_called()


class MentionDashboardTests(unittest.IsolatedAsyncioTestCase):
    async def test_panel_publishes_and_records_the_same_mention_text(self):
        plugin = testqzonedashboard.DashboardQzonePublishTests()._plugin(
            {"text": "今天出游", "mentions": FRIENDS}
        )
        result = await plugin.qzone_publish.page_qzone_publish()
        self.assertTrue(result["ok"])
        self.assertEqual(plugin.qzone_service.calls[0]["text"], EXPECTED)
        self.assertEqual(plugin.db.history[0][0][2], EXPECTED)

    async def test_panel_accepts_mention_only_post(self):
        plugin = testqzonedashboard.DashboardQzonePublishTests()._plugin(
            {"mentions": FRIENDS[:1]}
        )
        result = await plugin.qzone_publish.page_qzone_publish()
        self.assertTrue(result["ok"])
        self.assertEqual(
            plugin.qzone_service.calls[0]["text"], "@{uin:10001,nick:好友甲}"
        )

    async def test_panel_rejects_invalid_mentions_before_publish(self):
        plugin = testqzonedashboard.DashboardQzonePublishTests()._plugin(
            {"text": "测试", "mentions": [{"uin": "10001", "nick": "错误,昵称"}]}
        )
        result = await plugin.qzone_publish.page_qzone_publish()
        self.assertFalse(result["ok"])
        self.assertEqual(plugin.qzone_service.calls, [])
        self.assertEqual(plugin.db.history, [])

    async def test_panel_publish_cleans_qzone_post_before_adding_mentions(self):
        plugin = testqzonedashboard.DashboardQzonePublishTests()._plugin(
            {"text": "面板正文，带有标点。", "mentions": FRIENDS[:1]}
        )
        bridge = types.SimpleNamespace(
            clean_expression_punctuation=AsyncMock(return_value="清洗后的面板正文")
        )
        plugin.plugin = types.SimpleNamespace(daily_life_bridge=bridge)

        result = await plugin.qzone_publish.page_qzone_publish()

        self.assertTrue(result["ok"])
        self.assertEqual(
            plugin.qzone_service.calls[0]["text"],
            "清洗后的面板正文\n@{uin:10001,nick:好友甲}",
        )
        bridge.clean_expression_punctuation.assert_awaited_once_with(
            "面板正文，带有标点。", scene="qzone_post"
        )


class MentionHostTests(unittest.IsolatedAsyncioTestCase):
    async def test_login_retry_preserves_mentions_and_images_without_duplicates(self):
        module = _load_qzone_host()
        post = types.SimpleNamespace(tid="", text=EXPECTED)
        service = types.SimpleNamespace(
            context=AsyncMock(
                return_value=types.SimpleNamespace(nickname="测试账号", uin=100000001)
            ),
            publish_post=AsyncMock(side_effect=[RuntimeError("Cookie 失效"), post]),
            invalidate=Mock(),
        )
        host = module.PluginQzoneService(
            types.SimpleNamespace(plugin=types.SimpleNamespace(), qzone_service=service)
        )
        result = await host.publish_qzone(
            text="今天出游", images=[b"image"], mentions=FRIENDS
        )
        self.assertIs(result, post)
        service.invalidate.assert_called_once_with()
        self.assertEqual(service.publish_post.await_count, 2)
        for call in service.publish_post.await_args_list:
            self.assertEqual(call.kwargs, {"text": EXPECTED, "images": [b"image"]})

    async def test_invalid_mentions_do_not_attempt_login_or_publish(self):
        module = _load_qzone_host()
        service = types.SimpleNamespace(context=AsyncMock(), publish_post=AsyncMock())
        host = module.PluginQzoneService(types.SimpleNamespace(qzone_service=service))
        with self.assertRaises(ValueError):
            await host.publish_qzone(mentions=[{"uin": "10001"}])
        service.context.assert_not_awaited()
        service.publish_post.assert_not_awaited()

    async def test_public_plugin_api_passes_mentions_through_support_service(self):
        from .testmedia import _load_main_module, _new_plugin_with_support

        module = _load_main_module()
        plugin = _new_plugin_with_support(module)
        post = types.SimpleNamespace(tid="", text=EXPECTED)
        plugin.qzone_service = types.SimpleNamespace(
            context=AsyncMock(
                return_value=types.SimpleNamespace(nickname="测试账号", uin=100000001)
            ),
            publish_post=AsyncMock(return_value=post),
        )
        result = await plugin.publish_qzone(
            text="今天出游", images=[b"image"], mentions=FRIENDS
        )
        self.assertIs(result, post)
        plugin.qzone_service.publish_post.assert_awaited_once_with(
            text=EXPECTED, images=[b"image"]
        )

    async def test_public_plugin_api_cleans_qzone_post_before_publish(self):
        module = _load_qzone_host()
        post = types.SimpleNamespace(tid="", text="清洗后的正文")
        bridge = types.SimpleNamespace(
            clean_expression_punctuation=AsyncMock(return_value="清洗后的正文")
        )
        service = types.SimpleNamespace(
            context=AsyncMock(
                return_value=types.SimpleNamespace(nickname="测试账号", uin=100000001)
            ),
            publish_post=AsyncMock(return_value=post),
        )
        host = module.PluginQzoneService(
            types.SimpleNamespace(
                plugin=types.SimpleNamespace(daily_life_bridge=bridge),
                qzone_service=service,
            )
        )

        result = await host.publish_qzone(text="正文，带有标点。")

        self.assertIs(result, post)
        service.publish_post.assert_awaited_once_with(
            text="清洗后的正文", images=[]
        )
        bridge.clean_expression_punctuation.assert_awaited_once_with(
            "正文，带有标点。", scene="qzone_post"
        )


class MentionToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        fixture = testpermission.QzoneToolPermissionTests()
        fixture.setUp()
        self.host = fixture.host
        self.host.qzone_service.publish_post = AsyncMock(
            return_value=testpermission._QzonePost(uin=100000303, text=EXPECTED)
        )
        self.host.db.add_sent_history = AsyncMock()

    async def test_admin_tool_passes_mentions_through_dispatch(self):
        result = await self.host.run_qzone_tool(
            testpermission._Event(role="admin"),
            action="publish",
            content="今天出游",
            mentions=FRIENDS,
        )
        self.assertIn("已发布 QQ 空间说说", result)
        self.host.qzone_service.publish_post.assert_awaited_once_with(
            text=EXPECTED, images=[]
        )
        self.assertEqual(self.host.db.add_sent_history.await_args.args[2], EXPECTED)

    async def test_llm_publish_cleans_qzone_post_before_adding_mentions(self):
        bridge = types.SimpleNamespace(
            clean_expression_punctuation=AsyncMock(return_value="清洗后的正文")
        )
        self.host.runtime.plugin = types.SimpleNamespace(daily_life_bridge=bridge)
        result = await self.host.run_qzone_tool(
            testpermission._Event(role="admin"),
            action="publish",
            content="模型生成的正文，带有标点。",
            mentions=FRIENDS[:1],
        )
        self.assertIn("已发布 QQ 空间说说", result)
        self.host.qzone_service.publish_post.assert_awaited_once_with(
            text="清洗后的正文\n@{uin:10001,nick:好友甲}", images=[]
        )
        bridge.clean_expression_punctuation.assert_awaited_once_with(
            "模型生成的正文，带有标点。", scene="qzone_post"
        )

    async def test_member_cannot_publish_with_mentions(self):
        result = await self.host.run_qzone_tool(
            testpermission._Event(role="member"),
            action="publish",
            content="今天出游",
            mentions=FRIENDS,
        )
        self.assertIn("仅管理员可用", result)
        self.host.qzone_service.publish_post.assert_not_awaited()

    async def test_mentions_on_comment_are_rejected_before_mutation(self):
        result = await self.host.run_qzone_tool(
            testpermission._Event(role="admin"),
            action="comment",
            post_id="10001:tid-1",
            content="测试",
            mentions=FRIENDS,
        )
        self.assertIn("mentions 仅用于发布说说", result)
        self.assertEqual(self.host.qzone_service.calls, [])

    async def test_invalid_mentions_never_submit(self):
        result = await self.host.run_qzone_tool(
            testpermission._Event(role="admin"),
            action="publish",
            content="测试",
            mentions=[{"uin": "10001", "nick": "错误,昵称"}],
        )
        self.assertIn("昵称不能为空", result)
        self.host.qzone_service.publish_post.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

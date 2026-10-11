import sys
import unittest
from unittest.mock import AsyncMock

from .testprefix import CONFIG_MODULE_NAME, _service


class ChatShareExpressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_types_review_body_before_prefix_for_both_audiences(self):
        service = _service("【蜂蜜】【电脑】原始正文")
        config = sys.modules[CONFIG_MODULE_NAME]
        service.basic_conf["share_output_format"] = "保留标题，正文一段"
        service.daily_life_bridge.get_share_chat_style_prompt = AsyncMock(
            return_value="【daily_life 聊天表达参考】轻松自然，不凑感悟。"
        )
        service.daily_life_bridge.prepare_expression = AsyncMock(
            return_value={"text": "【蜂蜜】【电脑】自然分享正文"}
        )
        for is_group in (False, True):
            for stype in config.ShareType:
                with self.subTest(is_group=is_group, stype=stype):
                    result = await service.generate(
                        stype,
                        config.TimePeriod.AFTERNOON,
                        "bot:GroupMessage:1" if is_group else "bot:FriendMessage:1",
                        is_group,
                        "当前在休息",
                        news_data=(
                            [{"title": "新闻", "description": "真实资料"}],
                            "zhihu",
                        ),
                        recent_dynamics="历史文艺长文不得成为表达示例",
                    )
                    scene = "share_group" if is_group else "share_private"
                    service.daily_life_bridge.get_share_chat_style_prompt.assert_awaited_with(
                        scene=scene
                    )
                    call = service.daily_life_bridge.prepare_expression.await_args
                    self.assertEqual(call.args, ("【蜂蜜】【电脑】原始正文",))
                    self.assertEqual(call.kwargs["scene"], scene)
                    self.assertEqual(
                        call.kwargs["requirements"]["target_umo"],
                        "bot:GroupMessage:1" if is_group else "bot:FriendMessage:1",
                    )
                    self.assertIn(
                        "保留标题，正文一段",
                        call.kwargs["requirements"]["output_format"],
                    )
                    self.assertEqual(
                        call.kwargs["requirements"]["share_type"], stype.value
                    )
                    self.assertIn(
                        "【蜂蜜】", call.kwargs["requirements"]["required_terms"]
                    )
                    prompt = service.llm_calls[-1]["prompt"]
                    self.assertIn("轻松自然，不凑感悟", prompt)
                    self.assertNotIn("历史文艺长文", prompt)
                    self.assertIn("自然分享正文", result)
                    if stype == config.ShareType.KNOWLEDGE:
                        self.assertTrue(result.startswith("知识类型:"))
                    elif stype == config.ShareType.RECOMMENDATION:
                        self.assertTrue(result.startswith("推荐类型:"))
        self.assertEqual(service.daily_life_bridge.prepare_expression.await_count, 10)

    async def test_review_keeps_titles_layout_and_original_on_failure(self):
        service = _service("")
        original = "【蜂蜜】\n不是所有人都适合。"
        ctx = {"is_group": True, "output_format_hint": "标题与正文分行"}
        review = AsyncMock()
        service.daily_life_bridge.prepare_expression = review
        for response in (
            None,
            {},
            {"text": ["非法类型"]},
            {"text": "改掉了标题"},
            {"text": "【蜂蜜】合并为一行"},
        ):
            with self.subTest(response=response):
                review.return_value = response
                self.assertEqual(
                    await service.support._review_share_expression(original, ctx),
                    original,
                )
        review.side_effect = TimeoutError()
        self.assertEqual(
            await service.support._review_share_expression(original, ctx), original
        )

    async def test_final_dedup_uses_reviewed_body_and_only_supplied_target_history(
        self,
    ):
        service = _service("未经润色的旧表达")
        config = sys.modules[CONFIG_MODULE_NAME]
        service.daily_life_bridge.prepare_expression = AsyncMock(
            return_value={"text": "歇会儿。"}
        )
        for history, expected in (
            (["歇会儿。"], None),
            (["另一个对象的不同内容"], "歇会儿。"),
        ):
            result = await service.generate(
                config.ShareType.MOOD,
                config.TimePeriod.AFTERNOON,
                "bot:FriendMessage:1",
                False,
                "休息中",
                recent_post_contents=history,
            )
            self.assertEqual(result, expected)
        self.assertEqual(len(service.llm_calls), 2)

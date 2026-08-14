import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _tool_docstring(function_name: str) -> str:
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == function_name:
            return ast.get_docstring(node) or ""
    raise AssertionError(f"missing tool function: {function_name}")


def _args_from_docstring(docstring: str) -> dict:
    return dict(
        re.findall(
            r"^\s+([A-Za-z_][A-Za-z0-9_]*) \((string|boolean|number|object|array)\):",
            docstring,
            flags=re.MULTILINE,
        )
    )


class LlmToolDocstringTests(unittest.TestCase):
    def test_daily_share_tool_declares_astrbot_args(self):
        args = _args_from_docstring(_tool_docstring("daily_share_tool"))

        self.assertEqual(
            args,
            {
                "share_type": "string",
                "source": "string",
                "get_image": "boolean",
                "need_image": "boolean",
                "need_video": "boolean",
                "need_voice": "boolean",
                "to_qzone": "boolean",
            },
        )

    def test_news_link_tool_declares_astrbot_args(self):
        args = _args_from_docstring(_tool_docstring("news_link_tool"))

        self.assertEqual(
            args,
            {
                "action": "string",
                "index": "string",
                "query": "string",
                "source": "string",
                "source_explicit": "boolean",
                "to_qzone": "boolean",
            },
        )

    def test_qzone_auto_interact_tool_declares_astrbot_args(self):
        args = _args_from_docstring(_tool_docstring("qzone_auto_interact_tool"))

        self.assertEqual(args, {"action": "string", "target_id": "string"})

    def test_qzone_tool_docstring_separates_friend_thread_and_bot_reply(self):
        qzone_doc = _tool_docstring("qzone_tool")
        auto_doc = _tool_docstring("qzone_auto_interact_tool")

        self.assertIn("动作选择：list=获取最新列表", qzone_doc)
        self.assertIn("comment=直发用户给出的原话", qzone_doc)
        self.assertIn("auto_comment=让机器人按自动评论配置代写", qzone_doc)
        self.assertIn("正文配图和转发配图", qzone_doc)
        self.assertIn("用户说“我的说说”指当前说话用户的 QQ 空间", qzone_doc)
        self.assertIn("qzone_auto_interact.comment", qzone_doc)
        self.assertIn("qzone_auto_interact.reply", qzone_doc)
        self.assertIn("普通用户只能查看、详情、点赞、评论自己 QQ 号的说说", qzone_doc)
        self.assertIn("动作选择：like=自动点赞", auto_doc)
        self.assertIn("单条说说固定评论用 qzone.comment", auto_doc)
        self.assertIn("单条说说自动生成一级评论用 qzone.auto_comment", auto_doc)
        self.assertIn("用户说“我的说说”时 target_id 填该用户 QQ", auto_doc)
        self.assertIn("reply 只在明确指向", auto_doc)
        self.assertIn("机器人自己说说", auto_doc)

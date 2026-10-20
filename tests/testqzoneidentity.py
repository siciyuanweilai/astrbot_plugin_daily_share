"""跨接口评论合并必须保留作者、评论楼和一级评论身份。"""

import importlib
import unittest

from .testqzone import _load_qzone_service


class CommentIdentityTests(unittest.TestCase):
    def setUp(self):
        self.service = _load_qzone_service().QzoneService
        self.parser = importlib.import_module(
            f"{self.service.__module__.rsplit('.', 1)[0]}.parser"
        )

    def test_reply_button_self_target_is_not_a_root_reply(self):
        root = self.parser.parse_comments(
            [
                {
                    "tid": 1,
                    "uin": 89761500,
                    "content": "没啥好吃的",
                    "html": '<a data-param="t2_tid=1&amp;t2_uin=89761500">回复</a>',
                }
            ]
        )[0]
        self.assertEqual(
            (root.parent_tid, root.reply_to_tid, root.reply_to_uin), ("", "", 0)
        )
        self.assertEqual(
            (root.raw_reply_to_tid, root.raw_reply_to_uin), ("1", 89761500)
        )

    def test_nested_reply_keeps_target_with_same_short_id_and_author(self):
        comments = self.parser.parse_comments(
            [
                {
                    "tid": 1,
                    "uin": 89761500,
                    "content": "原评论",
                    "list_3": [
                        {
                            "tid": 1,
                            "uin": 89761500,
                            "content": "补充一句",
                            "html": '<a data-param="t2_tid=1&t2_uin=89761500">回复</a>',
                        }
                    ],
                }
            ]
        )
        self.assertEqual(comments[1].parent_tid, "1")
        self.assertEqual(
            (comments[1].reply_to_tid, comments[1].reply_to_uin), ("1", 89761500)
        )

    def test_merge_does_not_turn_root_into_reply_with_same_submit_id(self):
        base = self.parser.parse_comments(
            [{"tid": 1, "uin": 89761500, "content": "原评论"}]
        )
        detail = self.parser.parse_comments(
            [
                {
                    "tid": 2,
                    "uin": 188852752,
                    "content": "Bot 评论",
                    "list_3": [{"tid": 1, "uin": 89761500, "content": "回复 Bot"}],
                }
            ]
        )
        merged = self.service._merge_comments(base, detail)
        self.assertEqual(len(merged), 3)
        self.assertEqual((merged[0].parent_tid, merged[0].content), ("", "原评论"))

    def test_merge_keeps_identical_replies_in_different_threads_separate(self):
        def thread(root_id):
            return self.parser.parse_comments(
                [
                    {
                        "tid": root_id,
                        "uin": 188852752,
                        "content": f"评论 {root_id}",
                        "list_3": [{"tid": 1, "uin": 89761500, "content": "哈哈"}],
                    }
                ]
            )

        merged = self.service._merge_comments(thread(2), thread(3))
        self.assertEqual(len(merged), 4)
        self.assertEqual(
            {c.parent_tid for c in merged if c.uin == 89761500}, {"2", "3"}
        )

    def test_merge_preserves_replies_when_detail_uses_real_root_ids(self):
        base = self.parser.parse_comments(
            [
                {
                    "tid": 1,
                    "uin": 89761500,
                    "content": "原评论",
                    "list_3": [{"tid": 1, "uin": 188852752, "content": "Bot 回评"}],
                }
            ]
        )
        detail = self.parser.parse_comments(
            [
                {
                    "commentid": "root-real",
                    "uin": 89761500,
                    "content": "原评论",
                    "list_3": [
                        {
                            "commentid": "reply-real",
                            "uin": 188852752,
                            "content": "Bot 回评",
                        }
                    ],
                }
            ]
        )
        merged = self.service._merge_comments(base, detail)
        self.assertEqual(len(merged), 2)
        self.assertEqual(
            (merged[1].parent_tid, merged[1].submit_tid), ("1", "reply-real")
        )

    def test_new_detail_reply_stays_attached_to_existing_root(self):
        base = self.parser.parse_comments(
            [{"tid": 1, "uin": 89761500, "content": "原评论"}]
        )
        detail = self.parser.parse_comments(
            [
                {
                    "commentid": "root-real",
                    "uin": 89761500,
                    "content": "原评论",
                    "list_3": [
                        {
                            "commentid": "reply-real",
                            "uin": 188852752,
                            "content": "Bot 回评",
                        }
                    ],
                }
            ]
        )
        merged = self.service._merge_comments(base, detail)
        self.assertEqual(len(merged), 2)
        self.assertEqual((merged[1].parent_tid, merged[1].reply_to_tid), ("1", "1"))


if __name__ == "__main__":
    unittest.main()

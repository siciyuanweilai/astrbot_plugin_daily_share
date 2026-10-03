"""Photo targets must not confuse upload metadata with per-photo identities."""

import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock
from urllib.parse import quote

from .testqzone import _load_qzone_service, _new_qzone_service, _parser
from .testqzonephotoauto import album_feed, parse_feed


def batch_feed_html():
    return (Path(__file__).parent / "fixtures/qzone_album_batch_feed.html").read_text()


def upload_feed_html():
    # Feed markup reproduces the logged topic shape; identifiers are synthetic.
    return (Path(__file__).parent / "fixtures/qzone_album_upload_feed.html").read_text()


class PhotoTargetParsingTests(unittest.TestCase):
    def test_numeric_batch_topic_resolves_actual_photo_not_upload_subid(self):
        post = parse_feed(album_feed(photos=[], html=upload_feed_html()))
        self.assertEqual(len(post.photo_targets), 3)
        self.assertEqual(
            {photo.pic_key for photo in post.photo_targets},
            {f"pic-{index}!!" for index in range(1, 4)},
        )
        self.assertEqual({photo.album_id for photo in post.photo_targets}, {"album-1"})
        for photo in post.photo_targets:
            self.assertEqual(photo.batch_id, "1790992589220000")
            self.assertEqual(photo.platform_sub_id, 4)
            self.assertEqual(photo.feed_topic_id, "album-1_pic-1!!_1790992589220000_4")
            self.assertIn(
                "topicId", replace(post, photo_targets=[photo]).comment_target_error
            )

    def test_numeric_batch_topic_works_with_feedinfo_html_parser(self):
        post = _parser().parse_feedinfo_html(upload_feed_html())
        self.assertEqual(post.appid, 4)
        self.assertEqual(len(post.photo_targets), 3)
        self.assertNotIn(
            "1790992589220000", {photo.pic_key for photo in post.photo_targets}
        )

    def test_numeric_batch_topic_preserves_underscores_in_album_and_photo(self):
        for topic in (
            "album_with_underscores_pic_with_underscores!!_1790992589220000_4",
            quote(
                "album_with_underscores_pic_with_underscores!!_1790992589220000_4",
                safe="",
            ),
        ):
            with self.subTest(topic=topic):
                post = parse_feed(
                    album_feed(
                        photos=[],
                        html=(
                            '<div class="f-info">Upload</div>'
                            '<i name="feed_data" data-tid="album_with_underscores" '
                            'data-subid="1790992589220000" '
                            f'data-topicid="{topic}"></i>'
                        ),
                    )
                )
                self.assertEqual(len(post.photo_targets), 1)
                photo = post.photo_targets[0]
                self.assertEqual(photo.album_id, "album_with_underscores")
                self.assertEqual(photo.pic_key, "pic_with_underscores!!")
                self.assertEqual(photo.batch_id, "1790992589220000")
                self.assertEqual(photo.platform_sub_id, 4)
                self.assertIn("topicId", post.comment_target_error)

    def test_numeric_topic_link_can_derive_album_from_explicit_photo_key(self):
        post = parse_feed(
            album_feed(
                photos=[],
                html=(
                    '<a href="https://h5.qzone.qq.com/page/photo?'
                    "topicId=album_with_underscores_pic_key!!_1790992589220000_4"
                    '&amp;picKey=pic_key!!">Photo</a>'
                ),
            )
        )
        self.assertEqual(len(post.photo_targets), 1)
        self.assertEqual(post.photo_targets[0].album_id, "album_with_underscores")
        self.assertEqual(post.photo_targets[0].pic_key, "pic_key!!")

    def test_json_and_html_duplicate_keeps_batch_topic_metadata(self):
        post = parse_feed(
            album_feed(
                photos=[
                    {"albumId": "album-1", "picKey": f"pic-{index}!!"}
                    for index in range(1, 4)
                ],
                html=upload_feed_html(),
            )
        )
        self.assertEqual(len(post.photo_targets), 3)
        for photo in post.photo_targets:
            self.assertEqual(photo.batch_id, "1790992589220000")
            self.assertEqual(photo.platform_sub_id, 4)

    def test_duplicate_metadata_does_not_hide_explicit_batch_or_platform_conflict(self):
        for extra in ({"batchId": "another-batch"}, {"platformSubId": 0}):
            with self.subTest(extra=extra):
                post = parse_feed(
                    album_feed(
                        photos=[{"albumId": "album-1", "picKey": "pic-1!!", **extra}],
                        html=upload_feed_html(),
                    )
                )
                photo = post.photo_targets[0]
                if "batchId" in extra:
                    self.assertEqual(photo.batch_id, "another-batch")
                else:
                    self.assertEqual(photo.platform_sub_id, 0)
                self.assertIn(
                    "topicId", replace(post, photo_targets=[photo]).comment_target_error
                )

    def test_unknown_upload_suffix_is_not_normalized_as_a_photo_topic(self):
        for suffix in ("0_4", "batch_4", "1790992589220000_52", "1790992589220000_0"):
            with self.subTest(suffix=suffix):
                topic = f"album-1_pic-1!!_{suffix}"
                post = parse_feed(
                    album_feed(
                        photos=[
                            {
                                "albumId": "album-1",
                                "picKey": "pic-1!!",
                                "topicId": topic,
                            }
                        ]
                    )
                )
                self.assertEqual(post.photo_targets[0].feed_comment_topic_id, topic)
                self.assertEqual(post.photo_targets[0].batch_id, "")
                self.assertIn("topicId", post.comment_target_error)

    def test_unknown_link_suffix_is_not_mistaken_for_a_pure_album_id(self):
        for suffix in ("0_4", "batch_4", "1790992589220000_52"):
            with self.subTest(suffix=suffix):
                topic = f"album-1_pic-1!!_{suffix}"
                post = parse_feed(
                    album_feed(
                        photos=[],
                        html=(
                            '<a href="https://h5.qzone.qq.com/page/photo?'
                            f'topicId={topic}&amp;picKey=pic-1!!">Photo</a>'
                        ),
                    )
                )
                self.assertEqual(len(post.photo_targets), 1)
                self.assertEqual(post.photo_targets[0].album_id, "album-1")
                self.assertEqual(post.photo_targets[0].feed_topic_id, topic)
                self.assertIn("topicId", post.comment_target_error)

    def test_batch_subid_does_not_create_a_fourth_photo_target(self):
        post = parse_feed(album_feed(photos=[], html=batch_feed_html()))
        self.assertEqual(len(post.photo_targets), 3)
        self.assertEqual(
            {photo.pic_key for photo in post.photo_targets},
            {f"pic-{index}!!" for index in range(1, 4)},
        )
        for photo in post.photo_targets:
            self.assertEqual(
                replace(post, photo_targets=[photo]).comment_target_error, ""
            )
            self.assertEqual(
                photo.feed_comment_topic_id, f"album-1_{photo.pic_key}_0_0"
            )
        self.assertIn("多个照片", post.comment_target_error)

    def test_feedinfo_html_parser_uses_the_same_photo_binding(self):
        post = _parser().parse_feedinfo_html(batch_feed_html())
        self.assertEqual(post.appid, 4)
        self.assertEqual(len(post.photo_targets), 3)
        self.assertNotIn("batch-1", {photo.pic_key for photo in post.photo_targets})

    def test_photo_links_with_shared_topic_keep_their_explicit_album(self):
        html = batch_feed_html()
        for index in (2, 3):
            html = html.replace(
                f"topicId=album-1_pic-{index}!!_0_0",
                "topicId=album-1_pic-1!!_0_0",
            )
        post = parse_feed(album_feed(photos=[], html=html))
        self.assertEqual(len(post.photo_targets), 3)
        self.assertEqual({photo.album_id for photo in post.photo_targets}, {"album-1"})
        self.assertEqual(
            {photo.feed_topic_id for photo in post.photo_targets},
            {"album-1_pic-1!!_0_0"},
        )

    def test_complete_topic_is_authoritative_for_implicit_feed_data_photo(self):
        for subid, origtid in (
            ("batch-1", "pic_with_underscores!!"),
            ("batch-1", ""),
            ("batch-1", "batch-1"),
        ):
            with self.subTest(subid=subid, origtid=origtid):
                post = parse_feed(
                    album_feed(
                        photos=[],
                        html=(
                            '<div class="f-info">Upload</div>'
                            '<i name="feed_data" data-tid="album_with_underscores" '
                            f'data-subid="{subid}" data-origtid="{origtid}" '
                            'data-topicid="album_with_underscores_pic_with_underscores!!_0_0"></i>'
                        ),
                    )
                )
                self.assertEqual(len(post.photo_targets), 1)
                self.assertEqual(
                    post.photo_targets[0].album_id, "album_with_underscores"
                )
                self.assertEqual(
                    post.photo_targets[0].pic_key, "pic_with_underscores!!"
                )
                self.assertEqual(post.comment_target_error, "")

    def test_without_composite_topic_origtid_precedes_batch_subid(self):
        post = parse_feed(
            album_feed(
                photos=[],
                html=(
                    '<div class="f-info">Upload</div>'
                    '<i name="feed_data" data-tid="album-1" '
                    'data-subid="batch-1" data-origtid="pic-1!!" '
                    'data-topicid="album-1"></i>'
                ),
            )
        )
        self.assertEqual(len(post.photo_targets), 1)
        self.assertEqual(post.photo_targets[0].pic_key, "pic-1!!")
        self.assertEqual(post.comment_target_error, "")

    def test_explicit_photo_key_conflict_is_not_hidden_by_feed_metadata(self):
        post = parse_feed(
            album_feed(
                photos=[],
                html=(
                    '<div class="f-info">Upload</div>'
                    '<i name="feed_data" data-tid="album-1" data-pickey="pic-2!!" '
                    'data-subid="batch-1" data-origtid="pic-1!!" '
                    'data-topicid="album-1_pic-1!!_0_0"></i>'
                ),
            )
        )
        self.assertEqual(post.photo_targets[0].pic_key, "pic-2!!")
        self.assertIn("topicId", post.comment_target_error)

    def test_topic_aliases_normalize_but_foreign_targets_remain_invalid(self):
        post = parse_feed(album_feed())
        photo = post.photo_targets[0]
        for topic in (
            "",
            "album-1",
            "album-1_pic-1!!",
            "album-1_pic-1!!_0_0",
            quote("album-1_pic-1!!_0_0", safe=""),
        ):
            with self.subTest(topic=topic):
                photo.feed_topic_id = topic
                self.assertEqual(photo.feed_comment_topic_id, "album-1_pic-1!!_0_0")
                self.assertEqual(post.comment_target_error, "")
        for topic in ("other_pic-1!!_0_0", "album-1_pic-2!!_0_0"):
            with self.subTest(topic=topic):
                photo.feed_topic_id = topic
                self.assertEqual(photo.feed_comment_topic_id, topic)
                self.assertIn("topicId", post.comment_target_error)


class PhotoTopicSubmissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.module = _load_qzone_service()
        self.service = _new_qzone_service(self.module)
        self.service.context = AsyncMock(
            return_value=self.module.QzoneContext(
                uin=10001,
                skey="dummy",
                p_skey="dummy",
            )
        )
        self.service._request = AsyncMock(return_value={"code": 0, "data": {"id": 123}})

    async def test_direct_photo_comments_normalize_only_known_aliases(self):
        for topic in (
            "album-1",
            "album-1_pic-1!!",
            quote("album-1_pic-1!!_0_0", safe=""),
        ):
            with self.subTest(topic=topic):
                await self.service.comment_photo(
                    owner_uin=20002,
                    album_id="album-1",
                    pic_key="pic-1!!",
                    content="Hello",
                    feed_topic_id=topic,
                )
                call = self.service._request.call_args
                self.assertEqual(call.args[1], self.service.PHOTO_COMMENT_URL)
                self.assertEqual(call.kwargs["data"]["topicId"], "album-1_pic-1!!")

    async def test_photo_reply_normalizes_alias_before_checking_root_topic(self):
        root = self.module.QzoneComment(
            tid="41",
            uin=30003,
            nickname="Friend",
            raw_fields={"photo_topic_id": "album-1_pic-1!!_0_0"},
        )
        result = await self.service.reply_photo_comment(
            owner_uin=20002,
            album_id="album-1",
            pic_key="pic-1!!",
            content="Thanks",
            comment=root,
            feed_topic_id="album-1",
        )
        self.assertIsInstance(result, dict)
        call = self.service._request.call_args
        self.assertEqual(call.args[1], self.service.PHOTO_REPLY_URL)
        self.assertEqual(call.kwargs["data"]["topicId"], "album-1_pic-1!!_0_0")
        self.assertEqual(call.kwargs["data"]["commentId"], "41")

    async def test_direct_shared_topic_cannot_bypass_batch_verification(self):
        with self.assertRaisesRegex(RuntimeError, "topicId.*不一致"):
            await self.service.comment_photo(
                owner_uin=20002,
                album_id="album-1",
                pic_key="pic-2!!",
                content="Hello",
                feed_topic_id="album-1_pic-1!!_0_0",
            )
        self.service._request.assert_not_awaited()

    async def test_direct_decorated_topic_cannot_bypass_viewer_verification(self):
        with self.assertRaisesRegex(RuntimeError, "topicId.*不一致"):
            await self.service.comment_photo(
                owner_uin=20002,
                album_id="album-1",
                pic_key="pic-1!!",
                content="Hello",
                feed_topic_id="album-1_pic-1!!_1790992589220000_4",
            )
        self.service._request.assert_not_awaited()

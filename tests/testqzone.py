import base64
import tempfile
import unittest
import importlib.util
import sys
import types
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "daily_share_qzone_testpkg"
SPACE_PACKAGE_NAME = f"{PACKAGE_NAME}.core.space"
PARSER_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.parser"
RELATION_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.relation"
ENTRY_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.entry"
H5_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.h5"
ALBUM_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.album"
VIDEO_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.video"
MEDIA_UPLOAD_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.upload"
CONSTANTS_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.endpoints"
CLIENT_SERVICE_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.gateway"
COMMENT_SERVICE_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.discussion"
FEED_SERVICE_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.feed"
SERVICE_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.service"
HOST_MODULE_NAME = f"{PACKAGE_NAME}.core.host.space"


class _Logger:
    def debug(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None


def _install_stub_module(name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _load_qzone_parser():
    _install_stub_module("astrbot", api=_install_stub_module("astrbot.api", logger=_Logger()))
    package_paths = {
        PACKAGE_NAME: ROOT,
        f"{PACKAGE_NAME}.core": ROOT / "core",
        SPACE_PACKAGE_NAME: ROOT / "core" / "space",
    }
    for name, path in package_paths.items():
        module = _install_stub_module(name)
        module.__path__ = [str(path)]

    models_spec = importlib.util.spec_from_file_location(
        f"{SPACE_PACKAGE_NAME}.models",
        ROOT / "core" / "space" / "models.py",
    )
    models_module = importlib.util.module_from_spec(models_spec)
    sys.modules[models_spec.name] = models_module
    models_spec.loader.exec_module(models_module)

    parser_spec = importlib.util.spec_from_file_location(
        PARSER_MODULE_NAME,
        ROOT / "core" / "space" / "parser.py",
    )
    parser_module = importlib.util.module_from_spec(parser_spec)
    sys.modules[PARSER_MODULE_NAME] = parser_module
    parser_spec.loader.exec_module(parser_module)
    return parser_module


_parser_module = _load_qzone_parser()
parse_feed_list = _parser_module.parse_feed_list
parse_feedinfo_html = _parser_module.parse_feedinfo_html
parse_home_feed_list = _parser_module.parse_home_feed_list
parse_recent_feed_list = _parser_module.parse_recent_feed_list


async def _confirmed_reply_verification(*args, **kwargs):
    return {
        "status": "confirmed",
        "verified_reply_tid": "verified-r1",
        "verified_reply_to_tid": "target",
        "verified_reply_to_uin": 1,
        "candidates": [],
    }


class _ConfirmedThreadVerificationMixin:
    async def _verify_thread_reply_submission(self, *args, **kwargs):
        return await _confirmed_reply_verification(*args, **kwargs)


def _load_qzone_relation():
    _load_qzone_parser()
    relation_spec = importlib.util.spec_from_file_location(
        RELATION_MODULE_NAME,
        ROOT / "core" / "space" / "relation.py",
    )
    relation_module = importlib.util.module_from_spec(relation_spec)
    sys.modules[RELATION_MODULE_NAME] = relation_module
    relation_spec.loader.exec_module(relation_module)
    return relation_module


def _load_qzone_entry():
    _load_qzone_parser()
    entry_spec = importlib.util.spec_from_file_location(
        ENTRY_MODULE_NAME,
        ROOT / "core" / "space" / "entry.py",
    )
    entry_module = importlib.util.module_from_spec(entry_spec)
    sys.modules[ENTRY_MODULE_NAME] = entry_module
    entry_spec.loader.exec_module(entry_module)
    return entry_module


def _load_qzone_service():
    parser_module = _load_qzone_parser()
    _load_qzone_relation()
    _load_qzone_entry()
    for module_name, filename in (
        (CONSTANTS_MODULE_NAME, "endpoints.py"),
        (CLIENT_SERVICE_MODULE_NAME, "gateway.py"),
        (COMMENT_SERVICE_MODULE_NAME, "discussion.py"),
        (FEED_SERVICE_MODULE_NAME, "feed.py"),
        (H5_MODULE_NAME, "h5.py"),
        (ALBUM_MODULE_NAME, "album.py"),
        (VIDEO_MODULE_NAME, "video.py"),
        (MEDIA_UPLOAD_MODULE_NAME, "upload.py"),
    ):
        spec = importlib.util.spec_from_file_location(
            module_name,
            ROOT / "core" / "space" / filename,
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    service_spec = importlib.util.spec_from_file_location(
        SERVICE_MODULE_NAME,
        ROOT / "core" / "space" / "service.py",
    )
    service_module = importlib.util.module_from_spec(service_spec)
    sys.modules[SERVICE_MODULE_NAME] = service_module
    service_spec.loader.exec_module(service_module)
    return service_module


def _load_qzone_host():
    _install_stub_module("astrbot", api=_install_stub_module("astrbot.api", logger=_Logger()))
    host_spec = importlib.util.spec_from_file_location(
        HOST_MODULE_NAME,
        ROOT / "core" / "host" / "space.py",
    )
    host_module = importlib.util.module_from_spec(host_spec)
    sys.modules[HOST_MODULE_NAME] = host_module
    host_spec.loader.exec_module(host_module)
    return host_module


class QzoneParserTests(unittest.TestCase):
    def test_parse_qzone_response_supports_sns_callback(self):
        payload = _parser_module.parse_qzone_response(
            'frameElement.callback({ret:0, code:0, msg:"succ"});'
        )

        self.assertEqual(payload["ret"], 0)
        self.assertEqual(payload["code"], 0)
        self.assertEqual(payload["msg"], "succ")

    def test_relation_parser_normalizes_care_friend_items(self):
        relation = _load_qzone_relation()

        items = relation.parse_qzone_relations(
            {
                "code": 0,
                "data": {
                    "items_list": [
                        {
                            "uin": "o10001",
                            "name": "测试人格",
                            "remark": "恬恬",
                            "img": "https://q.qlogo.cn/g?b=qq&nk=10001&s=30",
                            "score": "88",
                            "lastVisitTime": 1781785507,
                        },
                        {"uin": "10001", "name": "重复项"},
                        {"uin": "0", "name": "无效项"},
                    ]
                },
            }
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["uin"], 10001)
        self.assertEqual(items[0]["name"], "测试人格")
        self.assertEqual(items[0]["remark"], "恬恬")
        self.assertEqual(items[0]["score"], 88)
        self.assertIn("10001", items[0]["home"])
        self.assertTrue(items[0]["avatar"].startswith("https://"))

    def test_relation_parser_reads_visit_stats(self):
        relation = _load_qzone_relation()

        stats = relation.parse_qzone_visit_stats(
            {
                "code": 0,
                "data": {
                    "count": 2,
                    "modvisitcount": [
                        {"totalcount": 12, "todaycount": 1},
                        {"totalcount": 3087, "todaycount": 2},
                    ],
                },
            }
        )

        self.assertTrue(stats["available"])
        self.assertEqual(stats["today_views"], 2)
        self.assertEqual(stats["total_views"], 3087)
        self.assertEqual(stats["visitor_count"], 2)

    def test_entry_parser_reads_favorites(self):
        entry = _load_qzone_entry()

        result = entry.parse_favorites(
            {
                "code": 0,
                "data": {
                    "total_num": 1,
                    "fav_list": [
                        {
                            "id": "fav-1",
                            "title": "收藏标题",
                            "abstract": "收藏摘要",
                            "img_list": ["https://example.com/a.jpg"],
                            "create_time": 1781800000,
                        }
                    ],
                },
            }
        )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["title"], "收藏标题")
        self.assertEqual(result["items"][0]["image"], "https://example.com/a.jpg")

    def test_entry_parser_reads_message_board(self):
        entry = _load_qzone_entry()

        result = entry.parse_message_board(
            {
                "code": 0,
                "data": {
                    "total": 2,
                    "commentList": [
                        {
                            "id": "msg-1",
                            "uin": 10001,
                            "nickname": "好友",
                            "content": "留言<br>内容",
                            "create_time": 1781800000,
                        }
                    ],
                },
            }
        )

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["items"][0]["floor"], 2)
        self.assertEqual(result["items"][0]["content"], "留言\n内容")

    def test_clean_qzone_text_keeps_line_breaks_and_removes_expand_label(self):
        parser = _load_qzone_parser()

        result = parser.clean_qzone_text("从美术馆的光影里退场，<br>一出门就被大太阳撞了个满怀。<br>赶紧躲进梧桐树荫底下，<br>翻出收藏夹里那家几百米外的咖啡店。 展开全文")

        self.assertEqual(
            result,
            "从美术馆的光影里退场，\n一出门就被大太阳撞了个满怀。\n赶紧躲进梧桐树荫底下，\n翻出收藏夹里那家几百米外的咖啡店。",
        )

    def test_recent_feed_ignores_avatar_images(self):
        payload = {
            "data": {
                "data": [
                    {
                        "appid": "311",
                        "key": "abc",
                        "uin": 12345,
                        "nickname": "测试用户乙",
                        "pic": "https://q.qlogo.cn/headimg_dl?dst_uin=12345&spec=100",
                        "abstime": 1718000000,
                        "html": """
                            <div class="user-avatar">
                              <img src="https://q.qlogo.cn/headimg_dl?dst_uin=12345&spec=100">
                            </div>
                            <div class="f-info">测试看看</div>
                            <div class="img-box">
                              <img src="https://example.com/content.jpg">
                            </div>
                        """,
                    }
                ]
            }
        }

        posts = parse_recent_feed_list(payload)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].avatar_url, "https://q.qlogo.cn/headimg_dl?dst_uin=12345&spec=100")
        self.assertEqual(posts[0].images, ["https://example.com/content.jpg"])

    def test_recent_feed_ignores_placeholder_and_uses_real_lazy_image(self):
        payload = {
            "data": {
                "data": [
                    {
                        "appid": "311",
                        "key": "abc",
                        "uin": 12345,
                        "nickname": "测试用户乙",
                        "pic": "https://q.qlogo.cn/headimg_dl?dst_uin=12345&spec=100",
                        "abstime": 1718000000,
                        "html": """
                            <div class="f-info">测试看看</div>
                            <div class="img-box">
                              <img src="https://qzonestyle.gtimg.cn/qzone/space.gif" data-src="https://example.com/real.jpg">
                            </div>
                            <div class="img-box">
                              <img data-src="https://q.qlogo.cn/headimg_dl?dst_uin=12345&spec=100">
                            </div>
                        """,
                    }
                ]
            }
        }

        posts = parse_recent_feed_list(payload)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].images, ["https://example.com/real.jpg"])

    def test_recent_feed_marks_expandable_when_html_has_expand_link(self):
        payload = {
            "data": {
                "data": [
                    {
                        "appid": "311",
                        "key": "abc",
                        "uin": 12345,
                        "nickname": "测试用户乙",
                        "abstime": 1718000000,
                        "html": '<div class="f-info">第一行<br>第二行 展开全文</div>',
                    }
                ]
            }
        }

        posts = parse_recent_feed_list(payload)

        self.assertEqual(len(posts), 1)
        self.assertTrue(posts[0].expandable)
        self.assertEqual(posts[0].text, "第一行\n第二行")

    def test_recent_feed_uses_action_fid_instead_of_stream_key(self):
        payload = {
            "data": {
                "data": [
                    {
                        "appid": "311",
                        "key": "stream-key",
                        "fid": "real-fid",
                        "uin": 12345,
                        "nickname": "测试用户乙",
                        "curkey": "curkey-from-feed",
                        "unikey": "unikey-from-feed",
                        "operation": {"busi_param": {"private": "value"}},
                        "html": '<div class="f-info">测试看看</div>',
                    }
                ]
            }
        }

        posts = parse_recent_feed_list(payload)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].key, "12345:real-fid")
        self.assertEqual(posts[0].feed_key, "stream-key")
        self.assertEqual(posts[0].curkey, "curkey-from-feed")
        self.assertEqual(posts[0].unikey, "unikey-from-feed")
        self.assertEqual(posts[0].busi_param, {"private": "value"})

    def test_recent_feed_parses_feeds3_feed_data_with_comments(self):
        payload = {
            "data": {
                "data": [
                    {
                        "key": "stream-key",
                        "html": """
                            <li class="f-single">
                              <div class="f-single-head">
                                <div class="f-nick">
                                  <a class="f-name q_namecard" link="nameCard_2492835361">测试用户甲</a>
                                </div>
                              </div>
                              <div id="feed_2492835361_311_0_1774000000_1_1">
                                <div class="qz_summary wupfeed">
                                  <i class="none" name="feed_data" data-tid="1774000000" data-uin="2492835361" data-abstime="1774000000" data-fkey="real-fkey-abc123"></i>
                                  <div class="f-info">测试用户甲：今天去了书店</div>
                                  <div class="comments-list">
                                    <ul>
                                      <li class="comments-item bor3" data-type="commentroot" data-tid="11" data-uin="100000001" data-nick="Bot">
                                        <div class="comments-item-bd">
                                          <div class="comments-content">
                                            <a class="nickname">Bot</a>&nbsp;:&nbsp;这家书店听起来好舒服
                                          </div>
                                        </div>
                                        <div class="comments-list mod-comments-sub">
                                          <ul>
                                            <li class="comments-item bor3" data-type="replyroot" data-tid="1" data-uin="2492835361" data-nick="测试用户甲">
                                              <div class="comments-content">
                                                <a class="nickname">测试用户甲</a>&nbsp;回复<a class="nickname">Bot</a>&nbsp;:&nbsp;下次一起去
                                              </div>
                                              <div class="comments-op">
                                                <a class="reply" data-param="t1_tid=real-fkey-abc123&t2_uin=100000001&t2_tid=11">回复</a>
                                              </div>
                                            </li>
                                          </ul>
                                        </div>
                                      </li>
                                    </ul>
                                  </div>
                                </div>
                              </div>
                            </li>
                        """,
                    }
                ]
            }
        }

        posts = parse_recent_feed_list(payload)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].key, "2492835361:real-fkey-abc123")
        self.assertEqual(posts[0].name, "测试用户甲")
        self.assertEqual(posts[0].text, "今天去了书店")
        self.assertEqual(posts[0].create_time, 1774000000)
        self.assertEqual([comment.tid for comment in posts[0].comments], ["11", "11_r_1_2492835361"])
        self.assertEqual(posts[0].comments[1].parent_tid, "11")
        self.assertEqual(posts[0].comments[1].reply_to_tid, "11")
        self.assertEqual(posts[0].comments[1].reply_to_uin, 100000001)
        self.assertEqual(posts[0].comments[1].content, "下次一起去")

    def test_recent_feed_parses_feeds3_html_outside_data_array(self):
        payload = {
            "code": 0,
            "data": {
                "data": [],
                "main": {
                    "html": """
                        <li class="f-single">
                          <div class="f-nick"><a class="f-name q_namecard" link="nameCard_2492835361">测试用户甲</a></div>
                          <div id="feed_2492835361_311_0_1774000000_1_1">
                            <i class="none" name="feed_data" data-tid="1774000000" data-uin="2492835361" data-abstime="1774000000" data-fkey="real-fkey-main"></i>
                            <div class="f-info">测试用户甲：藏在 main 里的动态</div>
                          </div>
                        </li>
                    """
                },
            },
        }

        posts = parse_recent_feed_list(payload)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].key, "2492835361:real-fkey-main")
        self.assertEqual(posts[0].text, "藏在 main 里的动态")

    def test_recent_feed_parses_liked_state(self):
        payload = {
            "data": {
                "data": [
                    {
                        "appid": "311",
                        "fid": "liked-fid",
                        "uin": 12345,
                        "nickname": "测试用户乙",
                        "like": {"isliked": 1},
                        "html": '<div class="f-info">测试看看</div>',
                    }
                ]
            }
        }

        posts = parse_recent_feed_list(payload)

        self.assertEqual(len(posts), 1)
        self.assertTrue(posts[0].liked)
        self.assertTrue(posts[0].to_payload()["liked"])

    def test_payload_includes_comment_reply_target(self):
        service_module = _load_qzone_service()
        post = service_module.QzonePost(
            uin=10001,
            tid="feed-1",
            comments=[
                service_module.QzoneComment(uin=20002, nickname="Alice", content="first", tid="c1"),
                service_module.QzoneComment(uin=30003, nickname="Bob", content="reply", tid="r1", parent_tid="c1"),
                service_module.QzoneComment(
                    uin=40004,
                    nickname="Carol",
                    content="nested",
                    tid="r2",
                    parent_tid="c1",
                    reply_to_tid="r1",
                    reply_to_uin=30003,
                    reply_to_nickname="Bob",
                ),
            ],
        )

        payload = post.to_payload(include_comments=True)

        self.assertNotIn("reply_to", payload["comments"][0])
        self.assertEqual(payload["comments"][1]["parent_id"], "c1")
        self.assertEqual(payload["comments"][1]["reply_to"]["uin"], 20002)
        self.assertEqual(payload["comments"][1]["reply_to"]["nickname"], "Alice")
        self.assertEqual(payload["comments"][2]["parent_id"], "c1")
        self.assertEqual(payload["comments"][2]["reply_to"]["id"], "r1")
        self.assertEqual(payload["comments"][2]["reply_to"]["uin"], 30003)
        self.assertEqual(payload["comments"][2]["reply_to"]["nickname"], "Bob")

    def test_recent_feed_keeps_non_mood_video_feed(self):
        payload = {
            "data": {
                "data": [
                    {
                        "appid": "4",
                        "key": "video-stream-key",
                        "fid": "video-fid",
                        "uin": 12345,
                        "nickname": "测试用户乙",
                        "abstime": 1718000000,
                        "html": """
                            <div class="f-info">视频正文</div>
                            <div class="img-box f-video-wrap" url3="https://example.com/video.mp4">
                              <img src="https://example.com/video-cover.jpg">
                            </div>
                        """,
                    }
                ]
            }
        }

        posts = parse_recent_feed_list(payload)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].appid, 4)
        self.assertEqual(posts[0].tid, "video-fid")
        self.assertEqual(posts[0].text, "视频正文")
        self.assertEqual(posts[0].videos, ["https://example.com/video.mp4"])

    def test_recent_feed_extracts_video_vid_without_direct_url(self):
        payload = {
            "data": {
                "data": [
                    {
                        "appid": "4",
                        "key": "video-stream-key",
                        "fid": "video-fid",
                        "common": {"uin": 12345},
                        "nickname": "测试用户乙",
                        "abstime": 1718000000,
                        "html": """
                            <div class="f-info">上传了一个视频</div>
                            <div class="img-box f-video-wrap" data-vid="1075_0b53nrbk4cydeuaogbrsobvda3aevz6agbca">
                              <img src="https://example.com/video-cover.jpg">
                            </div>
                        """,
                    }
                ]
            }
        }

        posts = parse_recent_feed_list(payload)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].uin, 12345)
        self.assertEqual(posts[0].videos, ["qzone://video/1075_0b53nrbk4cydeuaogbrsobvda3aevz6agbca"])

    def test_feed_detail_extracts_video_vid_from_richval(self):
        post = _parser_module.parse_feed_item(
            {
                "tid": "mood-video",
                "uin": 100000001,
                "appid": 311,
                "content": "hello",
                "richval": "playurl=http://cache.tv.qq.com/qqplayerout.swf?v=1075_0b53richvid&auto=0&vid=1075_0b53richvid",
            }
        )

        self.assertIsNotNone(post)
        self.assertEqual(post.videos, ["qzone://video/1075_0b53richvid"])

    def test_feed_detail_parses_liked_state(self):
        post = _parser_module.parse_feed_item(
            {
                "tid": "liked-mood",
                "uin": 100000001,
                "content": "hello",
                "like": {"ismylike": "1"},
            }
        )

        self.assertIsNotNone(post)
        self.assertTrue(post.liked)

    def test_feed_detail_extracts_video_vid_from_vvid_field(self):
        post = _parser_module.parse_feed_item(
            {
                "tid": "mood-video",
                "uin": 100000001,
                "appid": 311,
                "content": "hello",
                "operation": {"busi_param": {"vvid": "1075_0b53vvidfield"}},
            }
        )

        self.assertIsNotNone(post)
        self.assertEqual(post.videos, ["qzone://video/1075_0b53vvidfield"])

    def test_home_feed_parses_video_feed_from_module_html(self):
        markup = """
            <script>
            var _feedsdata = {
              code: 0,
              data: {
                main: {},
                host_data: [{
                  appid: 4,
                  key: "home-video-key",
                  fid: "home-video-fid",
                  uin: 12345,
                  abstime: 1718000000,
                  html: "<div class='f-info'>上传了一个视频</div><div class='img-box f-video-wrap' data-vid='1075_0b53homevideo'></div>"
                }]
              }
            };
            if (window) {}
            </script>
            <ul>
              <li class="f-single" data-key="home-video-key">
                <div class="f-info">上传了一个视频</div>
                <div class="img-box f-video-wrap" data-vid="1075_0b53homevideo"></div>
              </li>
            </ul>
        """

        posts = parse_home_feed_list(markup)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].tid, "home-video-fid")
        self.assertEqual(posts[0].videos, ["qzone://video/1075_0b53homevideo"])

    def test_publish_feedinfo_parses_native_video_marker(self):
        markup = """
            <li class="f-single f-s-s" id="fct_100000001_311_0_1781752293_0_1" data-uin="100000001">
              <div class="f-info">今天测试一下</div>
              <div class="img-box f-video-wrap" data-vid="1075_0b53feedinfovid">
                <img src="https://example.com/cover.jpg">
              </div>
            </li>
        """

        post = parse_feedinfo_html(markup, context_uin=100000001, context_tid="feedinfo-tid", context_time=1781752293)

        self.assertIsNotNone(post)
        self.assertEqual(post.tid, "feedinfo-tid")
        self.assertEqual(post.appid, 311)
        self.assertEqual(post.text, "今天测试一下")
        self.assertEqual(post.videos, ["qzone://video/1075_0b53feedinfovid"])

    def test_self_feed_does_not_use_pic_list_as_avatar(self):
        posts = parse_feed_list([
            {
                "tid": "mood-1",
                "uin": 12345,
                "nickname": "测试用户乙",
                "content": "今天也很好",
                "pic": [{"url1": "https://example.com/content.jpg"}],
                "created_time": 1718000000,
            }
        ])

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].images, ["https://example.com/content.jpg"])
        self.assertEqual(posts[0].avatar_url, "https://q.qlogo.cn/headimg_dl?dst_uin=12345&spec=100")

    def test_parse_comments_supports_commentid_and_reply_list(self):
        posts = parse_feed_list([
            {
                "tid": "mood-1",
                "uin": "o12345",
                "content": "post text",
                "commentlist": [
                    {
                        "commentid": "root-c1",
                        "uin": "o20002",
                        "nickname": "Alice",
                        "content": "first",
                        "replyList": [
                            {
                                "commentId": "reply-r2",
                                "commentUin": "o20002",
                                "nickname": "Alice",
                                "commentContent": "second",
                                "replyList": [
                                    {
                                        "commentId": "reply-r3",
                                        "commentUin": "o30003",
                                        "nickname": "Bob",
                                        "commentContent": "third",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ])

        comments = posts[0].comments
        self.assertEqual([item.tid for item in comments], ["root-c1", "reply-r2", "reply-r3"])
        self.assertEqual(comments[1].parent_tid, "root-c1")
        self.assertEqual(comments[1].reply_to_tid, "root-c1")
        self.assertEqual(comments[1].uin, 20002)
        self.assertEqual(comments[2].parent_tid, "root-c1")
        self.assertEqual(comments[2].reply_to_tid, "reply-r2")

    def test_parse_comments_reads_reply_target_from_html_params(self):
        posts = parse_feed_list([
            {
                "tid": "mood-1",
                "uin": "o12345",
                "content": "post text",
                "commentlist": [
                    {
                        "commentid": "root-c1",
                        "uin": "o20002",
                        "nickname": "Alice",
                        "content": "first",
                        "replyList": [
                            {
                                "commentId": "reply-r2",
                                "commentUin": "o30003",
                                "nickname": "Bob",
                                "commentContent": '回复内容 <a data-param="t2_uin=20002&t2_tid=root-c1">回复</a>',
                            }
                        ],
                    }
                ],
            }
        ])

        comment = posts[0].comments[1]
        self.assertEqual(comment.parent_tid, "root-c1")
        self.assertEqual(comment.reply_to_tid, "root-c1")
        self.assertEqual(comment.reply_to_uin, 20002)
        self.assertEqual(comment.raw_fields["commentId"], "reply-r2")
        self.assertEqual(comment.raw_fields["commentUin"], "o30003")
        self.assertEqual(comment.raw_fields["extracted_params"]["t2_tid"], "root-c1")
        self.assertEqual(comment.raw_fields["extracted_params"]["t2_uin"], "20002")

    def test_parse_comments_reads_reply_target_from_mention(self):
        posts = parse_feed_list([
            {
                "tid": "mood-1",
                "uin": "o12345",
                "content": "post text",
                "commentlist": [
                    {
                        "commentid": "root-c1",
                        "uin": "o20002",
                        "nickname": "Alice",
                        "content": "first",
                        "replyList": [
                            {
                                "commentId": "reply-r2",
                                "commentUin": "o30003",
                                "nickname": "Bob",
                                "commentContent": "@{uin:12345,nick:Me,auto:1} third",
                            }
                        ],
                    }
                ],
            }
        ])

        comment = posts[0].comments[1]
        self.assertEqual(comment.parent_tid, "root-c1")
        self.assertEqual(comment.reply_to_uin, 12345)
        self.assertEqual(comment.reply_to_nickname, "Me")

    def test_parse_comments_stabilizes_short_reply_ids(self):
        posts = parse_feed_list([
            {
                "tid": "mood-1",
                "uin": "o12345",
                "content": "post text",
                "commentlist": [
                    {
                        "commentid": "11",
                        "uin": "o20002",
                        "nickname": "Alice",
                        "content": "first",
                        "replyList": [
                            {
                                "commentId": "1",
                                "commentUin": "o12345",
                                "nickname": "Me",
                                "commentContent": "reply",
                            },
                            {
                                "commentId": "1",
                                "commentUin": "o20002",
                                "nickname": "Alice",
                                "commentContent": 'again <a data-param="t2_uin=12345&t2_tid=1">回复</a>',
                            },
                        ],
                    }
                ],
            }
        ])

        comments = posts[0].comments
        self.assertEqual(comments[1].tid, "11_r_1_12345")
        self.assertEqual(comments[1].submit_tid, "1")
        self.assertEqual(comments[2].tid, "11_r_1_20002")
        self.assertEqual(comments[2].submit_tid, "1")
        self.assertEqual(comments[2].reply_to_tid, "11_r_1_12345")
        self.assertEqual(comments[2].raw_reply_to_tid, "1")
        self.assertEqual(comments[2].reply_to_tid_source, "param:t2_tid")
        self.assertEqual(comments[2].reply_to_uin, 12345)

    def test_parse_comments_does_not_bind_short_reply_target_to_future_comment(self):
        posts = parse_feed_list([
            {
                "tid": "mood-1",
                "uin": "o12345",
                "content": "post text",
                "commentlist": [
                    {
                        "commentid": "11",
                        "uin": "o20002",
                        "nickname": "Friend",
                        "content": "first",
                        "replyList": [
                            {
                                "commentId": "1",
                                "commentUin": "o12345",
                                "nickname": "Bot",
                                "commentContent": 'bot reply <a data-param="t2_uin=20002&t2_tid=11">回复</a>',
                            },
                            {
                                "commentId": "1",
                                "commentUin": "o20002",
                                "nickname": "Friend",
                                "commentContent": 'again <a data-param="t2_uin=12345&t2_tid=1">回复</a>',
                            },
                        ],
                    }
                ],
            }
        ])

        comments = posts[0].comments
        self.assertEqual(comments[1].tid, "11_r_1_12345")
        self.assertEqual(comments[1].reply_to_tid, "11")
        self.assertEqual(comments[2].tid, "11_r_1_20002")
        self.assertEqual(comments[2].reply_to_tid, "11_r_1_12345")

    def test_parse_comments_keeps_duplicate_short_ids_unique_for_same_user(self):
        posts = parse_feed_list([
            {
                "tid": "mood-1",
                "uin": "o12345",
                "content": "post text",
                "commentlist": [
                    {
                        "commentid": "11",
                        "uin": "o20002",
                        "nickname": "Friend",
                        "content": "first",
                        "replyList": [
                            {"commentId": "1", "commentUin": "o20002", "nickname": "Friend", "commentContent": "one"},
                            {"commentId": "1", "commentUin": "o20002", "nickname": "Friend", "commentContent": "two"},
                        ],
                    }
                ],
            }
        ])

        self.assertEqual([comment.tid for comment in posts[0].comments], ["11", "11_r_1_20002", "11_r_1_20002_n2"])

    def test_parse_comments_prefers_commentid_as_submit_tid_when_tid_is_short_seq(self):
        posts = parse_feed_list([
            {
                "tid": "mood-1",
                "uin": "o12345",
                "content": "post text",
                "commentlist": [
                    {
                        "tid": "11",
                        "commentid": "root-real-11",
                        "uin": "o20002",
                        "nickname": "Friend",
                        "content": "first",
                        "replyList": [
                            {
                                "tid": "2",
                                "commentid": "reply-real-2",
                                "commentUin": "o20002",
                                "nickname": "Friend",
                                "commentContent": "again",
                            },
                        ],
                    }
                ],
            }
        ])

        comments = posts[0].comments
        self.assertEqual(comments[0].tid, "11")
        self.assertEqual(comments[0].submit_tid, "root-real-11")
        self.assertEqual(comments[1].tid, "11_r_2_20002")
        self.assertEqual(comments[1].submit_tid, "reply-real-2")

    def test_parse_feed_item_supports_comment_list_alias(self):
        posts = parse_feed_list([
            {
                "tid": "mood-1",
                "uin": "o12345",
                "content": "post text",
                "commentList": [
                    {
                        "commentId": "root-c1",
                        "commentUin": "o20002",
                        "nickname": "Alice",
                        "commentContent": "first",
                    }
                ],
            }
        ])

        self.assertEqual(len(posts[0].comments), 1)
        self.assertEqual(posts[0].comments[0].tid, "root-c1")
        self.assertEqual(posts[0].comments[0].content, "first")


class QzoneServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_bot_prefers_configured_qzone_adapter(self):
        service_module = _load_qzone_service()
        first = object()
        selected = object()

        class CtxService:
            bot_map = {"V": first, "Swan": selected}

            def _get_bot_instance(self, adapter_id):
                return self.bot_map.get(adapter_id)

            def _is_onebot_platform(self, _key):
                return False

            def _get_onebot_bot(self, *args, **kwargs):
                return None

        plugin = types.SimpleNamespace(
            _cached_qq_adapter_id="V",
            qzone_conf={"qzone_adapter_id": "Swan"},
            ctx_service=CtxService(),
        )
        service = service_module.QzoneService(plugin)

        self.assertIs(service._get_bot(), selected)

    async def test_get_bot_uses_first_instance_when_qzone_adapter_empty(self):
        service_module = _load_qzone_service()
        first = object()
        second = object()

        class CtxService:
            bot_map = {"V": first, "Swan": second}

            def _get_bot_instance(self, adapter_id):
                if adapter_id:
                    return self.bot_map.get(adapter_id)
                return next(iter(self.bot_map.values()))

            def _is_onebot_platform(self, _key):
                return False

            def _get_onebot_bot(self, *args, **kwargs):
                return None

        plugin = types.SimpleNamespace(
            _cached_qq_adapter_id="",
            qzone_conf={"qzone_adapter_id": ""},
            ctx_service=CtxService(),
        )
        service = service_module.QzoneService(plugin)

        self.assertIs(service._get_bot(), first)

    async def test_query_recent_posts_uses_feeds3_basic_params(self):
        service_module = _load_qzone_service()

        class Service(_ConfirmedThreadVerificationMixin, service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))
                self.call = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.call = {
                    "method": method,
                    "url": url,
                    "params": dict(params or {}),
                    "headers": dict(headers or {}),
                }
                return {
                    "code": 0,
                    "_http_status": 200,
                    "_raw_length": 2048,
                    "data": {
                        "main": {
                            "hasMoreFeeds": True,
                            "externparam": "pagenum=2&basetime=1773990000",
                        },
                        "data": [
                            {
                                "html": """
                                    <li class="f-single">
                                      <div class="f-nick"><a class="f-name q_namecard" link="nameCard_2492835361">测试用户甲</a></div>
                                      <div id="feed_2492835361_311_0_1774000000_1_1">
                                        <i class="none" name="feed_data" data-tid="1774000000" data-uin="2492835361" data-abstime="1774000000" data-fkey="real-fkey-abc123"></i>
                                        <div class="f-info">测试用户甲：今天去了书店</div>
                                      </div>
                                    </li>
                                """
                            }
                        ],
                    },
                }

        service = Service()
        posts = await service.query_recent_posts(num=3)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].key, "2492835361:real-fkey-abc123")
        self.assertEqual(service.call["url"], service.RECENT_URL)
        self.assertEqual(service.call["params"]["scope"], 0)
        self.assertEqual(service.call["params"]["view"], 1)
        self.assertEqual(service.call["params"]["filter"], "all")
        self.assertEqual(service.call["params"]["flag"], 1)
        self.assertEqual(service.call["params"]["applist"], "all")
        self.assertEqual(service.call["params"]["outputhtmlfeed"], 1)
        self.assertNotIn("windowId", service.call["params"])
        self.assertNotIn("usertime", service.call["params"])
        self.assertIn("XMLHttpRequest", service.call["headers"].get("X-Requested-With", ""))
        self.assertEqual(service.last_friend_feeds_meta["source"], "recent_posts")
        self.assertEqual(service.last_friend_feeds_meta["count"], 1)
        self.assertEqual(service.last_friend_feeds_meta["parsed_count"], 1)
        self.assertTrue(service.last_friend_feeds_meta["has_more"])
        self.assertEqual(service.last_friend_feeds_meta["next_cursor"], "pagenum=2&basetime=1773990000")

    async def test_query_mention_posts_uses_about_me_notification_feed(self):
        service_module = _load_qzone_service()
        bot_uin = 10001
        friend_uin = 20002

        class Service(_ConfirmedThreadVerificationMixin, service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))
                self.call = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=bot_uin,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="BOT_NICK",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.call = {
                    "method": method,
                    "url": url,
                    "params": dict(params or {}),
                    "headers": dict(headers or {}),
                }
                return {
                    "code": 0,
                    "data": {
                        "main": {"total_number": 1},
                        "data": [
                            {
                                "appid": "311",
                                "key": "mention-fkey",
                                "uin": str(friend_uin),
                                "nickname": "FRIEND_NICK",
                                "abstime": "1782452784",
                                "html": """
                                    <li class="f-single">
                                      <div class="f-nick">
                                        <a class="f-name q_namecard" link="nameCard_20002">FRIEND_NICK</a>
                                        <span class="state">提到我</span>
                                      </div>
                                      <div id="feed_20002_311_4_1782452784_1_1">
                                        <i class="none" name="feed_data"
                                           data-fkey="mention-fkey"
                                           data-tid="mention-fkey"
                                           data-uin="20002"
                                           data-abstime="1782452784"></i>
                                        <p class="txt-box-title">
                                          <a class="nickname q_namecard" link="nameCard_20002">FRIEND_NICK</a>
                                          <span class="state">：</span>
                                          周末去旧书店吗？
                                          <a class="nickname q_namecard" link="nameCard_10001">@BOT_NICK</a>
                                        </p>
                                      </div>
                                    </li>
                                """,
                            },
                            {
                                "appid": "311",
                                "key": "normal-fkey",
                                "uin": str(friend_uin),
                                "nickname": "FRIEND_NICK",
                                "html": """
                                    <li class="f-single">
                                      <div id="feed_20002_311_4_1782450000_1_1">
                                        <i class="none" name="feed_data" data-fkey="normal-fkey" data-uin="20002"></i>
                                        <div class="f-info">普通动态</div>
                                      </div>
                                    </li>
                                """,
                            },
                            {
                                "appid": "311",
                                "key": "comment-notice-key",
                                "uin": str(friend_uin),
                                "nickname": "FRIEND_NICK",
                                "html": """
                                    <li class="f-single">
                                      <div class="f-nick">
                                        <a class="f-name q_namecard" link="nameCard_20002">FRIEND_NICK</a>
                                        <span class="state">评论了我的说说</span>
                                      </div>
                                      <div id="feed_10001_311_4_1782452785_1_1">
                                        <i class="none" name="feed_data"
                                           data-fkey="self-post-key"
                                           data-tid="self-post-key"
                                           data-uin="10001"
                                           data-abstime="1782452785"></i>
                                        <p class="txt-box-title">Bot 自己发的带图说说</p>
                                        <div class="comments-content">
                                          <a class="nickname q_namecard" link="nameCard_20002">FRIEND_NICK</a>
                                          回复
                                          <a class="nickname q_namecard" link="nameCard_10001">@BOT_NICK</a>
                                        </div>
                                      </div>
                                    </li>
                                """,
                            },
                        ],
                    },
                }

        service = Service()
        posts = await service.query_mention_posts(count=3, with_detail=False)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].key, "20002:mention-fkey")
        self.assertIn("周末去旧书店吗", posts[0].text)
        self.assertEqual(service.call["url"], service.ABOUT_ME_URL)
        self.assertEqual(service.call["params"]["uin"], bot_uin)
        self.assertEqual(service.call["params"]["getappnotification"], 1)
        self.assertEqual(service.call["params"]["getnotifi"], 1)
        self.assertEqual(service.call["params"]["outputhtmlfeed"], 1)
        self.assertEqual(service.call["params"]["scope"], 1)

    async def test_query_relations_uses_friend_ship_manager_do_type(self):
        service_module = _load_qzone_service()

        class Service(_ConfirmedThreadVerificationMixin, service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))
                self.call = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.call = {"method": method, "url": url, "params": dict(params or {})}
                return {
                    "code": 0,
                    "data": {"items_list": [{"uin": "10001", "name": "好友", "score": "9"}]},
                }

        service = Service()
        result = await service.query_relations(relation_type="care_by")

        self.assertEqual(result["type"], "care_by")
        self.assertEqual(result["items"][0]["uin"], 10001)
        self.assertEqual(service.call["url"], service.RELATION_URL)
        self.assertEqual(service.call["params"]["uin"], 100000001)
        self.assertEqual(service.call["params"]["do"], 2)
        self.assertEqual(service.call["params"]["g_tk"], "337168208")

    async def test_query_posts_with_detail_keeps_list_comments_when_detail_has_none(self):
        service_module = _load_qzone_service()

        class Service(_ConfirmedThreadVerificationMixin, service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                if url == self.LIST_URL:
                    return {
                        "code": 0,
                        "msglist": [
                            {
                                "tid": "mood-1",
                                "uin": 100000001,
                                "content": "今天很开心",
                                "commentlist": [
                                    {
                                        "commentid": "c1",
                                        "uin": 10001,
                                        "nickname": "Alice",
                                        "content": "真不错",
                                    }
                                ],
                            }
                        ],
                    }
                return {
                    "code": 0,
                    "tid": "mood-1",
                    "uin": 100000001,
                    "content": "今天很开心",
                }

        service = Service()
        posts = await service.query_posts(target_id="100000001", with_detail=True)

        self.assertEqual(len(posts), 1)
        self.assertEqual([comment.tid for comment in posts[0].comments], ["c1"])

    async def test_query_posts_with_detail_merges_list_thread_comments(self):
        service_module = _load_qzone_service()

        class Service(_ConfirmedThreadVerificationMixin, service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                if url == self.LIST_URL:
                    return {
                        "code": 0,
                        "msglist": [
                            {
                                "tid": "mood-1",
                                "uin": 100000001,
                                "content": "今天很开心",
                                "commentlist": [
                                    {
                                        "commentid": "c1",
                                        "uin": 10001,
                                        "nickname": "Alice",
                                        "content": "真不错",
                                        "replyList": [
                                            {
                                                "commentId": "r1",
                                                "commentUin": 100000001,
                                                "nickname": "测试用户乙",
                                                "commentContent": "谢谢你呀",
                                            },
                                            {
                                                "commentId": "r2",
                                                "commentUin": 10001,
                                                "nickname": "Alice",
                                                "commentContent": "哈哈我也觉得",
                                            },
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                return {
                    "code": 0,
                    "tid": "mood-1",
                    "uin": 100000001,
                    "content": "今天很开心",
                    "commentList": [
                        {
                            "commentId": "c1",
                            "commentUin": 10001,
                            "nickname": "Alice",
                            "commentContent": "真不错",
                        }
                    ],
                }

        service = Service()
        posts = await service.query_posts(target_id="100000001", with_detail=True)

        self.assertEqual([comment.tid for comment in posts[0].comments], ["c1", "r1", "r2"])
        self.assertEqual(posts[0].comments[1].parent_tid, "c1")
        self.assertEqual(posts[0].comments[2].parent_tid, "c1")

    async def test_query_posts_with_detail_keeps_stable_tid_and_recovers_real_submit_tid(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                if url == self.LIST_URL:
                    return {
                        "code": 0,
                        "msglist": [
                            {
                                "tid": "mood-1",
                                "uin": 100000001,
                                "content": "今天很开心",
                                "commentlist": [
                                    {
                                        "commentid": "11",
                                        "uin": 10001,
                                        "nickname": "Alice",
                                        "content": "真不错",
                                        "replyList": [
                                            {
                                                "commentId": "2",
                                                "commentUin": 10001,
                                                "nickname": "Alice",
                                                "commentContent": "哈哈我也觉得",
                                            },
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                return {
                    "code": 0,
                    "tid": "mood-1",
                    "uin": 100000001,
                    "content": "今天很开心",
                    "commentList": [
                        {
                            "tid": "11",
                            "commentid": "root-real-11",
                            "commentUin": 10001,
                            "nickname": "Alice",
                            "commentContent": "真不错",
                            "replyList": [
                                {
                                    "tid": "2",
                                    "commentid": "reply-real-2",
                                    "commentUin": 10001,
                                    "nickname": "Alice",
                                    "commentContent": "哈哈我也觉得",
                                }
                            ],
                        }
                    ],
                }

        service = Service()
        posts = await service.query_posts(target_id="100000001", with_detail=True)

        self.assertEqual([comment.tid for comment in posts[0].comments], ["11", "11_r_2_10001"])
        self.assertEqual(posts[0].comments[0].submit_tid, "root-real-11")
        self.assertEqual(posts[0].comments[1].submit_tid, "reply-real-2")

    async def test_base64_image_decodes_before_path_check(self):
        service_module = _load_qzone_service()
        service = service_module.QzoneService(types.SimpleNamespace())
        data = b"daily-share-image"

        result = await service._image_bytes(f"base64://{base64.b64encode(data).decode('ascii')}")

        self.assertEqual(result, data)

    async def test_api_timeout_reads_qzone_config_and_clamps(self):
        service_module = _load_qzone_service()
        plugin = types.SimpleNamespace(qzone_conf={"qzone_api_timeout_seconds": "180"})
        service = service_module.QzoneService(plugin)

        self.assertEqual(service._api_timeout_seconds(), 180)

        plugin.qzone_conf["qzone_api_timeout_seconds"] = 999
        self.assertEqual(service._api_timeout_seconds(), 300)

        plugin.qzone_conf["qzone_api_timeout_seconds"] = "bad"
        self.assertEqual(service._api_timeout_seconds(), 120)

    async def test_http_rebuilds_session_when_timeout_changes(self):
        service_module = _load_qzone_service()
        client_module = sys.modules[CLIENT_SERVICE_MODULE_NAME]
        plugin = types.SimpleNamespace(qzone_conf={"qzone_api_timeout_seconds": 120})
        service = service_module.QzoneService(plugin)

        class FakeTimeout:
            def __init__(self, *, total):
                self.total = total

        class FakeSession:
            def __init__(self, *, timeout):
                self.timeout = timeout
                self.closed = False

            async def close(self):
                self.closed = True

        fake_aiohttp = types.SimpleNamespace(ClientSession=FakeSession, ClientTimeout=FakeTimeout)

        try:
            with patch.object(client_module, "aiohttp", fake_aiohttp):
                session = await service._http()
                self.assertEqual(session.timeout.total, 120)

                plugin.qzone_conf["qzone_api_timeout_seconds"] = 180
                rebuilt = await service._http()

                self.assertIsNot(session, rebuilt)
                self.assertTrue(session.closed)
                self.assertEqual(rebuilt.timeout.total, 180)
        finally:
            await service.close()

    async def test_h5_headers_include_full_qzone_cookie_context_for_feed_upload(self):
        service_module = _load_qzone_service()
        service = service_module.QzoneService(types.SimpleNamespace())
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
            cookie_values={"uin": "o100000001", "ptcz": "noise"},
        )

        headers = service._h5_headers(ctx)

        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertIn("uin=100000001", headers["Cookie"])
        self.assertIn("p_uin=100000001", headers["Cookie"])
        self.assertIn("p_skey=p_skey", headers["Cookie"])
        self.assertIn("skey=skey", headers["Cookie"])
        self.assertIn("ptcz=noise", headers["Cookie"])

    async def test_comment_h5_headers_use_h5_origin_and_ajax_headers(self):
        service_module = _load_qzone_service()
        service = service_module.QzoneService(types.SimpleNamespace())
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        headers = service._comment_h5_headers(ctx, referer="https://h5.qzone.qq.com/100000001/mood/post-1")

        self.assertEqual(headers["Origin"], service.H5_ORIGIN)
        self.assertEqual(headers["Referer"], "https://h5.qzone.qq.com/100000001/mood/post-1")
        self.assertEqual(headers["X-Requested-With"], "XMLHttpRequest")
        self.assertEqual(headers["Sec-Fetch-Mode"], "cors")

    async def test_h5_post_json_prefers_http2_and_sends_full_cookie_context(self):
        service_module = _load_qzone_service()
        client_module = sys.modules[CLIENT_SERVICE_MODULE_NAME]
        plugin = types.SimpleNamespace(qzone_conf={"qzone_api_timeout_seconds": 120})
        service = service_module.QzoneService(plugin)
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
            cookie_values={"uin": "o100000001", "extra": "ignored"},
        )

        class FakeResponse:
            status_code = 200
            text = '{"ret":0,"data":{"flag":1}}'

        class FakeAsyncClient:
            def __init__(self, *, http2, timeout, headers):
                self.http2 = http2
                self.timeout = timeout
                self.headers = headers
                self.calls = []
                self.closed = False

            async def post(self, url, *, params=None, content=None, headers=None):
                self.calls.append({"url": url, "params": params, "content": content, "headers": headers})
                return FakeResponse()

            async def aclose(self):
                self.closed = True

        fake_httpx = types.SimpleNamespace(
            AsyncClient=FakeAsyncClient,
            TimeoutException=TimeoutError,
            HTTPError=Exception,
        )

        try:
            with (
                patch.object(client_module, "httpx", fake_httpx),
                patch.object(client_module.importlib.util, "find_spec", lambda name: object() if name == "h2" else None),
            ):
                result = await service._h5_post_json(
                    ctx,
                    "https://h5.qzone.qq.com/webapp/json/sliceUpload/FileUpload",
                    {"hello": "world"},
                    params={"g_tk": ctx.gtk},
                    label="cover-chunk-0",
                )

            self.assertEqual(result["ret"], 0)
            self.assertEqual(result["_endpoint"], "cover-chunk-0")
            self.assertTrue(service._h2_session.http2)
            call = service._h2_session.calls[0]
            self.assertIn("uin=100000001", call["headers"]["Cookie"])
            self.assertIn("p_skey=p_skey", call["headers"]["Cookie"])
            self.assertIn("skey=skey", call["headers"]["Cookie"])
            self.assertIn("extra=ignored", call["headers"]["Cookie"])
            self.assertEqual(call["content"], b'{"hello":"world"}')
        finally:
            await service.close()

    async def test_fetch_bot_cookie_merges_qzone_cookie_domains(self):
        service_module = _load_qzone_service()

        class Bot:
            def __init__(self):
                self.domains = []

            async def get_cookies(self, *, domain):
                self.domains.append(domain)
                cookies = {
                    "user.qzone.qq.com": "uin=o100000001; skey=skey",
                    "h5.qzone.qq.com": "p_skey=p_skey; pt4_token=pt-token",
                    "qzone.qq.com": "ptcz=ptcz-value",
                }
                return {"cookies": cookies.get(domain, "")}

        bot = Bot()
        ctx_service = types.SimpleNamespace(
            _get_bot_instance=lambda adapter_id: bot,
            bot_map={},
            _is_onebot_platform=lambda key: False,
            _get_onebot_bot=lambda target_umo, adapter_id: bot,
        )
        plugin = types.SimpleNamespace(_cached_qq_adapter_id="", ctx_service=ctx_service)
        service = service_module.QzoneService(plugin)

        cookie = await service._fetch_bot_cookie()
        ctx = await service._context_from_cookie(cookie)

        self.assertIn("user.qzone.qq.com", bot.domains)
        self.assertIn("h5.qzone.qq.com", bot.domains)
        self.assertIn("qzone.qq.com", bot.domains)
        self.assertEqual(ctx.uin, 100000001)
        self.assertEqual(ctx.p_skey, "p_skey")
        self.assertEqual(ctx.cookie_values["pt4_token"], "pt-token")
        self.assertEqual(ctx.cookie_values["ptcz"], "ptcz-value")

    async def test_request_does_not_mix_explicit_cookie_header_with_cookie_jar(self):
        service_module = _load_qzone_service()

        class FakeResponse:
            status = 200

            async def text(self):
                return '{"code":0}'

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

        class FakeSession:
            closed = False

            def __init__(self):
                self.calls = []

            def request(self, method, url, **kwargs):
                self.calls.append({"method": method, "url": url, **kwargs})
                return FakeResponse()

        service = service_module.QzoneService(types.SimpleNamespace())
        service._session = FakeSession()
        service._session_timeout_seconds = service._api_timeout_seconds()
        service._ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
            cookie_values={"uin": "o100000001", "ptcz": "noise"},
        )
        service._ctx_at = 9999999999

        result = await service._request(
            "GET",
            "https://example.com",
            headers={"Cookie": "uin=100000001;p_skey=p_skey"},
        )

        self.assertEqual(result["code"], 0)
        self.assertIsNone(service._session.calls[0]["cookies"])

    async def test_h5_post_json_native_h2_empty_response_falls_back_to_httpx(self):
        service_module = _load_qzone_service()
        client_module = sys.modules[CLIENT_SERVICE_MODULE_NAME]
        plugin = types.SimpleNamespace(qzone_conf={"qzone_api_timeout_seconds": 120})
        service = service_module.QzoneService(plugin)
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
            cookie_values={"uin": "o100000001"},
        )
        service.native_calls = 0

        async def native_h2(ctx_arg, url, payload, *, params=None, headers=None):
            service.native_calls += 1
            service.native_headers = dict(headers or {})
            return 200, ""

        class FakeResponse:
            status_code = 200
            text = '{"ret":0,"data":{"session":"cover-session"}}'

        class FakeAsyncClient:
            def __init__(self, *, http2, timeout, headers):
                self.http2 = http2
                self.timeout = timeout
                self.headers = headers
                self.calls = []

            async def post(self, url, *, params=None, content=None, headers=None):
                self.calls.append({"url": url, "params": params, "content": content, "headers": headers})
                return FakeResponse()

            async def aclose(self):
                return None

        fake_httpx = types.SimpleNamespace(
            AsyncClient=FakeAsyncClient,
            TimeoutException=TimeoutError,
            HTTPError=Exception,
        )

        try:
            with (
                patch.object(service, "_h5_post_json_native_h2", native_h2),
                patch.object(client_module, "httpx", fake_httpx),
                patch.object(client_module.importlib.util, "find_spec", lambda name: object() if name == "h2" else None),
            ):
                result = await service._h5_post_json(
                    ctx,
                    "https://h5.qzone.qq.com/webapp/json/sliceUpload/FileBatchControl/covermd5",
                    {"hello": "world"},
                    params={"g_tk": ctx.gtk},
                    label="cover-init",
                    prefer_native_h2=True,
                )

            self.assertEqual(service.native_calls, 1)
            self.assertIn("uin=100000001", service.native_headers["Cookie"])
            self.assertEqual(result["data"]["session"], "cover-session")
            self.assertEqual(result["_transport"], "HTTP/2")
        finally:
            await service.close()

    async def test_h5_post_json_http2_gateway_timeout_retries_http11(self):
        service_module = _load_qzone_service()
        client_module = sys.modules[CLIENT_SERVICE_MODULE_NAME]
        plugin = types.SimpleNamespace(qzone_conf={"qzone_api_timeout_seconds": 120})
        service = service_module.QzoneService(plugin)
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
            cookie_values={"uin": "o100000001"},
        )

        class H2Response:
            status_code = 504
            text = "<html><body>504 Gateway Time-out</body></html>"

        class FakeAsyncClient:
            def __init__(self, *, http2, timeout, headers):
                self.http2 = http2
                self.timeout = timeout
                self.headers = headers
                self.calls = []

            async def post(self, url, *, params=None, content=None, headers=None):
                self.calls.append({"url": url, "params": params, "content": content, "headers": headers})
                return H2Response()

            async def aclose(self):
                return None

        class H1Response:
            status = 200

            async def text(self):
                return '{"ret":0,"data":{"session":"video-session"}}'

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

        class FakeSession:
            closed = False

            def __init__(self):
                self.calls = []

            def post(self, url, **kwargs):
                self.calls.append({"url": url, **kwargs})
                return H1Response()

            async def close(self):
                self.closed = True

        async def no_sleep(_seconds):
            return None

        fake_httpx = types.SimpleNamespace(
            AsyncClient=FakeAsyncClient,
            TimeoutException=TimeoutError,
            HTTPError=Exception,
        )

        service._session = FakeSession()
        service._session_timeout_seconds = service._api_timeout_seconds()
        try:
            with (
                patch.object(client_module, "httpx", fake_httpx),
                patch.object(client_module.importlib.util, "find_spec", lambda name: object() if name == "h2" else None),
                patch.object(service_module.asyncio, "sleep", no_sleep),
            ):
                result = await service._h5_post_json(
                    ctx,
                    "https://h5.qzone.qq.com/webapp/json/sliceUpload/FileBatchControl",
                    {"hello": "world"},
                    params={"g_tk": ctx.gtk},
                    label="video-init",
                )

            self.assertEqual(result["ret"], 0)
            self.assertEqual(result["data"]["session"], "video-session")
            self.assertEqual(result["_transport"], "HTTP/1.1")
            self.assertEqual(len(service._h2_session.calls), 1)
            self.assertEqual(len(service._session.calls), 1)
            self.assertEqual(service._session.calls[0]["data"], b'{"hello":"world"}')
        finally:
            await service.close()

    async def test_h5_post_bytes_http2_gateway_timeout_retries_http11(self):
        service_module = _load_qzone_service()
        client_module = sys.modules[CLIENT_SERVICE_MODULE_NAME]
        plugin = types.SimpleNamespace(qzone_conf={"qzone_api_timeout_seconds": 120})
        service = service_module.QzoneService(plugin)
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
            cookie_values={"uin": "o100000001"},
        )

        class H2Response:
            status_code = 504
            text = "<html><body>504 Gateway Time-out</body></html>"

        class FakeAsyncClient:
            def __init__(self, *, http2, timeout, headers):
                self.calls = []

            async def post(self, url, *, params=None, content=None, headers=None):
                self.calls.append({"url": url, "params": params, "content": content, "headers": headers})
                return H2Response()

            async def aclose(self):
                return None

        class H1Response:
            status = 200

            async def text(self):
                return '{"ret":0,"data":{"uploaded":true}}'

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

        class FakeSession:
            closed = False

            def __init__(self):
                self.calls = []

            def post(self, url, **kwargs):
                self.calls.append({"url": url, **kwargs})
                return H1Response()

            async def close(self):
                self.closed = True

        async def no_sleep(_seconds):
            return None

        fake_httpx = types.SimpleNamespace(
            AsyncClient=FakeAsyncClient,
            TimeoutException=TimeoutError,
            HTTPError=Exception,
        )

        service._session = FakeSession()
        service._session_timeout_seconds = service._api_timeout_seconds()
        try:
            with (
                patch.object(client_module, "httpx", fake_httpx),
                patch.object(client_module.importlib.util, "find_spec", lambda name: object() if name == "h2" else None),
                patch.object(service_module.asyncio, "sleep", no_sleep),
            ):
                result = await service._h5_post_bytes(
                    ctx,
                    "https://h5.qzone.qq.com/webapp/json/sliceUpload/FileUploadVideo",
                    b"video-bytes",
                    "application/octet-stream",
                    label="video-chunk-0",
                )

            self.assertEqual(result["ret"], 0)
            self.assertEqual(result["_transport"], "HTTP/1.1")
            self.assertEqual(len(service._h2_session.calls), 1)
            self.assertEqual(len(service._session.calls), 1)
            self.assertEqual(service._session.calls[0]["data"], b"video-bytes")
            self.assertEqual(service._session.calls[0]["headers"]["Content-Type"], "application/octet-stream")
        finally:
            await service.close()

    async def test_h5_post_json_native_h2_gateway_timeout_retries_http11(self):
        service_module = _load_qzone_service()
        plugin = types.SimpleNamespace(qzone_conf={"qzone_api_timeout_seconds": 120})
        service = service_module.QzoneService(plugin)
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
            cookie_values={"uin": "o100000001"},
        )
        service.native_calls = 0

        async def native_h2(ctx_arg, url, payload, *, params=None, headers=None):
            service.native_calls += 1
            return 504, "<html><body>504 Gateway Time-out</body></html>"

        class H1Response:
            status = 200

            async def text(self):
                return '{"ret":0,"data":{"session":"cover-session"}}'

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

        class FakeSession:
            closed = False

            def __init__(self):
                self.calls = []

            def post(self, url, **kwargs):
                self.calls.append({"url": url, **kwargs})
                return H1Response()

            async def close(self):
                self.closed = True

        async def no_sleep(_seconds):
            return None

        service._session = FakeSession()
        service._session_timeout_seconds = service._api_timeout_seconds()
        try:
            with (
                patch.object(service, "_h5_post_json_native_h2", native_h2),
                patch.object(service_module.asyncio, "sleep", no_sleep),
            ):
                result = await service._h5_post_json(
                    ctx,
                    "https://h5.qzone.qq.com/webapp/json/sliceUpload/FileBatchControl/covermd5",
                    {"hello": "world"},
                    params={"g_tk": ctx.gtk},
                    label="cover-init",
                    prefer_native_h2=True,
                )

            self.assertEqual(service.native_calls, 1)
            self.assertEqual(result["data"]["session"], "cover-session")
            self.assertEqual(result["_transport"], "HTTP/1.1")
            self.assertEqual(len(service._session.calls), 1)
        finally:
            await service.close()

    async def test_h5_error_message_keeps_5xx_gateway_status_as_primary_error(self):
        service_module = _load_qzone_service()
        service = service_module.QzoneService(types.SimpleNamespace())

        message = service._h5_error_message(
            {
                "code": -1,
                "message": "QQ 空间返回内容不是结构化数据",
                "_endpoint": "video-init",
                "_http_status": 504,
                "_raw_length": 164,
                "_transport": "HTTP/2",
            },
            "QQ 空间 H5 上传接口暂不可用（HTTP 504）",
        )

        self.assertIn("QQ 空间 H5 上传接口暂不可用（HTTP 504）", message)
        self.assertIn("阶段: video-init", message)
        self.assertIn("传输: HTTP/2", message)
        self.assertNotIn("返回内容不是结构化数据", message)

    async def test_publish_retry_reuses_uploaded_images_after_submit_timeout(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.upload_calls = 0
                self.submit_calls = 0

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                )

            async def _upload_image(self, image):
                self.upload_calls += 1
                return "picbo", "richval"

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True):
                self.submit_calls += 1
                if data.get("pic_bo") != "picbo" or data.get("richval") != "richval":
                    raise AssertionError("没有复用已上传图片参数")
                if self.submit_calls == 1:
                    raise RuntimeError("QQ 空间请求超时（60秒）")
                return {"code": 0, "tid": "123", "now": 1718000000}

        async def no_sleep(_seconds):
            return None

        service = Service()
        with patch.object(service_module.asyncio, "sleep", no_sleep):
            post = await service.publish_post(text="测试", images=[b"image"])

        self.assertEqual(post.tid, "123")
        self.assertEqual(service.upload_calls, 1)
        self.assertEqual(service.submit_calls, 2)

    async def test_publish_video_url_appends_link_to_text(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.submit_data = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                )

            async def _submit_post(self, ctx, data):
                self.submit_data = dict(data)
                return {"code": 0, "tid": "video-url", "now": 1718000000}

        service = Service()
        post = await service.publish_post(text="测试视频", videos=["https://example.com/video.mp4"])

        self.assertEqual(service.submit_data["con"], "测试视频\n\nVideo: https://example.com/video.mp4")
        self.assertEqual(post.videos, ["https://example.com/video.mp4"])

    async def test_publish_raw_video_requires_album_video_dynamic_after_upload(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.uploaded = []
                self.submit_data = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                )

            async def _upload_local_video(self, ctx, video):
                self.uploaded.append((ctx.uin, video))
                return {
                    "source": "base64://AAAA",
                    "vid": "vid-1",
                    "urls": ["https://qzone.qq.com/video.mp4"],
                }

            async def _submit_post(self, ctx, data):
                self.submit_data = dict(data)
                return {"code": 0, "tid": "local-video", "now": 1718000000}

        service = Service()

        with self.assertRaisesRegex(RuntimeError, "未生成相册视频动态"):
            await service.publish_post(text="本地视频", videos=[{"source": "base64://AAAA", "require_album_dynamic": True}])

        self.assertEqual(service.uploaded[0][0], 100000001)
        self.assertEqual(service.uploaded[0][1]["source"], "base64://AAAA")
        self.assertEqual(service.uploaded[0][1]["publish_text"], "本地视频")
        self.assertIsNone(service.submit_data)

    async def test_publish_local_video_uses_album_video_dynamic(self):
        service_module = _load_qzone_service()
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
            handle.write(b"video")
            video_path = handle.name

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.submit_calls = 0
                self.upload_calls = 0
                self.confirm_calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                )

            async def _upload_local_video(self, ctx, video):
                self.upload_calls += 1
                return {
                    "source": video_path,
                    "vid": "vid-album",
                    "urls": [],
                    "feed_post": service_module.QzonePost(
                        tid="album-cellid",
                        uin=ctx.uin,
                        text="",
                        videos=["qzone://video/vid-album", "https://photovideo.photo.qq.com/vid-album.f0.mp4"],
                        appid=4,
                        busi_param={
                            "daily_share_result_type": service_module.QzoneService.RESULT_TYPE_ALBUM_VIDEO_DYNAMIC,
                            "daily_share_vid": "vid-album",
                        },
                    ),
                }

            async def _submit_post(self, ctx, data):
                self.submit_calls += 1
                raise AssertionError("album video dynamic path must not submit another mood")

        try:
            service = Service()

            post = await service.publish_post(text="相册视频", videos=[{"source": video_path, "require_album_dynamic": True}])

            self.assertEqual(post.tid, "album-cellid")
            self.assertEqual(post.text, "相册视频")
            self.assertEqual(post.videos, ["qzone://video/vid-album", "https://photovideo.photo.qq.com/vid-album.f0.mp4"])
            self.assertEqual(post.appid, 4)
            self.assertEqual(service.submit_calls, 0)
            self.assertEqual(service.upload_calls, 1)
            self.assertEqual(service.confirm_calls, [])
        finally:
            Path(video_path).unlink(missing_ok=True)

    async def test_prepare_publish_videos_returns_public_album_video_post(self):
        service_module = _load_qzone_service()
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
            handle.write(b"video")
            video_path = handle.name

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.upload_calls = 0

            async def _upload_local_video(self, ctx, video):
                self.upload_calls += 1
                return {
                    "source": video_path,
                    "vid": "vid-h5",
                    "urls": [],
                    "feed_post": service_module.QzonePost(
                        tid="album-h5",
                        uin=ctx.uin,
                        text="",
                        videos=["qzone://video/vid-h5"],
                        appid=4,
                        busi_param={"daily_share_vid": "vid-h5"},
                    ),
                }

        try:
            service = Service()
            ctx = service_module.QzoneContext(100000001, "skey", "p_skey", "测试用户乙")

            links, post_videos, album_video_post = await service._prepare_publish_videos(
                ctx,
                [{"source": video_path, "require_album_dynamic": True}],
                text="fallback",
            )

            self.assertEqual(service.upload_calls, 1)
            self.assertEqual(links, [])
            self.assertIsNotNone(album_video_post)
            self.assertEqual(album_video_post.tid, "album-h5")
            self.assertEqual(album_video_post.text, "fallback")
            self.assertEqual(album_video_post.appid, 4)
            self.assertEqual(post_videos, ["qzone://video/vid-h5"])
        finally:
            Path(video_path).unlink(missing_ok=True)

    async def test_local_video_without_album_dynamic_is_rejected_before_text_fallback(self):
        service_module = _load_qzone_service()
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
            handle.write(b"video")
            video_path = handle.name

        class Bot:
            async def call_action(self, action, **params):
                return {"retcode": 0, "data": {"fid": "tid-native", "ugc_right": 1, "visibility": "public"}}

        class CtxService:
            def __init__(self):
                self.bot = Bot()
                self.bot_map = {"aiocqhttp": self.bot}

            def _get_bot_instance(self, _adapter_id):
                return None

            def _is_onebot_platform(self, key):
                return "aiocqhttp" in key

            def _get_onebot_bot(self, *args, **kwargs):
                return self.bot

            async def _bot_call_action(self, bot, action, **params):
                return await bot.call_action(action, **params)

        try:
            class Service(service_module.QzoneService):
                async def _upload_local_video(self, ctx, video):
                    return {
                        "source": video_path,
                        "vid": "vid-only",
                        "urls": [],
                    }

            service = Service(types.SimpleNamespace(_cached_qq_adapter_id="", ctx_service=CtxService()))
            ctx = service_module.QzoneContext(100000001, "skey", "p_skey", "测试用户乙")

            with self.assertRaisesRegex(RuntimeError, "未生成相册视频动态"):
                await service._prepare_publish_videos(
                    ctx,
                    [{"source": video_path, "require_album_dynamic": True}],
                    text="no vid",
                )
        finally:
            Path(video_path).unlink(missing_ok=True)

    async def test_publish_local_video_returns_album_dynamic_without_text_only_shell(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.submit_calls = 0
                self.submit_data = None
                self.deleted = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                )

            async def _upload_local_video(self, ctx, video):
                return {
                    "source": "local.mp4",
                    "vid": "vid-from-upload",
                    "urls": [],
                    "feed_post": service_module.QzonePost(
                        tid="album-cellid",
                        uin=ctx.uin,
                        text="",
                        videos=["qzone://video/vid-from-upload"],
                        appid=4,
                        busi_param={
                            "daily_share_cellid": "album-cellid",
                            "daily_share_busi_param_1": "photo-sloc",
                            "daily_share_vid": "vid-from-upload",
                        },
                    ),
                }

            async def _submit_post(self, ctx, data):
                self.submit_calls += 1
                self.submit_data = dict(data)
                return {"code": 0, "tid": "text-only-shell", "now": 1718000000}

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                raise AssertionError(url)

            async def _delete_own_post_by_tid(self, ctx, tid):
                self.deleted.append(tid)

        service = Service()

        post = await service.publish_post(text="本地视频", videos=[{"source": "local.mp4", "require_album_dynamic": True}])

        self.assertEqual(post.tid, "album-cellid")
        self.assertEqual(post.text, "本地视频")
        self.assertEqual(post.appid, 4)
        self.assertEqual(post.videos, ["qzone://video/vid-from-upload"])
        self.assertEqual(service.submit_calls, 0)
        self.assertIsNone(service.submit_data)
        self.assertEqual(service.deleted, [])

    async def test_publish_local_video_requires_confirmed_album_dynamic(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.submit_calls = 0

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                )

            async def _upload_local_video(self, ctx, video):
                return {
                    "source": "local.mp4",
                    "vid": "vid-from-upload",
                    "urls": [],
                    "feed_post": None,
                }

            async def _submit_post(self, ctx, data):
                self.submit_calls += 1
                raise AssertionError("local video without public album feed must not submit text shell")

        service = Service()

        with self.assertRaisesRegex(RuntimeError, "未生成相册视频动态"):
            await service.publish_post(text="本地视频", videos=[{"source": "local.mp4", "require_album_dynamic": True}])

        self.assertEqual(service.submit_calls, 0)

    async def test_confirm_uploaded_video_in_library_reports_vid_hit(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))

            async def _query_qzone_video_library(self, ctx, *, start=0, count=20):
                return {
                    "code": 0,
                    "data": {
                        "Videos": [
                            {
                                "vid": "vid-from-library",
                                "url": "https://example.com/video-from-library.mp4",
                            }
                        ]
                    },
                }

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        result = await service._confirm_uploaded_video_in_library(ctx, "vid-from-library")

        self.assertTrue(result["confirmed"])
        self.assertEqual(result["vid"], "vid-from-library")
        self.assertEqual(result["urls"], ["https://example.com/video-from-library.mp4"])

    async def test_upload_local_video_keeps_upload_fields_empty_when_only_vid_returned(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.play_time = None

            async def _local_media_payload(self, media, *, default_name, label):
                return {
                    "source": "local.mp4",
                    "filename": "video.mp4",
                    "size": 3,
                    "md5": "md5hex",
                    "data": b"abc",
                }

            async def _probe_video_play_time(self, video_payload):
                return 4321

            async def _init_h5_video_upload(
                self,
                ctx,
                video_payload,
                *,
                title,
                description,
                play_time,
                client_key="",
                upload_time=0,
            ):
                self.play_time = play_time
                return {"ret": 0, "data": {"flag": 1, "biz": {"sVid": "vid-from-upload"}}}

            async def _confirm_album_video_public(self, ctx, vid, *, cover_result=None, submitted_at=0):
                return None

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        uploaded = await service._upload_local_video(ctx, {"source": "local.mp4"})

        self.assertEqual(uploaded["vid"], "vid-from-upload")
        self.assertNotIn("publish_fields", uploaded)
        self.assertEqual(service.play_time, 4321)

    async def test_upload_local_video_requests_album_video_feed(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.init_kwargs = {}
                self.cover_kwargs = {}

            async def _local_media_payload(self, media, *, default_name, label):
                return {
                    "source": "local.mp4",
                    "filename": "video.mp4",
                    "size": 3,
                    "md5": "md5hex",
                    "data": b"abc",
                }

            async def _init_h5_video_upload(
                self,
                ctx,
                video_payload,
                *,
                title,
                description,
                play_time,
                client_key="",
                upload_time=0,
            ):
                self.init_kwargs = {
                    "title": title,
                    "description": description,
                    "play_time": play_time,
                    "client_key": client_key,
                    "upload_time": upload_time,
                }
                return {"ret": 0, "data": {"flag": 1, "biz": {"sVid": "vid-from-upload"}}}

            async def _extract_video_cover_frame(self, video_payload):
                return ""

            async def _qzone_album_for_video(self, ctx, video):
                return {"id": "album-1", "name": "album"}

            async def _upload_video_cover(self, ctx, cover, **kwargs):
                self.cover_kwargs = dict(kwargs)
                return {"ret": 0, "data": {"flag": 1}}

            async def _confirm_album_video_public(self, ctx, vid, *, cover_result=None, submitted_at=0):
                return None

            async def _confirm_uploaded_video_in_library(self, ctx, vid):
                return {"confirmed": False, "vid": vid}

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        await service._upload_local_video(
            ctx,
            {
                "source": "local.mp4",
                "cover": "cover.jpg",
                "description": "视频元数据描述",
                "duration_ms": 5678,
                "publish_text": "今天测试一下",
            },
        )

        self.assertEqual(service.init_kwargs["description"], "今天测试一下")
        self.assertEqual(service.cover_kwargs["description"], "今天测试一下")
        self.assertEqual(service.cover_kwargs["need_feeds"], 1)
        self.assertNotIn("business_data", service.cover_kwargs)

    async def test_prepare_publish_videos_rejects_only_uploaded_vid_for_album_video_publish(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())

            async def _upload_local_video(self, ctx, video):
                return {
                    "source": "local.mp4",
                    "vid": "vid-from-upload",
                    "urls": [],
                }

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        with self.assertRaisesRegex(RuntimeError, "未生成相册视频动态"):
            await service._prepare_publish_videos(
                ctx,
                [{"source": "local.mp4", "require_album_dynamic": True}],
            )

    def test_video_debug_payload_redacts_large_and_sensitive_fields(self):
        service_module = _load_qzone_service()
        service = service_module.QzoneService(types.SimpleNamespace())

        with patch.object(service_module.logger, "debug") as debug:
            service._debug_qzone_video_payload(
                "upload",
                {
                    "ret": 0,
                    "data": "base64-video-chunk",
                    "cookie": "uin=100000001;p_skey=secret",
                    "video_token": "secret-video-token",
                    "video_data": "base64-video-data",
                    "biz": {
                        "sVid": "vid-1",
                        "video_id": "vid-1",
                        "url3": "https://example.com/video.mp4",
                        "richval": "",
                    },
                },
            )

        message = str(debug.call_args.args[0])
        self.assertIn("QQ 空间视频返回探针(upload)", message)
        self.assertIn("biz.sVid=vid-1", message)
        self.assertIn("biz.url3=https://example.com/video.mp4", message)
        self.assertIn("video_token=<redacted>", message)
        self.assertIn("video_data=<redacted>", message)
        self.assertNotIn("base64-video-chunk", message)
        self.assertNotIn("base64-video-data", message)
        self.assertNotIn("secret", message)

    async def test_upload_local_video_uses_video_library_url_after_cover_failure(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))

            async def _local_media_payload(self, media, *, default_name, label):
                return {
                    "source": "local.mp4" if label == "视频" else "cover.jpg",
                    "filename": "video.mp4" if label == "视频" else "cover.jpg",
                    "size": 3,
                    "md5": "md5hex" if label == "视频" else "covermd5",
                    "data": b"abc",
                }

            async def _init_h5_video_upload(
                self,
                ctx,
                video_payload,
                *,
                title,
                description,
                play_time,
                client_key="",
                upload_time=0,
            ):
                return {"ret": 0, "data": {"flag": 1, "biz": {"sVid": "vid-from-upload"}}}

            async def _extract_video_cover_frame(self, video_payload):
                return ""

            async def _qzone_album_for_video(self, ctx, video):
                return {"id": "album-1", "name": "默认相册"}

            async def _upload_video_cover(self, *args, **kwargs):
                raise RuntimeError("QQ 空间返回为空")

            async def _confirm_album_video_public(self, ctx, vid, *, cover_result=None, submitted_at=0):
                return None

            async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
                return []

            async def query_recent_posts(self, *, pos=0, num=5, with_detail=False):
                return []

            async def query_home_posts(self, *, pos=0, num=5):
                return []

            async def _query_qzone_video_library(self, ctx, *, start=0, count=20):
                return {
                    "code": 0,
                    "data": {
                        "Videos": [
                            {
                                "vid": "vid-from-upload",
                                "url": "https://example.com/video-from-library.mp4",
                            }
                        ]
                    },
                }

        async def no_sleep(_seconds):
            return None

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        with patch.object(service_module.asyncio, "sleep", no_sleep):
            uploaded = await service._upload_local_video(
                ctx,
                {"source": "local.mp4", "cover": "cover.jpg", "description": "视频正文"},
            )

        self.assertEqual(uploaded["vid"], "vid-from-upload")
        self.assertEqual(uploaded["urls"], ["https://example.com/video-from-library.mp4"])
        self.assertNotIn("publish_fields", uploaded)

    async def test_publish_post_does_not_treat_album_video_feed_as_mood_video(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))
                self.submit_called = False
                self.submit_data = None
                self.repaired_tid = ""
                self.deleted = []
                self.confirm_calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                )

            async def _local_media_payload(self, media, *, default_name, label):
                if label == "视频":
                    return {
                        "source": "local.mp4",
                        "filename": "video.mp4",
                        "size": 3,
                        "md5": "md5hex",
                        "data": b"abc",
                    }
                return {
                    "filename": "cover.jpg",
                    "size": 3,
                    "md5": "covermd5",
                    "data": b"abc",
                }

            async def _init_h5_video_upload(
                self,
                ctx,
                video_payload,
                *,
                title,
                description,
                play_time,
                client_key="",
                upload_time=0,
            ):
                return {"ret": 0, "data": {"flag": 1, "biz": {"sVid": "vid-cover-feed"}}}

            async def _qzone_album_for_video(self, ctx, video):
                return {"id": "album-1", "name": "默认相册"}

            async def _upload_video_cover(self, *args, **kwargs):
                return {"ret": 0, "data": {"flag": 1}}

            async def _confirm_album_video_public(self, ctx, vid, *, cover_result=None, submitted_at=0):
                return service_module.QzonePost(
                    tid="album-video",
                    uin=ctx.uin,
                    text="",
                    videos=["qzone://video/vid-cover-feed", "https://photovideo.photo.qq.com/vid-cover-feed.f0.mp4"],
                    appid=4,
                    busi_param={
                        "daily_share_result_type": "album_video_dynamic",
                        "daily_share_vid": "vid-cover-feed",
                    },
                )

            async def _query_qzone_video_library(self, ctx, *, start=0, count=20):
                return {"code": 0, "data": {"Videos": []}}

            async def _submit_post(self, ctx, data):
                self.submit_called = True
                self.submit_data = dict(data)
                raise AssertionError("album video dynamic path must not submit mood")

            async def _delete_own_post_by_tid(self, ctx, tid):
                self.deleted.append(tid)

        async def no_sleep(_seconds):
            return None

        service = Service()
        with patch.object(service_module.asyncio, "sleep", no_sleep):
            post = await service.publish_post(
                text="视频正文",
                videos=[
                    {
                        "source": "local.mp4",
                        "cover": "cover.jpg",
                        "description": "视频正文",
                        "require_album_dynamic": True,
                    }
                ],
            )

        self.assertEqual(post.tid, "album-video")
        self.assertEqual(post.text, "视频正文")
        self.assertEqual(post.appid, 4)
        self.assertEqual(
            post.videos,
            ["qzone://video/vid-cover-feed", "https://photovideo.photo.qq.com/vid-cover-feed.f0.mp4"],
        )
        self.assertFalse(service.submit_called)
        self.assertIsNone(service.submit_data)
        self.assertEqual(service.repaired_tid, "")
        self.assertEqual(service.deleted, [])
        self.assertEqual(service.confirm_calls, [])

    async def test_album_dynamic_local_video_requires_public_album_video_confirmation(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))
                self.submit_data = None
                self.deleted = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                )

            async def _local_media_payload(self, media, *, default_name, label):
                if label == "视频":
                    return {
                        "source": "local.mp4",
                        "filename": "video.mp4",
                        "size": 3,
                        "md5": "md5hex",
                        "data": b"abc",
                    }
                return {
                    "filename": "cover.jpg",
                    "size": 3,
                    "md5": "covermd5",
                    "data": b"abc",
                }

            async def _init_h5_video_upload(
                self,
                ctx,
                video_payload,
                *,
                title,
                description,
                play_time,
                client_key="",
                upload_time=0,
            ):
                return {"ret": 0, "data": {"flag": 1, "biz": {"sVid": "vid-cover-feed"}}}

            async def _qzone_album_for_video(self, ctx, video):
                return {"id": "album-1", "name": "默认相册"}

            async def _upload_video_cover(self, *args, **kwargs):
                return {"ret": 0, "data": {"flag": 1}}

            async def _confirm_album_video_public(self, ctx, vid, *, cover_result=None, submitted_at=0):
                return None

            async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
                return []

            async def query_recent_posts(self, *, pos=0, num=5, with_detail=False):
                return [
                    service_module.QzonePost(
                        tid="video-feed",
                        uin=100000001,
                        text="上传了一个视频",
                        videos=[
                            "https://video.qq.com/from-album.mp4",
                            "qzone://video/album-only-vid",
                        ],
                        create_time=9999999999,
                        appid=4,
                    )
                ]

            async def query_home_posts(self, *, pos=0, num=5):
                return []

            async def _query_qzone_video_library(self, ctx, *, start=0, count=20):
                return {"code": 0, "data": {"Videos": []}}

            async def _submit_post(self, ctx, data):
                self.submit_data = dict(data)
                return {"code": 0, "tid": "video-link-fallback", "now": 1718000000}

            async def _delete_own_post_by_tid(self, ctx, tid):
                self.deleted.append(tid)

        async def no_sleep(_seconds):
            return None

        service = Service()
        with patch.object(service_module.asyncio, "sleep", no_sleep):
            with self.assertRaisesRegex(RuntimeError, "未确认相册视频可公开展示"):
                await service.publish_post(
                    text="视频正文",
                    videos=[
                        {
                            "source": "local.mp4",
                            "cover": "cover.jpg",
                            "description": "视频正文",
                            "require_album_dynamic": True,
                        }
                    ],
                )

        self.assertIsNone(service.submit_data)
        self.assertEqual(service.deleted, [])

    async def test_upload_local_video_prefers_extracted_cover_frame_and_cleans_it(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self, extracted_cover):
                super().__init__(types.SimpleNamespace(qzone_conf={}))
                self.extracted_cover = extracted_cover
                self.cover_arg = None

            async def _local_media_payload(self, media, *, default_name, label):
                if label == "视频":
                    return {
                        "source": "local.mp4",
                        "filename": "video.mp4",
                        "size": 3,
                        "md5": "md5hex",
                        "data": b"abc",
                    }
                return {
                    "filename": "cover.jpg",
                    "size": 3,
                    "md5": "covermd5",
                    "data": b"abc",
                }

            async def _init_h5_video_upload(
                self,
                ctx,
                video_payload,
                *,
                title,
                description,
                play_time,
                client_key="",
                upload_time=0,
            ):
                return {"ret": 0, "data": {"flag": 1, "biz": {"sVid": "vid-cover-feed"}}}

            async def _extract_video_cover_frame(self, video_payload):
                return self.extracted_cover

            async def _qzone_album_for_video(self, ctx, video):
                return {"id": "album-1", "name": "默认相册"}

            async def _upload_video_cover(self, ctx, cover, **kwargs):
                self.cover_arg = cover
                return {"ret": 0, "data": {"flag": 1}}

            async def _confirm_album_video_public(self, ctx, vid, *, cover_result=None, submitted_at=0):
                return None

            async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
                return []

            async def query_recent_posts(self, *, pos=0, num=5, with_detail=False):
                return [
                    service_module.QzonePost(
                        tid="video-feed",
                        uin=100000001,
                        text="视频正文",
                        videos=["qzone://video/vid-cover-feed"],
                        create_time=9999999999,
                    )
                ]

            async def query_home_posts(self, *, pos=0, num=5):
                return []

        async def no_sleep(_seconds):
            return None

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
            handle.write(b"cover")
            extracted_cover = handle.name

        service = Service(extracted_cover)
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )
        with patch.object(service_module.asyncio, "sleep", no_sleep):
            uploaded = await service._upload_local_video(
                ctx,
                {"source": "local.mp4", "cover": "original-cover.jpg", "description": "视频正文"},
            )

        self.assertEqual(service.cover_arg, extracted_cover)
        self.assertFalse(Path(extracted_cover).exists())
        self.assertIsNone(uploaded["feed_post"])
        self.assertEqual(uploaded["cover_upload_result"]["vid"], "vid-cover-feed")

    async def test_upload_local_video_uses_default_album_with_album_feed(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))
                self.cover_kwargs = None

            async def _local_media_payload(self, media, *, default_name, label):
                if label == "视频":
                    return {
                        "source": "local.mp4",
                        "filename": "video.mp4",
                        "size": 1234,
                        "md5": "md5hex",
                        "data": b"abc",
                    }
                return {
                    "filename": "cover.jpg",
                    "size": 3,
                    "md5": "covermd5",
                    "data": b"abc",
                }

            async def _resolve_video_play_time(self, video, video_payload):
                return 5678

            async def _init_h5_video_upload(
                self,
                ctx,
                video_payload,
                *,
                title,
                description,
                play_time,
                client_key="",
                upload_time=0,
            ):
                return {"ret": 0, "data": {"flag": 1, "biz": {"sVid": "vid-cover-feed"}}}

            async def _extract_video_cover_frame(self, video_payload):
                return ""

            async def _qzone_album_for_video(self, ctx, video):
                return {
                    "id": "",
                    "name": self.DEFAULT_VIDEO_ALBUM_NAME,
                    "album_type_id": self.DEFAULT_VIDEO_ALBUM_TYPE_ID,
                    "default": True,
                }

            async def _upload_video_cover(self, ctx, cover, **kwargs):
                self.cover_kwargs = dict(kwargs)
                return {
                    "ret": 0,
                    "data": {
                        "flag": 1,
                        "biz": {
                            "sAlbumID": "album-default",
                            "sPhotoID": "photo-default",
                            "sSloc": "photo-default",
                        },
                    },
                }

            async def _confirm_album_video_public(self, ctx, vid, *, cover_result=None, submitted_at=0):
                self.probed_vid = vid
                self.probed_cover = cover_result
                return None

            async def _confirm_uploaded_video_in_library(self, ctx, vid):
                return {"confirmed": False, "vid": vid}

            async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
                return []

            async def query_recent_posts(self, *, pos=0, num=5, with_detail=False):
                return []

            async def query_home_posts(self, *, pos=0, num=5):
                return []

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        uploaded = await service._upload_local_video(
            ctx,
            {"source": "local.mp4", "cover": "cover.jpg", "description": "视频正文"},
        )

        self.assertEqual(uploaded["vid"], "vid-cover-feed")
        self.assertEqual(service.cover_kwargs["default_album"], True)
        self.assertEqual(service.cover_kwargs["album_type_id"], service.DEFAULT_VIDEO_ALBUM_TYPE_ID)
        self.assertEqual(service.cover_kwargs["need_feeds"], 1)
        self.assertEqual(service.cover_kwargs["description"], "视频正文")
        self.assertEqual(service.cover_kwargs["video_size"], 1234)
        self.assertEqual(service.cover_kwargs["duration_ms"], 5678)
        self.assertEqual(service.probed_vid, "vid-cover-feed")
        self.assertEqual(service.probed_cover["data"]["biz"]["sAlbumID"], "album-default")

    async def test_confirm_album_video_public_accepts_same_vid_public_video_url(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))
                self.floatview_args = None

            async def _query_qzone_photo_floatview(self, ctx, album_id, photo_key, *, retry_login=True):
                self.floatview_args = (album_id, photo_key)
                return {
                    "code": 0,
                    "data": {
                        "photos": [
                            {
                                "svid": "vid-public",
                                "priv": 0,
                                "accessright": 1,
                                "videourl": "https://photovideo.photo.qq.com/video.mp4",
                                "desc": "今天测试一下",
                            }
                        ]
                    },
                }

            async def _query_qzone_album_photos(self, ctx, album_id, *, start=0, count=20, retry_login=True):
                return {"code": 0, "data": {"photos": []}}

            async def _query_qzone_album_info(self, ctx, album_id, *, retry_login=True):
                return {"code": 0, "data": {"priv": 1}}

            async def _query_qzone_video_library(self, ctx, *, start=0, count=20, retry_login=True):
                return {"code": 0, "data": {"videos": []}}

            async def _probe_public_album_video_url(self, url):
                self.probed_url = url
                return {"state": "success", "status_code": 206, "content_type": "video/mp4"}

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        post = await service._confirm_album_video_public(
            ctx,
            "vid-public",
            cover_result={
                "data": {
                    "biz": {
                        "sAlbumID": "album-default",
                        "sPhotoID": "photo-default",
                        "sSloc": "photo-default",
                    }
                }
            },
            submitted_at=1718000000,
        )

        self.assertIsNotNone(post)
        self.assertEqual(post.appid, 4)
        self.assertEqual(post.text, "今天测试一下")
        self.assertIn("qzone://video/vid-public", post.videos)
        self.assertEqual(service.floatview_args, ("album-default", "photo-default"))
        self.assertEqual(service.probed_url, "https://photovideo.photo.qq.com/video.mp4")
        self.assertEqual(post.busi_param["daily_share_album_id"], "album-default")
        self.assertEqual(post.busi_param["daily_share_photo_id"], "photo-default")

    async def test_confirm_album_video_public_rejects_private_mood_log_album(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))
                self.probed_url = ""

            async def _query_qzone_photo_floatview(self, ctx, album_id, photo_key, *, retry_login=True):
                return {
                    "code": 0,
                    "data": {
                        "photos": [
                            {
                                "svid": "vid-private",
                                "videourl": "https://photovideo.photo.qq.com/video.mp4",
                                "desc": "今天测试一下",
                            }
                        ],
                        "topic": {
                            "topicId": "album-default",
                            "topicName": "说说和日志相册",
                            "priv": 3,
                            "pypriv": 3,
                        },
                    },
                }

            async def _query_qzone_album_photos(self, ctx, album_id, *, start=0, count=20, retry_login=True):
                return {"code": 0, "data": {"photos": []}}

            async def _query_qzone_album_info(self, ctx, album_id, *, retry_login=True):
                return {"code": 0, "data": {"priv": 3, "pypriv": 3}}

            async def _query_qzone_video_library(self, ctx, *, start=0, count=20, retry_login=True):
                return {"code": 0, "data": {"videos": []}}

            async def _probe_public_album_video_url(self, url):
                self.probed_url = url
                return {"state": "success", "status_code": 206, "content_type": "video/mp4"}

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        post = await service._confirm_album_video_public(
            ctx,
            "vid-private",
            cover_result={
                "data": {
                    "biz": {
                        "sAlbumID": "album-default",
                        "sPhotoID": "photo-default",
                        "sSloc": "photo-default",
                    }
                }
            },
            submitted_at=1718000000,
        )

        self.assertIsNone(post)
        self.assertEqual(service.probed_url, "")

    async def test_confirm_album_video_public_rejects_video_library_when_album_context_private(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))
                self.probed_url = ""

            async def _query_qzone_photo_floatview(self, ctx, album_id, photo_key, *, retry_login=True):
                return {
                    "code": 0,
                    "data": {
                        "photos": [],
                        "topic": {
                            "topicId": "album-default",
                            "topicName": "说说和日志相册",
                            "priv": 3,
                            "pypriv": 3,
                        },
                    },
                }

            async def _query_qzone_album_photos(self, ctx, album_id, *, start=0, count=20, retry_login=True):
                return {"code": 0, "data": {"photoList": []}}

            async def _query_qzone_album_info(self, ctx, album_id, *, retry_login=True):
                return {"code": 0, "data": {"priv": 3, "pypriv": 3}}

            async def _query_qzone_video_library(self, ctx, *, start=0, count=20, retry_login=True):
                return {
                    "code": 0,
                    "data": {
                        "Videos": [
                            {
                                "vid": "vid-private-library",
                                "priv": 0,
                                "url": "https://photovideo.photo.qq.com/vid-private-library.f0.mp4",
                            }
                        ]
                    },
                }

            async def _probe_public_album_video_url(self, url):
                self.probed_url = url
                return {"state": "success", "status_code": 206, "content_type": "video/mp4"}

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        post = await service._confirm_album_video_public(
            ctx,
            "vid-private-library",
            cover_result={
                "data": {
                    "biz": {
                        "sAlbumID": "album-default",
                        "sPhotoID": "photo-default",
                        "sSloc": "photo-default",
                    }
                }
            },
            submitted_at=1718000000,
        )

        self.assertIsNone(post)
        self.assertEqual(service.probed_url, "")

    def test_album_video_context_extracts_share_fields(self):
        service_module = _load_qzone_service()

        context = service_module.QzoneService._album_video_context(
            {
                "data": {
                    "photos": [
                        {
                            "topicId": "album-id",
                            "lloc": "photo-id",
                            "video_info": {
                                "video_share_h5": (
                                    "https://h5.qzone.qq.com/ugc/share/video?"
                                    "uin=100000001&appid=4&cellid=album-cell&busi_param_1=photo-sloc"
                                )
                            },
                        }
                    ]
                }
            }
        )

        self.assertEqual(context["album_id"], "album-id")
        self.assertEqual(context["photo_id"], "photo-id")
        self.assertEqual(context["cellid"], "album-cell")
        self.assertEqual(context["busi_param_1"], "photo-sloc")
        self.assertIn("ugc/share/video", context["video_share_h5"])

    async def test_prepare_publish_videos_returns_album_video_post_as_publish_result(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))

            async def _upload_local_video(self, ctx, video):
                return {
                    "source": "local.mp4",
                    "vid": "vid-public",
                    "urls": [],
                    "feed_post": service_module.QzonePost(
                        tid="album-video",
                        uin=ctx.uin,
                        text="",
                        videos=["qzone://video/vid-public"],
                        appid=4,
                        busi_param={"daily_share_result_type": "album_video_dynamic"},
                    ),
                }

            async def query_recent_posts(self, *, pos=0, num=5, with_detail=False):
                return []

            async def query_home_posts(self, *, pos=0, num=5):
                return []

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        links, post_videos, album_video_post = await service._prepare_publish_videos(
            ctx,
            [{"source": "local.mp4", "require_album_dynamic": True}],
            text="今天测试一下",
        )

        self.assertEqual(links, [])
        self.assertIsNotNone(album_video_post)
        self.assertEqual(post_videos, ["qzone://video/vid-public"])
        self.assertEqual(album_video_post.tid, "album-video")
        self.assertEqual(album_video_post.text, "今天测试一下")
        self.assertEqual(album_video_post.appid, 4)

    async def test_prepare_publish_videos_can_opt_into_album_video_dynamic_feed(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))

            async def _upload_local_video(self, ctx, video):
                return {
                    "source": "local.mp4",
                    "vid": "vid-public",
                    "urls": [],
                    "feed_post": service_module.QzonePost(
                        tid="photo-sloc",
                        uin=ctx.uin,
                        text="",
                        videos=["qzone://video/vid-public", "https://photovideo.photo.qq.com/vid-public.f0.mp4"],
                        appid=4,
                        busi_param={
                            "daily_share_result_type": "album_video_dynamic",
                            "daily_share_vid": "vid-public",
                            "album_video_public": {"public": True},
                        },
                    ),
                }

            async def query_recent_posts(self, *, pos=0, num=5, with_detail=False):
                return [
                    service_module.QzonePost(
                        tid="dynamic-feed",
                        uin=100000001,
                        text="上传了一个视频",
                        videos=["qzone://video/vid-public"],
                        create_time=9999999999,
                        appid=4,
                    )
                ]

            async def query_home_posts(self, *, pos=0, num=5):
                return []

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        links, post_videos, album_video_post = await service._prepare_publish_videos(
            ctx,
            [{"source": "local.mp4", "require_album_dynamic": True}],
            text="今天测试一下",
            submitted_at=9999999900,
        )

        self.assertEqual(links, [])
        self.assertEqual(post_videos, ["qzone://video/vid-public", "https://photovideo.photo.qq.com/vid-public.f0.mp4"])
        self.assertIsNotNone(album_video_post)
        self.assertEqual(album_video_post.tid, "photo-sloc")
        self.assertEqual(album_video_post.text, "今天测试一下")
        self.assertEqual(album_video_post.appid, 4)
        self.assertEqual(album_video_post.busi_param["daily_share_result_type"], "album_video_dynamic")

    async def test_extract_video_cover_frame_returns_empty_without_ffmpeg(self):
        service_module = _load_qzone_service()

        service = service_module.QzoneService(types.SimpleNamespace())
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
            handle.write(b"not-real-video")
            video_path = handle.name
        try:
            with patch.object(service, "_ffmpeg_path", return_value=""):
                cover = await service._extract_video_cover_frame({"source": video_path})
        finally:
            Path(video_path).unlink(missing_ok=True)

        self.assertEqual(cover, "")

    async def test_album_dynamic_local_video_with_only_uploaded_vid_is_rejected(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())

            async def _upload_local_video(self, ctx, video):
                return {
                    "source": "local.mp4",
                    "vid": "vid-1",
                    "urls": [],
                }

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        with self.assertRaisesRegex(RuntimeError, "未生成相册视频动态"):
            await service._prepare_publish_videos(
                ctx,
                [{"source": "local.mp4", "require_album_dynamic": True}],
            )

    async def test_non_native_local_video_falls_back_to_text_with_vid(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())

            async def _upload_local_video(self, ctx, video):
                return {
                    "source": "local.mp4",
                    "vid": "",
                    "urls": [],
                }

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        video_links, post_videos, album_video_post = await service._prepare_publish_videos(
            ctx,
            [{"source": "local.mp4"}],
        )

        self.assertIsNone(album_video_post)
        self.assertEqual(video_links, [])
        self.assertEqual(post_videos, ["local.mp4"])

    async def test_non_native_uploaded_local_video_does_not_append_library_url_to_text(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.submit_data = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                    cookie_values={"uin": "o100000001"},
                )

            async def _upload_local_video(self, ctx, video):
                return {
                    "source": "local.mp4",
                    "vid": "vid-1",
                    "urls": ["https://example.com/from-library.mp4"],
                }

            async def _submit_post(self, ctx, data):
                self.submit_data = dict(data)
                return {"code": 0, "tid": "fallback-video-link", "now": 1718000000}

        service = Service()
        post = await service.publish_post(text="本地视频", videos=[{"source": "local.mp4"}])

        self.assertEqual(service.submit_data["con"], "本地视频")
        self.assertEqual(post.videos, ["qzone://video/vid-1"])

    async def test_h5_video_upload_uses_qzonephoto_slice_protocol(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.calls = []

            async def _h5_post_json(self, ctx, url, payload, *, params=None, label="", prefer_native_h2=False, headers=None):
                self.calls.append({"url": url, "payload": payload, "params": dict(params or {}), "label": label})
                if "FileBatchControl" in url:
                    return {"ret": 0, "data": {"session": "sess-1", "slice_size": 2}}
                return {"ret": 0, "data": {"flag": 1, "biz": {"sVid": "vid-1"}}}

            async def _h5_post_bytes(self, ctx, url, body, content_type, *, params=None, label="", headers=None):
                self.calls.append(
                    {
                        "url": url,
                        "body": body,
                        "content_type": content_type,
                        "params": dict(params or {}),
                        "label": label,
                        "headers": dict(headers or {}),
                    }
                )
                return {"ret": 0, "data": {"flag": 1, "biz": {"sVid": "vid-1"}}}

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )
        video_payload = {
            "filename": "video.mp4",
            "size": 3,
            "md5": "md5hex",
            "sha1": "sha1hex",
            "data": b"abc",
        }

        init = await service._init_h5_video_upload(
            ctx,
            video_payload,
            title="title",
            description="desc",
            play_time=1200,
            client_key="100000001_1718000000000",
            upload_time=1718000000,
        )
        result = await service._upload_h5_file_chunks(
            ctx,
            video_payload,
            session_id=init["data"]["session"],
            slice_size=init["data"]["slice_size"],
            is_video=True,
        )

        self.assertEqual(result["data"]["biz"]["sVid"], "vid-1")
        init_call = service.calls[0]
        self.assertTrue(init_call["url"].endswith("/FileBatchControl/sha1hex"))
        control_req = init_call["payload"]["control_req"][0]
        self.assertEqual(control_req["appid"], "video_qzone")
        self.assertEqual(control_req["token"], {"type": 4, "data": "p_skey", "appid": 5})
        self.assertEqual(control_req["biz_req"]["sDesc"], "desc")
        self.assertEqual(control_req["biz_req"]["iPlayTime"], 1200)
        self.assertEqual(control_req["biz_req"]["iUploadTime"], 1718000000)
        self.assertEqual(control_req["biz_req"]["extend_info"]["clientkey"], "100000001_1718000000000")
        self.assertNotIn("iBusiNessType", control_req["biz_req"])
        self.assertNotIn("vBusiNessData", control_req["biz_req"])
        upload_call = service.calls[1]
        self.assertEqual(init_call["label"], "video-init")
        self.assertEqual(upload_call["label"], "video-chunk-1")
        self.assertTrue(upload_call["url"].endswith("/FileUploadVideo"))
        self.assertEqual(upload_call["params"]["g_tk"], ctx.gtk)
        self.assertEqual(upload_call["params"]["offset"], 0)
        self.assertEqual(upload_call["params"]["end"], 2)
        self.assertEqual(upload_call["params"]["total"], 3)
        self.assertEqual(upload_call["params"]["type"], "form")
        self.assertIn("multipart/form-data", upload_call["content_type"])
        body_text = service_module.QzoneService._multipart_text(upload_call["body"])
        self.assertIn('name="appid"', body_text)
        self.assertIn("video_qzone", body_text)
        self.assertIn('name="cmd"', body_text)
        self.assertIn("FileUploadVideo", body_text)
        self.assertIn('name="biz_req.iUploadType"', body_text)
        self.assertIn("\r\n0\r\n", body_text)

    async def test_h5_headers_include_full_qzone_cookie_context(self):
        service_module = _load_qzone_service()

        service = service_module.QzoneService(types.SimpleNamespace())
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
            cookie_values={
                "uin": "o100000001",
                "p_uin": "o100000001",
                "pt4_token": "pt-token",
                "extra": "value",
            },
        )

        cookie = service._h5_headers(ctx)["Cookie"]

        self.assertIn("uin=100000001", cookie)
        self.assertIn("p_uin=100000001", cookie)
        self.assertIn("p_skey=p_skey", cookie)
        self.assertIn("skey=skey", cookie)
        self.assertIn("pt4_token=pt-token", cookie)
        self.assertIn("extra=value", cookie)

    async def test_duration_ms_from_ffmpeg_output(self):
        service_module = _load_qzone_service()

        duration = service_module.QzoneService._duration_ms_from_text(
            "Input #0\n  Duration: 00:00:07.36, start: 0.000000, bitrate: 1024 kb/s"
        )

        self.assertEqual(duration, 7360)

    async def test_h5_video_cover_upload_matches_qzonephoto_image_chunk_protocol(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.calls = []

            async def _local_media_payload(self, media, *, default_name, label):
                return {
                    "source": "cover.jpg",
                    "filename": "cover.jpg",
                    "size": 3,
                    "md5": "covermd5",
                    "data": b"abc",
                }

            async def _h5_post_json(self, ctx, url, payload, *, params=None, label="", prefer_native_h2=False, headers=None):
                self.calls.append(
                    {
                        "url": url,
                        "payload": payload,
                        "params": dict(params or {}),
                        "label": label,
                        "prefer_native_h2": prefer_native_h2,
                        "headers": dict(headers or {}),
                    }
                )
                if "FileBatchControl" in url:
                    return {"ret": 0, "data": {"session": "cover-session", "slice_size": 2}}
                return {"ret": 0, "data": {"flag": 1}}

            async def _h5_post_bytes(self, ctx, url, body, content_type, *, params=None, label="", headers=None):
                self.calls.append(
                    {
                        "url": url,
                        "body": body,
                        "content_type": content_type,
                        "params": dict(params or {}),
                        "label": label,
                        "headers": dict(headers or {}),
                    }
                )
                return {"ret": 0, "data": {"flag": 1}}

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        result = await service._upload_video_cover(
            ctx,
            "cover.jpg",
            filename="video.mp4",
            vid="vid-cover-feed",
            album_id="",
            album_name=service.DEFAULT_VIDEO_ALBUM_NAME,
            album_type_id=service.DEFAULT_VIDEO_ALBUM_TYPE_ID,
            default_album=True,
            client_key="100000001_1718000000000",
            description="视频正文",
            video_size=1234,
            duration_ms=5678,
            need_feeds=1,
        )

        self.assertEqual(result["data"]["flag"], 1)
        init_call = service.calls[0]
        control_req = init_call["payload"]["control_req"][0]
        self.assertEqual(control_req["appid"], "pic_qzone")
        self.assertEqual(control_req["env"], {"refer": "qzone", "deviceInfo": "h5"})
        self.assertEqual(control_req["biz_req"]["iNeedFeeds"], 1)
        self.assertEqual(control_req["biz_req"]["sPicDesc"], "视频正文")
        self.assertNotIn("iBusiNessType", control_req["biz_req"])
        self.assertNotIn("vBusiNessData", control_req["biz_req"])
        self.assertEqual(control_req["biz_req"]["mapExt"]["mobile_fakefeeds_clientkey"], "100000001_1718000000000")
        self.assertEqual(control_req["biz_req"]["sAlbumID"], "")
        self.assertEqual(control_req["biz_req"]["sAlbumName"], "")
        self.assertEqual(control_req["biz_req"]["iAlbumTypeID"], service.DEFAULT_VIDEO_ALBUM_TYPE_ID)
        map_params = control_req["biz_req"]["stExtendInfo"]["mapParams"]
        external_map_ext = control_req["biz_req"]["stExternalMapExt"]
        self.assertEqual(map_params["vid"], "vid-cover-feed")
        self.assertNotIn("albumid", map_params)
        self.assertNotIn("album_id", map_params)
        self.assertNotIn("topicId", map_params)
        self.assertEqual(map_params["priv"], "1")
        self.assertEqual(map_params["privacy"], "1")
        self.assertEqual(map_params["accessright"], "1")
        self.assertEqual(map_params["ugc_right"], "1")
        self.assertEqual(map_params["who"], "1")
        self.assertEqual(map_params["raw_size"], "3")
        self.assertNotIn("albumid", external_map_ext)
        self.assertEqual(external_map_ext["priv"], "1")
        self.assertEqual(external_map_ext["privacy"], "1")
        self.assertEqual(external_map_ext["accessright"], "1")
        self.assertEqual(external_map_ext["mix_isOriginalVideo"], "0")
        self.assertEqual(external_map_ext["mix_videoSize"], "1234")
        self.assertEqual(external_map_ext["mix_time"], "5678")
        self.assertEqual(external_map_ext["is_pic_video_mix_feeds"], "1")
        upload_call = service.calls[1]
        self.assertEqual(init_call["label"], "cover-init")
        self.assertTrue(init_call["prefer_native_h2"])
        self.assertEqual(upload_call["label"], "cover-chunk-1")
        self.assertTrue(upload_call["url"].endswith("/FileUpload"))
        self.assertEqual(upload_call["params"]["g_tk"], ctx.gtk)
        self.assertEqual(upload_call["params"]["type"], "form")
        self.assertEqual(init_call["headers"]["Cookie"], "uin=100000001;p_skey=p_skey")
        self.assertEqual(upload_call["headers"]["Cookie"], "uin=100000001;p_skey=p_skey")
        body_text = service_module.QzoneService._multipart_text(upload_call["body"])
        self.assertIn("pic_qzone", body_text)
        self.assertIn("FileUpload", body_text)
        self.assertIn('name="biz_req.iUploadType"', body_text)
        self.assertIn("\r\n2\r\n", body_text)

    async def test_h5_video_cover_retries_with_full_cookie_after_login_expired(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.calls = []
                self.context_calls = 0
                self.invalidated = False

            async def context(self):
                self.context_calls += 1
                return service_module.QzoneContext(
                    uin=100000001,
                    skey=f"skey-{self.context_calls}",
                    p_skey=f"p_skey-{self.context_calls}",
                    nickname="测试用户乙",
                    cookie_values={"pt4_token": f"pt-token-{self.context_calls}"},
                )

            def invalidate(self):
                self.invalidated = True

            async def _local_media_payload(self, media, *, default_name, label):
                return {
                    "source": "cover.jpg",
                    "filename": "cover.jpg",
                    "size": 3,
                    "md5": "covermd5",
                    "data": b"abc",
                }

            async def _h5_post_json(self, ctx, url, payload, *, params=None, label="", prefer_native_h2=False, headers=None):
                self.calls.append({"label": label, "headers": dict(headers or {})})
                if label == "cover-init" and len([call for call in self.calls if call["label"] == "cover-init"]) == 1:
                    return {"ret": -3000, "msg": "对不起，您尚未登录或者登录超时。"}
                if label == "cover-init":
                    return {"ret": 0, "data": {"session": "cover-session", "slice_size": 2}}
                return {"ret": 0, "data": {"flag": 1}}

            async def _h5_post_bytes(self, ctx, url, body, content_type, *, params=None, label="", headers=None):
                self.calls.append({"label": label, "headers": dict(headers or {})})
                return {"ret": 0, "data": {"flag": 1}}

        service = Service()
        ctx = await service.context()

        result = await service._upload_video_cover(
            ctx,
            "cover.jpg",
            filename="video.mp4",
            vid="vid-cover-feed",
            album_id="album-1",
            album_name="默认相册",
        )

        init_calls = [call for call in service.calls if call["label"] == "cover-init"]
        self.assertEqual(result["data"]["flag"], 1)
        self.assertFalse(service.invalidated)
        self.assertEqual(init_calls[0]["headers"]["Cookie"], "uin=100000001;p_skey=p_skey-1")
        self.assertIn("pt4_token=pt-token-1", init_calls[1]["headers"]["Cookie"])
        self.assertIn("p_skey=p_skey-1", init_calls[1]["headers"]["Cookie"])
        self.assertEqual(service.calls[-1]["headers"]["Cookie"], init_calls[1]["headers"]["Cookie"])

    async def test_select_public_video_album_supports_sort_and_class_payloads(self):
        service_module = _load_qzone_service()

        payload = {
            "code": 0,
            "data": {
                "albumListModeSort": [
                    {"id": "", "name": "缺少ID"},
                    {"id": "locked", "name": "不能上传", "allowUpload": 0},
                ],
                "albumListModeClass": [
                    {
                        "albumList": [
                            {"id": "daily", "name": "日常", "allowUpload": 1, "priv": "1"},
                            {"id": "video-public", "name": "说说和视频相册", "allowUpload": 1, "priv": "1"},
                        ]
                    }
                ],
            },
        }

        selected = service_module.QzoneService._select_public_video_album(payload)
        matched = service_module.QzoneService._select_public_video_album(payload, album_name="说说和视频相册")

        self.assertEqual(selected, {"id": "video-public", "name": "说说和视频相册"})
        self.assertEqual(matched, {"id": "video-public", "name": "说说和视频相册"})

    async def test_select_public_video_album_rejects_system_and_normal_album(self):
        service_module = _load_qzone_service()

        payload = {
            "code": 0,
            "data": {
                "albumListModeSort": [
                    {"id": "mood", "name": "说说和日志相册", "allowUpload": 1, "priv": "3", "handset": "7"},
                    {"id": "daily", "name": "日常相册", "allowUpload": 1, "priv": "1"},
                ],
            },
        }

        selected = service_module.QzoneService._select_public_video_album(payload)

        self.assertIsNone(selected)

    async def test_qzone_album_for_video_prefers_named_public_video_album(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))
                self.request = None

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.request = {
                    "method": method,
                    "url": url,
                    "params": dict(params or {}),
                    "headers": dict(headers or {}),
                }
                return {
                    "code": 0,
                    "data": {
                        "albumListModeClass": [
                            {
                                "albumList": [
                                    {"id": "mood", "name": "说说和日志相册", "allowUpload": 1, "priv": "3", "handset": "7"},
                                    {"id": "album-1", "name": "普通相册", "allowUpload": 1, "priv": "1"},
                                    {"id": "video-public", "name": "说说和视频相册", "allowUpload": 1, "priv": "1"},
                                ]
                            }
                        ]
                    },
                }

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        album = await service._qzone_album_for_video(ctx, {"source": "local.mp4"})

        self.assertEqual(
            album,
            {
                "id": "video-public",
                "name": "说说和视频相册",
            },
        )
        self.assertEqual(service.request["method"], "GET")
        self.assertEqual(service.request["url"], service.ALBUM_LIST_JSON_URL)
        self.assertEqual(service.request["params"]["hostUin"], 100000001)
        self.assertEqual(service.request["params"]["uin"], "100000001")
        self.assertEqual(service.request["params"]["format"], "json")
        self.assertEqual(service.request["headers"]["Cookie"], "uin=100000001;p_skey=p_skey")

    async def test_qzone_album_for_video_creates_public_album_when_only_system_album_exists(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))
                self.calls = []

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.calls.append({"method": method, "url": url, "data": dict(data or {})})
                if method == "POST":
                    return {"code": 0, "data": {"albumid": "created-public", "albumname": "说说和视频相册", "priv": "1"}}
                return {
                    "code": 0,
                    "data": {
                        "albumListModeSort": [
                            {"id": "mood", "name": "说说和日志相册", "allowUpload": 1, "priv": "3", "handset": "7"},
                        ]
                    },
                }

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        album = await service._qzone_album_for_video(ctx, {"source": "local.mp4"})

        self.assertEqual(album["id"], "created-public")
        self.assertEqual(album["name"], "说说和视频相册")
        self.assertEqual([call["method"] for call in service.calls], ["GET", "GET", "POST"])
        self.assertEqual(service.calls[-1]["data"]["albumname"], "说说和视频相册")
        self.assertEqual(service.calls[-1]["data"]["priv"], "1")

    async def test_qzone_album_for_video_creates_target_album_when_named_album_missing(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))
                self.calls = []

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.calls.append({"method": method, "url": url, "data": dict(data or {})})
                if method == "POST":
                    return {"code": 0, "data": {"albumid": "created-public", "albumname": "说说和视频相册", "priv": "1"}}
                return {
                    "code": 0,
                    "data": {
                        "albumListModeSort": [
                            {"id": "daily", "name": "日常相册", "allowUpload": 1, "priv": "1"},
                        ]
                    },
                }

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        album = await service._qzone_album_for_video(ctx, {"source": "local.mp4"})

        self.assertEqual(
            album,
            {
                "id": "created-public",
                "name": "说说和视频相册",
            },
        )
        self.assertEqual([call["method"] for call in service.calls], ["GET", "GET", "POST"])
        self.assertEqual(service.calls[-1]["data"]["albumname"], "说说和视频相册")

    async def test_qzone_album_for_video_creates_public_album_when_album_list_fails(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))
                self.calls = []

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.calls.append({"method": method, "url": url, "data": dict(data or {})})
                if method == "POST":
                    return {"code": 0, "albumid": "created-public"}
                return {"code": -1, "message": "QQ 空间返回为空", "_http_status": 500}

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        album = await service._qzone_album_for_video(ctx, {"source": "local.mp4"})

        self.assertEqual(
            album,
            {
                "id": "created-public",
                "name": "说说和视频相册",
            },
        )
        self.assertEqual([call["method"] for call in service.calls], ["GET", "GET", "POST"])
        self.assertEqual(service.calls[-1]["data"]["priv"], "1")

    async def test_qzone_album_for_video_rechecks_list_when_create_returns_no_album_id(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))
                self.calls = []

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.calls.append({"method": method, "url": url, "data": dict(data or {})})
                if method == "POST":
                    return {"code": 0, "message": ""}
                if len([call for call in self.calls if call["method"] == "GET"]) >= 3:
                    return {
                        "code": 0,
                        "data": {
                            "albumListModeSort": [
                                {"id": "created-after-list", "name": "说说和视频相册", "allowUpload": 1, "priv": "1"},
                            ]
                        },
                    }
                return {"code": 0, "data": {"albumListModeSort": []}}

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        album = await service._qzone_album_for_video(ctx, {"source": "local.mp4"})

        self.assertEqual(album, {"id": "created-after-list", "name": "说说和视频相册"})
        self.assertEqual([call["method"] for call in service.calls], ["GET", "GET", "POST", "GET", "GET"])

    async def test_qzone_album_for_video_reads_json_album_endpoint_for_public_album(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))
                self.calls = []

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.calls.append({"method": method, "url": url, "params": dict(params or {})})
                if url == self.ALBUM_LIST_URL:
                    return {"code": 0, "data": {"albumListModeSort": []}}
                return {
                    "code": 0,
                    "data": {
                        "albumList": [
                            {"id": "json-public", "name": "说说和视频相册", "allowUpload": 1, "priv": "1", "handset": "0"},
                        ]
                    },
                }

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        album = await service._qzone_album_for_video(ctx, {"source": "local.mp4"})

        self.assertEqual(album["id"], "json-public")
        self.assertEqual(album["name"], "说说和视频相册")
        self.assertEqual(service.calls[0]["url"], service.ALBUM_LIST_URL)
        self.assertEqual(service.calls[1]["url"], service.ALBUM_LIST_JSON_URL)
        self.assertEqual(service.calls[0]["params"]["g_tk"], ctx.gtk)
        self.assertEqual(service.calls[1]["params"]["g_tk"], ctx.gtk)
        self.assertEqual(service.calls[1]["params"]["format"], "json")

    async def test_qzone_album_for_video_rebuilds_cookie_after_login_retry(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))
                self.calls = []
                self.context_calls = 0
                self.invalidated = False

            async def context(self):
                self.context_calls += 1
                return service_module.QzoneContext(
                    uin=100000001,
                    skey=f"skey-{self.context_calls}",
                    p_skey=f"p_skey-{self.context_calls}",
                    nickname="测试用户乙",
                )

            def invalidate(self):
                self.invalidated = True

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.calls.append({"headers": dict(headers or {}), "retry": retry})
                if len(self.calls) == 1:
                    return {"code": -1, "message": "QQ 空间返回为空", "_http_status": 403}
                return {
                    "code": 0,
                    "data": {
                        "albumListModeSort": [
                            {"id": "album-1", "name": "说说和视频相册", "allowUpload": 1, "priv": "1"},
                        ]
                    },
                }

        service = Service()
        album = await service._qzone_album_for_video(await service.context(), {"source": "local.mp4"})

        self.assertEqual(
            album,
            {
                "id": "album-1",
                "name": "说说和视频相册",
            },
        )
        self.assertFalse(service.invalidated)
        self.assertEqual(service.calls[0]["headers"]["Cookie"], "uin=100000001;p_skey=p_skey-1")
        self.assertIn("p_skey=p_skey-1", service.calls[1]["headers"]["Cookie"])
        self.assertIn("skey=skey-1", service.calls[1]["headers"]["Cookie"])
        self.assertFalse(service.calls[0]["retry"])

    async def test_qzone_album_for_video_ignores_explicit_album_and_uses_target_public_album(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                return {
                    "code": 0,
                    "data": {
                        "albumListModeSort": [
                            {"id": "video-public", "name": "说说和视频相册", "allowUpload": 1, "priv": "1"},
                        ]
                    },
                }

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        album = await service._qzone_album_for_video(
            ctx,
            {"source": "local.mp4", "albumId": "album-2", "albumName": "视频相册"},
        )

        self.assertEqual(album, {"id": "video-public", "name": "说说和视频相册"})

    async def test_upload_video_cover_uses_album_info_in_biz_req(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace(qzone_conf={}))
                self.calls = []

            async def _local_media_payload(self, media, *, default_name, label):
                return {
                    "filename": "cover.jpg",
                    "size": 3,
                    "md5": "covermd5",
                    "data": b"abc",
                }

            async def _h5_post_json(self, ctx, url, payload, *, params=None, label="", prefer_native_h2=False, headers=None):
                self.calls.append({"url": url, "payload": payload, "params": dict(params or {}), "label": label, "headers": dict(headers or {})})
                return {"ret": 0, "data": {"flag": 1, "biz": {"sAlbumID": "album-1", "sPhotoID": "photo-1", "sSloc": "photo-1"}}}

        service = Service()
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        result = await service._upload_video_cover(
            ctx,
            b"cover",
            filename="video.mp4",
            vid="vid-1",
            album_id="album-1",
            album_name="默认相册",
            client_key="100000001_1718000000000",
            upload_time=1718000000,
            video_size=4321,
            duration_ms=8765,
        )

        self.assertEqual(result["data"]["biz"]["sAlbumID"], "album-1")
        control_req = service.calls[0]["payload"]["control_req"][0]
        self.assertEqual(control_req["appid"], "pic_qzone")
        self.assertEqual(control_req["biz_req"]["sAlbumID"], "album-1")
        self.assertEqual(control_req["biz_req"]["sAlbumName"], "默认相册")
        self.assertEqual(control_req["biz_req"]["iAlbumTypeID"], 0)
        self.assertEqual(control_req["biz_req"]["iUploadTime"], 1718000000)
        map_params = control_req["biz_req"]["stExtendInfo"]["mapParams"]
        external_map_ext = control_req["biz_req"]["stExternalMapExt"]
        self.assertEqual(map_params["vid"], "vid-1")
        self.assertEqual(map_params["clientkey"], "100000001_1718000000000")
        self.assertEqual(map_params["albumid"], "album-1")
        self.assertEqual(map_params["album_id"], "album-1")
        self.assertEqual(map_params["topicId"], "album-1")
        self.assertEqual(map_params["privacy"], "1")
        self.assertEqual(map_params["accessright"], "1")
        self.assertEqual(map_params["raw_size"], "3")
        self.assertEqual(external_map_ext["albumid"], "album-1")
        self.assertEqual(external_map_ext["album_id"], "album-1")
        self.assertEqual(external_map_ext["topicId"], "album-1")
        self.assertEqual(external_map_ext["ugc_right"], "1")
        self.assertEqual(external_map_ext["who"], "1")
        self.assertEqual(external_map_ext["mix_videoSize"], "4321")
        self.assertEqual(external_map_ext["mix_time"], "8765")

    async def test_reply_comment_rejects_synthetic_short_own_thread_reply_before_submit(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.request_url = None
                self.request_data = None
                self.request_headers = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.request_url = url
                self.request_data = dict(data or {})
                self.request_headers = headers
                return {"code": 0}

        service = Service()
        post = service_module.QzonePost(uin=10001, tid="post-1", appid=311)
        parent = service_module.QzoneComment(uin=20002, nickname="Alice", tid="root-c1")
        child = service_module.QzoneComment(
            uin=20002,
            nickname="Alice",
            tid="root-c1_r_1_20002",
            submit_tid="1",
            parent_tid="root-c1",
        )
        service._post_cache[post.key] = post

        with self.assertRaises(RuntimeError) as ctx:
            await service.reply_comment(post.key, child, "thread reply", parent_comment=parent)

        self.assertIsNone(service.request_data)
        self.assertTrue(getattr(ctx.exception, "reply_verification_failed", False))
        self.assertEqual(getattr(ctx.exception, "verification_status"), "unsafe_synthetic_thread_target")

    async def test_reply_comment_rejects_synthetic_reused_short_id_before_submit(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.request_url = None
                self.request_data = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.request_url = url
                self.request_data = dict(data or {})
                return {"code": 0}

        service = Service()
        post = service_module.QzonePost(uin=10001, tid="post-1", appid=311)
        parent = service_module.QzoneComment(uin=20002, nickname="Friend", tid="11")
        child = service_module.QzoneComment(
            uin=20002,
            nickname="Friend",
            tid="11_r_1_20002",
            submit_tid="1",
            parent_tid="11",
            reply_to_tid="11_r_1_10001",
            reply_to_uin=10001,
        )
        service._post_cache[post.key] = post

        with self.assertRaises(RuntimeError) as ctx:
            await service.reply_comment(post.key, child, "third reply", parent_comment=parent)

        self.assertIsNone(service.request_data)
        self.assertTrue(getattr(ctx.exception, "reply_verification_failed", False))
        self.assertEqual(getattr(ctx.exception, "verification_status"), "unsafe_synthetic_thread_target")

    async def test_reply_comment_uses_h5_re_feeds_for_friend_post_self_parent(self):
        service_module = _load_qzone_service()

        class Service(_ConfirmedThreadVerificationMixin, service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.request_url = None
                self.request_data = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.request_url = url
                self.request_data = dict(data or {})
                return {"code": 0}

        service = Service()
        post = service_module.QzonePost(uin=30003, tid="post-1", appid=311)
        parent = service_module.QzoneComment(uin=10001, nickname="Me", tid="root-c1")
        child = service_module.QzoneComment(
            uin=30003,
            nickname="Alice",
            tid="reply-r2",
            parent_tid="root-c1",
        )
        service._post_cache[post.key] = post

        await service.reply_comment(post.key, child, "thread reply", parent_comment=parent)

        self.assertEqual(service.request_url, service.H5_COMMENT_URL)
        self.assertEqual(service.request_data["topicId"], "30003_post-1__1")
        self.assertEqual(service.request_data["hostUin"], 30003)
        self.assertEqual(service.request_data["uin"], 10001)
        self.assertEqual(service.request_data["commentId"], "root-c1")
        self.assertEqual(service.request_data["commentUin"], 10001)
        self.assertEqual(service.request_data["content"], "@{uin:30003,nick:Alice,auto:1} thread reply")
        self.assertEqual(service.request_data["format"], "fs")
        self.assertEqual(service.request_data["paramstr"], "2")
        self.assertEqual(service.request_data["qzreferrer"], "https://user.qzone.qq.com/30003")
        self.assertNotIn("t1_tid", service.request_data)
        self.assertNotIn("t1_uin", service.request_data)
        self.assertNotIn("t2_tid", service.request_data)
        self.assertNotIn("t2_uin", service.request_data)
        self.assertNotIn("replyUin", service.request_data)
        self.assertNotIn("parentTid", service.request_data)
        self.assertNotIn("replyId", service.request_data)
        self.assertNotIn("replyTid", service.request_data)

    async def test_reply_comment_keeps_existing_reply_mention(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.request_data = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.request_data = dict(data or {})
                return {"code": 0}

        service = Service()
        post = service_module.QzonePost(uin=10001, tid="post-1", appid=311)
        comment = service_module.QzoneComment(uin=20002, nickname="Alice", tid="root-c1")
        service._post_cache[post.key] = post

        await service.reply_comment(post.key, comment, "@{uin:20002,nick:Alice,auto:1} already mentioned")

        self.assertEqual(service.request_data["content"], "@{uin:20002,nick:Alice,auto:1} already mentioned")

    async def test_reply_comment_ignores_post_tid_parent_for_top_level_comment(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.request_data = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.request_data = dict(data or {})
                return {"code": 0}

        service = Service()
        post = service_module.QzonePost(uin=10001, tid="post-1", appid=311)
        comment = service_module.QzoneComment(
            uin=20002,
            nickname="Alice",
            tid="root-c1",
            parent_tid="post-1",
        )
        service._post_cache[post.key] = post

        await service.reply_comment(post.key, comment, "top level reply")

        self.assertEqual(service.request_data["commentId"], "root-c1")
        self.assertNotIn("parentTid", service.request_data)
        self.assertNotIn("replyId", service.request_data)
        self.assertNotIn("replyTid", service.request_data)

    async def test_comment_uses_h5_feed_payload(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.calls.append((url, dict(data or {}), dict(headers or {})))
                return {"code": 0}

        service = Service()
        post = service_module.QzonePost(uin=20002, tid="post-1", appid=311, busi_param={"from": "feeds"})
        service._post_cache[post.key] = post

        await service.comment(post.key, "hello")

        self.assertEqual(len(service.calls), 1)
        url, data, headers = service.calls[0]
        self.assertEqual(url, service.COMMENT_URL)
        self.assertEqual(data["topicId"], "20002_post-1__1")
        self.assertEqual(data["format"], "fs")
        self.assertEqual(data["feedsType"], 100)
        self.assertEqual(data["appid"], 311)
        self.assertEqual(data["paramstr"], "1")
        self.assertEqual(data["isSignIn"], "0")
        self.assertEqual(data["busi_param"], '{"from": "feeds"}')
        self.assertEqual(headers["Origin"], service.BASE_URL)

    async def test_reply_comment_thread_reply_uses_only_addreply_ugc_for_own_post(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.calls.append((url, dict(data or {})))
                return {"code": -10000, "message": "使用人数过多，请稍后再试"} if len(self.calls) == 1 else {"code": 0}

        service = Service()
        post = service_module.QzonePost(uin=10001, tid="post-1", appid=311)
        parent = service_module.QzoneComment(uin=30003, nickname="Alice", tid="root-c1")
        child = service_module.QzoneComment(
            uin=30003,
            nickname="Alice",
            tid="reply-r2",
            parent_tid="root-c1",
        )
        service._post_cache[post.key] = post

        with self.assertRaises(RuntimeError):
            await service.reply_comment(post.key, child, "thread reply", parent_comment=parent)

        self.assertEqual(len(service.calls), 1)
        self.assertEqual(service.calls[0][0], service.ADD_REPLY_UGC_URL)
        data = service.calls[0][1]
        self.assertEqual(data["topicId"], "10001_post-1")
        self.assertEqual(data["content"], "@{uin:30003,nick:Alice,auto:1} thread reply")
        self.assertEqual(data["format"], "fs")
        self.assertEqual(data["commentId"], "root-c1")
        self.assertEqual(data["commentUin"], 30003)
        self.assertNotIn("t1_uin", data)
        self.assertNotIn("t1_tid", data)
        self.assertNotIn("t2_uin", data)
        self.assertNotIn("t2_tid", data)
        self.assertNotIn("replyUin", data)
        self.assertNotIn("parentTid", data)
        self.assertNotIn("replyId", data)
        self.assertNotIn("replyTid", data)

    async def test_reply_comment_thread_reply_uses_h5_re_feeds_for_friend_post_self_parent(self):
        service_module = _load_qzone_service()

        class Service(_ConfirmedThreadVerificationMixin, service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.calls.append((url, dict(data or {})))
                return {"code": 0}

        service = Service()
        post = service_module.QzonePost(uin=20002, tid="post-1", appid=311)
        parent = service_module.QzoneComment(uin=10001, nickname="Me", tid="root-c1")
        child = service_module.QzoneComment(
            uin=30003,
            nickname="Alice",
            tid="reply-r2",
            parent_tid="root-c1",
        )
        service._post_cache[post.key] = post

        result = await service.reply_comment(post.key, child, "thread reply", parent_comment=parent)

        self.assertEqual(len(service.calls), 1)
        self.assertEqual(service.calls[0][0], service.H5_COMMENT_URL)
        self.assertEqual(result["transport"], "h5_re_feeds_parent")
        data = service.calls[0][1]
        self.assertEqual(data["topicId"], "20002_post-1__1")
        self.assertEqual(data["hostUin"], 20002)
        self.assertEqual(data["uin"], 10001)
        self.assertEqual(data["format"], "fs")
        self.assertEqual(data["commentId"], "root-c1")
        self.assertEqual(data["commentUin"], 10001)
        self.assertEqual(data["paramstr"], "2")
        self.assertEqual(data["qzreferrer"], "https://user.qzone.qq.com/20002")
        self.assertEqual(data["content"], "@{uin:30003,nick:Alice,auto:1} thread reply")
        self.assertNotIn("t1_uin", data)
        self.assertNotIn("t1_tid", data)
        self.assertNotIn("t2_uin", data)
        self.assertNotIn("t2_tid", data)
        self.assertNotIn("replyUin", data)
        self.assertNotIn("parentTid", data)
        self.assertNotIn("replyId", data)
        self.assertNotIn("replyTid", data)

    async def test_reply_comment_rejects_synthetic_sns_stable_reply_id_for_reused_short_id(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.calls.append((url, dict(data or {})))
                return {"code": 0}

        service = Service()
        post = service_module.QzonePost(uin=10001, tid="post-1", appid=311)
        parent = service_module.QzoneComment(uin=20002, nickname="Friend", tid="11")
        child = service_module.QzoneComment(
            uin=20002,
            nickname="Friend",
            tid="11_r_1_20002",
            submit_tid="1",
            parent_tid="11",
            reply_to_tid="11_r_1_10001",
            reply_to_uin=10001,
        )
        service._post_cache[post.key] = post

        with self.assertRaises(RuntimeError) as ctx:
            await service.reply_comment(post.key, child, "third reply", parent_comment=parent)

        self.assertEqual(service.calls, [])
        self.assertTrue(getattr(ctx.exception, "reply_verification_failed", False))
        self.assertEqual(getattr(ctx.exception, "verification_status"), "unsafe_synthetic_thread_target")

    async def test_reply_comment_rejects_synthetic_second_friend_follow_up_before_submit(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.calls = []
                self.detail_post = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.calls.append((url, dict(data or {})))
                return {"code": 0}

            async def detail(self, post_id):
                return self.detail_post

        service = Service()
        post = service_module.QzonePost(uin=100000001, tid="post-1", appid=311)
        parent = service_module.QzoneComment(uin=100000002, nickname="Friend", tid="4", submit_tid="4")
        child = service_module.QzoneComment(
            uin=100000002,
            nickname="Friend",
            tid="4_r_2_100000002",
            submit_tid="2",
            parent_tid="4",
            reply_to_tid="4",
            reply_to_uin=100000001,
        )
        service._post_cache[post.key] = post

        with self.assertRaises(RuntimeError) as ctx:
            await service.reply_comment(post.key, child, "reply", parent_comment=parent)

        self.assertEqual(service.calls, [])
        self.assertTrue(getattr(ctx.exception, "reply_verification_failed", False))
        self.assertEqual(getattr(ctx.exception, "verification_status"), "unsafe_synthetic_thread_target")
        self.assertEqual(getattr(ctx.exception, "attempted_targets"), [{"comment_id": "4_r_2_100000002", "comment_uin": 100000002}])

    async def test_reply_comment_avoids_short_id_when_parent_and_child_submit_id_collide(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.calls = []
                self.detail_post = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.calls.append((url, dict(data or {})))
                return {"code": 0}

            async def detail(self, post_id):
                return self.detail_post

        service = Service()
        post = service_module.QzonePost(uin=100000001, tid="post-1", appid=311)
        parent = service_module.QzoneComment(uin=100000002, nickname="Friend", tid="2", submit_tid="2")
        child = service_module.QzoneComment(
            uin=100000002,
            nickname="Friend",
            tid="2_r_2_100000002",
            submit_tid="2",
            parent_tid="2",
            reply_to_tid="2_r_1_100000001",
            reply_to_uin=100000001,
        )
        post.comments = [
            parent,
            service_module.QzoneComment(
                uin=100000001,
                nickname="Me",
                tid="2_r_1_100000001",
                submit_tid="1",
                raw_tid="1",
                parent_tid="2",
                reply_to_tid="2",
                raw_reply_to_tid="2",
                reply_to_uin=100000002,
                raw_reply_to_uin=100000002,
            ),
            child,
        ]
        service.detail_post = post
        service._post_cache[post.key] = post

        with self.assertRaises(RuntimeError) as ctx:
            await service.reply_comment(post.key, child, "reply", parent_comment=parent)

        self.assertEqual(service.calls[0][0], service.ADD_REPLY_UGC_URL)
        self.assertEqual(service.calls[0][1]["commentId"], "2")
        self.assertEqual(service.calls[0][1]["commentUin"], 100000002)
        self.assertEqual(service.calls[0][1]["topicId"], "100000001_post-1")
        self.assertNotIn("t2_tid", service.calls[0][1])
        self.assertNotIn("t2_uin", service.calls[0][1])
        self.assertTrue(getattr(ctx.exception, "reply_verification_failed", False))
        self.assertEqual(getattr(ctx.exception, "verification_status"), "not_found")

    async def test_verify_thread_reply_accepts_stable_target_even_when_raw_short_id_matches_parent(self):
        service_module = _load_qzone_service()
        post = service_module.QzonePost(
            uin=100000001,
            tid="post-1",
            comments=[
                service_module.QzoneComment(
                    uin=100000002,
                    nickname="Friend",
                    tid="2",
                    submit_tid="2",
                    content="出门了吗",
                    create_time=100,
                ),
                service_module.QzoneComment(
                    uin=100000002,
                    nickname="Friend",
                    tid="2_r_2_100000002",
                    submit_tid="2",
                    parent_tid="2",
                    reply_to_tid="2_r_1_100000001",
                    reply_to_uin=100000001,
                    content="@{uin:100000001,nick:Me,auto:1} 等你好久了",
                    create_time=120,
                ),
                service_module.QzoneComment(
                    uin=100000001,
                    nickname="Me",
                    tid="2_r_3_100000001",
                    submit_tid="3",
                    raw_tid="3",
                    parent_tid="2",
                    reply_to_tid="2_r_2_100000002",
                    raw_reply_to_tid="2",
                    reply_to_uin=100000002,
                    raw_reply_to_uin=100000002,
                    reply_to_tid_source="t2_tid",
                    content="@{uin:100000002,nick:Friend,auto:1} reply",
                    create_time=2000000000,
                ),
            ],
        )
        target = post.comments[1]
        parent = post.comments[0]

        result = service_module.QzoneService._verify_thread_reply_in_post(
            post,
            target,
            "@{uin:100000002,nick:Friend,auto:1} reply",
            self_uin=100000001,
            target_ids=service_module.QzoneService._reply_verification_target_ids(
                target,
                parent_comment=parent,
            ),
            parent_ids=service_module.QzoneService._comment_id_aliases(parent),
            before_ids=set(),
            submitted_at=1999999999,
        )

        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(result["verified_reply_tid"], "2_r_3_100000001")
        self.assertEqual(result["candidates"][-1]["raw_reply_to_tid"], "2")

    async def test_reply_comment_rejects_unsafe_thread_reply_without_legacy_fallback(self):
        service_module = _load_qzone_service()

        class Service(_ConfirmedThreadVerificationMixin, service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.calls.append((url, dict(data or {})))
                return {"code": -10049, "message": "该条内容已被删除"} if len(self.calls) == 1 else {"code": 0}

        service = Service()
        post = service_module.QzonePost(uin=100000001, tid="post-1", appid=311)
        parent = service_module.QzoneComment(uin=100000002, nickname="Friend", tid="4", submit_tid="4")
        child = service_module.QzoneComment(
            uin=100000002,
            nickname="Friend",
            tid="4_r_2_100000002",
            submit_tid="2",
            parent_tid="4",
            reply_to_tid="4_r_1_100000001",
            reply_to_uin=100000001,
        )
        service._post_cache[post.key] = post

        with self.assertRaises(RuntimeError) as ctx:
            await service.reply_comment(post.key, child, "reply", parent_comment=parent)

        self.assertEqual(service.calls, [])
        self.assertTrue(getattr(ctx.exception, "reply_verification_failed", False))
        self.assertEqual(getattr(ctx.exception, "verification_status"), "unsafe_synthetic_thread_target")

    async def test_reply_comment_rejects_thread_submit_that_lands_on_parent_floor(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.calls.append((url, dict(data or {})))
                return {"code": 0}

            async def detail(self, post_id):
                return service_module.QzonePost(
                    uin=100000001,
                    tid="post-1",
                    appid=311,
                    comments=[
                        service_module.QzoneComment(
                            uin=100000002,
                            nickname="Friend",
                            tid="4",
                            submit_tid="4",
                            content="出门了吗",
                            create_time=100,
                        ),
                        service_module.QzoneComment(
                            uin=100000001,
                            nickname="Me",
                            tid="4_r_1_100000001",
                            submit_tid="1",
                            parent_tid="4",
                            reply_to_tid="4",
                            reply_to_uin=100000002,
                            content="@{uin:100000002,nick:Friend,auto:1} 先回一下",
                            create_time=110,
                        ),
                        service_module.QzoneComment(
                            uin=100000002,
                            nickname="Friend",
                            tid="4_r_2_100000002",
                            submit_tid="2",
                            parent_tid="4",
                            reply_to_tid="4_r_1_100000001",
                            reply_to_uin=100000001,
                            content="@{uin:100000001,nick:Me,auto:1} 已经在路上了",
                            create_time=120,
                        ),
                        service_module.QzoneComment(
                            uin=100000001,
                            nickname="Me",
                            tid="4_r_3_100000001",
                            submit_tid="3",
                            parent_tid="4",
                            reply_to_tid="4",
                            reply_to_uin=100000002,
                            content="@{uin:100000002,nick:Friend,auto:1} reply",
                            create_time=2000000000,
                        ),
                    ],
                )

        service = Service()
        post = service_module.QzonePost(
            uin=100000001,
            tid="post-1",
            appid=311,
            comments=[
                service_module.QzoneComment(
                    uin=100000002,
                    nickname="Friend",
                    tid="4",
                    submit_tid="4",
                    content="出门了吗",
                ),
                service_module.QzoneComment(
                    uin=100000001,
                    nickname="Me",
                    tid="4_r_1_100000001",
                    submit_tid="1",
                    parent_tid="4",
                    reply_to_tid="4",
                    reply_to_uin=100000002,
                    content="@{uin:100000002,nick:Friend,auto:1} 先回一下",
                ),
                service_module.QzoneComment(
                    uin=100000002,
                    nickname="Friend",
                    tid="4_r_2_100000002",
                    submit_tid="2",
                    parent_tid="4",
                    reply_to_tid="4_r_1_100000001",
                    reply_to_uin=100000001,
                    content="@{uin:100000001,nick:Me,auto:1} 已经在路上了",
                ),
            ],
        )
        parent = post.comments[0]
        child = post.comments[2]
        service._post_cache[post.key] = post

        with self.assertRaises(RuntimeError) as ctx:
            await service.reply_comment(post.key, child, "reply", parent_comment=parent)

        self.assertTrue(getattr(ctx.exception, "reply_verification_failed", False))
        self.assertEqual(getattr(ctx.exception, "verification_status"), "parent_target")
        self.assertEqual(service.calls[0][0], service.ADD_REPLY_UGC_URL)
        self.assertEqual(service.calls[0][1]["topicId"], "100000001_post-1")
        self.assertEqual(service.calls[0][1]["commentId"], "4")
        self.assertEqual(service.calls[0][1]["commentUin"], 100000002)
        self.assertEqual(service.calls[0][1]["content"], "@{uin:100000002,nick:Friend,auto:1} reply")
        self.assertEqual(service.calls[0][1]["format"], "fs")
        self.assertEqual(service.calls[0][1]["code_version"], 1)
        self.assertEqual(service.calls[0][1]["with_fwd"], 0)
        self.assertIn("mood_v6/html/index.html", service.calls[0][1]["qzreferrer"])
        self.assertTrue(any(url == service.SNS_DELETE_COMMENT_URL for url, _data in service.calls))
        self.assertTrue(
            any(
                (data.get("comment_id") or data.get("commentId")) == "4_r_3_100000001"
                for _url, data in service.calls
            )
        )
        self.assertEqual(getattr(ctx.exception, "attempts")[0]["variant"], "pc_addreply_ugc_parent")
        self.assertEqual(getattr(ctx.exception, "attempts")[0]["transport"], "addreply_ugc")
        self.assertEqual(getattr(ctx.exception, "verification_cleanup")["status"], "deleted")

    async def test_thread_reply_addreply_ugc_variant_uses_parent_anchor(self):
        service_module = _load_qzone_service()
        post = service_module.QzonePost(
            uin=100000001,
            tid="post-1",
            appid=311,
            comments=[
                service_module.QzoneComment(uin=100000002, nickname="Friend", tid="4", submit_tid="4"),
                service_module.QzoneComment(
                    uin=100000001,
                    nickname="Me",
                    tid="4_r_1_100000001",
                    submit_tid="1",
                    parent_tid="4",
                    reply_to_tid="4",
                    reply_to_uin=100000002,
                ),
                service_module.QzoneComment(
                    uin=100000002,
                    nickname="Friend",
                    tid="4_r_2_100000002",
                    submit_tid="2",
                    raw_tid="2",
                    parent_tid="4",
                    reply_to_tid="4_r_1_100000001",
                    raw_reply_to_tid="1",
                    reply_to_uin=100000001,
                    raw_reply_to_uin=100000001,
                ),
            ],
        )
        parent = post.comments[0]
        child = post.comments[2]

        variants = service_module.QzoneService._thread_reply_payload_variants(
            post,
            child,
            parent,
            [{"comment_id": child.tid, "comment_uin": child.uin}],
        )

        self.assertEqual([item["name"] for item in variants], ["pc_addreply_ugc_parent"])
        self.assertEqual(variants[0]["comment_id"], "4_r_2_100000002")
        self.assertEqual(variants[0]["comment_uin"], 100000002)
        self.assertEqual(variants[0]["payload_comment_id"], "4")
        self.assertEqual(variants[0]["payload_t2_tid"], "4_r_2_100000002")
        self.assertEqual(variants[0]["topic_id"], "100000001_post-1")

    async def test_thread_reply_addreply_ugc_variant_allows_colliding_parent_and_child_ids(self):
        service_module = _load_qzone_service()
        post = service_module.QzonePost(
            uin=100000001,
            tid="post-1",
            appid=311,
            comments=[
                service_module.QzoneComment(uin=100000002, nickname="Friend", tid="2", submit_tid="2"),
                service_module.QzoneComment(
                    uin=100000001,
                    nickname="Me",
                    tid="2_r_1_100000001",
                    submit_tid="1",
                    raw_tid="1",
                    parent_tid="2",
                    reply_to_tid="2",
                    raw_reply_to_tid="2",
                    reply_to_uin=100000002,
                    raw_reply_to_uin=100000002,
                ),
                service_module.QzoneComment(
                    uin=100000002,
                    nickname="Friend",
                    tid="2_r_2_100000002",
                    submit_tid="2",
                    raw_tid="2",
                    parent_tid="2",
                    reply_to_tid="2",
                    raw_reply_to_tid="2",
                    reply_to_uin=100000001,
                    raw_reply_to_uin=100000001,
                ),
            ],
        )
        parent = post.comments[0]
        child = post.comments[2]

        variants = service_module.QzoneService._thread_reply_payload_variants(
            post,
            child,
            parent,
            [{"comment_id": child.tid, "comment_uin": child.uin}],
        )

        self.assertEqual([item["name"] for item in variants], ["pc_addreply_ugc_parent"])
        self.assertEqual(variants[0]["comment_id"], "2_r_2_100000002")
        self.assertEqual(variants[0]["comment_uin"], 100000002)
        self.assertEqual(variants[0]["payload_comment_id"], "2")
        self.assertEqual(variants[0]["payload_t2_tid"], "2_r_2_100000002")
        self.assertEqual(variants[0]["topic_id"], "100000001_post-1")

    async def test_thread_reply_addreply_ugc_variant_allows_friend_post_bot_parent_short_id_one(self):
        service_module = _load_qzone_service()
        post = service_module.QzonePost(
            uin=100000002,
            tid="post-1",
            appid=311,
            comments=[
                service_module.QzoneComment(
                    uin=100000001,
                    nickname="Me",
                    tid="1",
                    submit_tid="1",
                    raw_tid="1",
                ),
                service_module.QzoneComment(
                    uin=100000002,
                    nickname="Friend",
                    tid="1_r_1_100000002",
                    submit_tid="1",
                    raw_tid="1",
                    parent_tid="1",
                    reply_to_tid="1",
                    raw_reply_to_tid="1",
                    reply_to_uin=100000001,
                    raw_reply_to_uin=100000001,
                ),
            ],
        )
        parent = post.comments[0]
        child = post.comments[1]

        variants = service_module.QzoneService._thread_reply_payload_variants(
            post,
            child,
            parent,
            [{"comment_id": child.tid, "comment_uin": child.uin}],
        )

        self.assertEqual([item["name"] for item in variants], ["pc_addreply_ugc_parent"])
        self.assertEqual(variants[0]["comment_id"], "1_r_1_100000002")
        self.assertEqual(variants[0]["comment_uin"], 100000002)
        self.assertEqual(variants[0]["payload_comment_id"], "1")
        self.assertEqual(variants[0]["payload_t2_tid"], "1_r_1_100000002")
        self.assertEqual(variants[0]["topic_id"], "100000002_post-1")

    async def test_friend_post_thread_reply_h5_re_feeds_uses_bot_parent_anchor(self):
        service_module = _load_qzone_service()

        class Service(_ConfirmedThreadVerificationMixin, service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.calls.append((url, dict(data or {})))
                return {"code": 0}

        service = Service()
        post = service_module.QzonePost(uin=100000003, tid="e9557f35fbc73c6af9a40000", appid=311)
        parent = service_module.QzoneComment(
            uin=100000001,
            nickname="Me",
            tid="1",
            submit_tid="1",
            raw_tid="1",
        )
        child = service_module.QzoneComment(
            uin=100000003,
            nickname="测试用户丙",
            tid="1_r_1_100000003",
            submit_tid="1",
            raw_tid="1",
            parent_tid="1",
            reply_to_tid="1",
            raw_reply_to_tid="1",
            reply_to_uin=100000001,
            raw_reply_to_uin=100000001,
        )
        service._post_cache[post.key] = post

        result = await service.reply_comment(post.key, child, "三级评论", parent_comment=parent)

        self.assertEqual(result["transport"], "h5_re_feeds_parent")
        self.assertEqual(len(service.calls), 1)
        self.assertEqual(service.calls[0][0], service.H5_COMMENT_URL)
        data = service.calls[0][1]
        self.assertEqual(data["topicId"], "100000003_e9557f35fbc73c6af9a40000__1")
        self.assertEqual(data["hostUin"], 100000003)
        self.assertEqual(data["uin"], 100000001)
        self.assertEqual(data["content"], "@{uin:100000003,nick:测试用户丙,auto:1} 三级评论")
        self.assertEqual(data["commentId"], "1")
        self.assertEqual(data["commentUin"], 100000001)
        self.assertEqual(data["paramstr"], "2")
        self.assertEqual(data["qzreferrer"], "https://user.qzone.qq.com/100000003")

    async def test_reply_comment_thread_reply_rejects_synthetic_short_id_variants(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.calls.append((url, dict(data or {})))
                if len(self.calls) < 3:
                    return {"code": -10049, "message": "该条内容已被删除"}
                return {"code": 0}

        service = Service()
        post = service_module.QzonePost(uin=100000001, tid="post-1", appid=311)
        parent = service_module.QzoneComment(uin=100000002, nickname="Friend", tid="4", submit_tid="4")
        child = service_module.QzoneComment(
            uin=100000002,
            nickname="Friend",
            tid="4_r_2_100000002",
            submit_tid="2",
            parent_tid="4",
            reply_to_tid="4_r_1_100000001",
            reply_to_uin=100000001,
        )
        service._post_cache[post.key] = post

        with self.assertRaises(RuntimeError) as ctx:
            await service.reply_comment(post.key, child, "reply", parent_comment=parent)

        self.assertEqual(service.calls, [])
        self.assertTrue(getattr(ctx.exception, "reply_verification_failed", False))
        self.assertEqual(getattr(ctx.exception, "verification_status"), "unsafe_synthetic_thread_target")

    async def test_reply_comment_thread_reply_submits_parent_anchor_only_with_addreply_ugc(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.calls.append((url, dict(data or {})))
                return {"code": -10049, "message": "该条内容已被删除"}

        service = Service()
        post = service_module.QzonePost(uin=100000001, tid="post-1", appid=311)
        parent = service_module.QzoneComment(uin=100000002, nickname="Friend", tid="4", submit_tid="4")
        child = service_module.QzoneComment(
            uin=100000002,
            nickname="Friend",
            tid="4_r_2_100000002",
            submit_tid="2",
            parent_tid="4",
            reply_to_tid="4_r_1_100000001",
            reply_to_uin=100000001,
        )
        post.comments = [
            parent,
            service_module.QzoneComment(
                uin=100000001,
                nickname="Me",
                tid="4_r_1_100000001",
                submit_tid="1",
                parent_tid="4",
                reply_to_tid="4",
                reply_to_uin=100000002,
            ),
            child,
        ]
        service._post_cache[post.key] = post

        with self.assertRaises(RuntimeError) as ctx:
            await service.reply_comment(post.key, child, "reply", parent_comment=parent)

        self.assertEqual(len(service.calls), 1)
        self.assertEqual(service.calls[0][0], service.ADD_REPLY_UGC_URL)
        data = service.calls[0][1]
        self.assertEqual(data["commentId"], "4")
        self.assertEqual(data["commentUin"], 100000002)
        self.assertEqual(data["topicId"], "100000001_post-1")
        self.assertNotIn("t1_tid", data)
        self.assertNotIn("t1_uin", data)
        self.assertNotIn("t2_tid", data)
        self.assertNotIn("t2_uin", data)
        self.assertNotIn("replyUin", data)
        self.assertNotIn("parentTid", data)
        self.assertNotIn("replyId", data)
        self.assertNotIn("replyTid", data)
        self.assertEqual(getattr(ctx.exception, "attempts")[0]["variant"], "pc_addreply_ugc_parent")
        self.assertEqual(getattr(ctx.exception, "attempts")[0]["transport"], "addreply_ugc")
        self.assertEqual(getattr(ctx.exception, "attempts")[0]["payload_comment_id"], "4")

    async def test_reply_comment_thread_reply_does_not_fallback_to_parent_comment(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.calls.append((url, dict(data or {})))
                return {"code": -1, "message": "该条内容已被删除"}

        service = Service()
        post = service_module.QzonePost(uin=10001, tid="post-1", appid=311)
        parent = service_module.QzoneComment(uin=20002, nickname="Friend", tid="11")
        child = service_module.QzoneComment(
            uin=20002,
            nickname="Friend",
            tid="11_r_1_20002",
            submit_tid="1",
            parent_tid="11",
            reply_to_tid="11_r_1_10001",
            reply_to_uin=10001,
        )
        service._post_cache[post.key] = post

        with self.assertRaises(RuntimeError) as ctx:
            await service.reply_comment(post.key, child, "third reply", parent_comment=parent)

        self.assertEqual(service.calls, [])
        self.assertTrue(getattr(ctx.exception, "reply_verification_failed", False))
        self.assertEqual(getattr(ctx.exception, "verification_status"), "unsafe_synthetic_thread_target")

    async def test_reply_comment_thread_reply_filters_parent_target_even_if_builder_regresses(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(types.SimpleNamespace())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(self, method, url, *, params=None, data=None, headers=None, retry=True, retry_parse_error=True):
                self.calls.append((url, dict(data or {})))
                return {"code": -10049, "message": "该条内容已被删除"}

            @staticmethod
            def _reply_submit_targets(post, comment, *, parent_comment=None):
                return [
                    {"comment_id": "11_r_2_20002", "comment_uin": 20002},
                    {"comment_id": "2", "comment_uin": 20002},
                    {"comment_id": "11", "comment_uin": 20002},
                ]

        service = Service()
        post = service_module.QzonePost(uin=10001, tid="post-1", appid=311)
        parent = service_module.QzoneComment(uin=20002, nickname="Friend", tid="11")
        child = service_module.QzoneComment(
            uin=20002,
            nickname="Friend",
            tid="11_r_2_20002",
            submit_tid="2",
            parent_tid="11",
            reply_to_tid="11_r_1_10001",
            reply_to_uin=10001,
        )
        service._post_cache[post.key] = post

        with self.assertRaises(RuntimeError) as ctx:
            await service.reply_comment(post.key, child, "third reply", parent_comment=parent)

        self.assertEqual(service.calls, [])
        self.assertEqual(
            getattr(ctx.exception, "attempted_targets"),
            [
                {"comment_id": "11_r_2_20002", "comment_uin": 20002},
            ],
        )
        self.assertEqual(getattr(ctx.exception, "attempts"), [])
        self.assertEqual(getattr(ctx.exception, "verification_status"), "unsafe_synthetic_thread_target")


class QzoneHostTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_retries_after_login_failure(self):
        host_module = _load_qzone_host()

        class Service:
            def __init__(self):
                self.publish_calls = 0
                self.invalidated = False

            async def context(self):
                return types.SimpleNamespace(nickname="测试用户乙", uin=100000001)

            async def publish_post(self, *, text="", images=None, videos=None):
                self.publish_calls += 1
                self.videos = list(videos or [])
                if self.publish_calls == 1:
                    raise RuntimeError("QQ 空间 Cookie 失效")
                return {"ok": True}

            def invalidate(self):
                self.invalidated = True

        class Plugin(host_module.PluginQzoneMixin):
            def __init__(self):
                self.qzone_service = Service()

        plugin = Plugin()
        result = await plugin._safe_publish_qzone(
            text="测试",
            images=[b"image"],
            videos=["https://example.com/video.mp4"],
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(plugin.qzone_service.publish_calls, 2)
        self.assertEqual(plugin.qzone_service.videos, ["https://example.com/video.mp4"])
        self.assertTrue(plugin.qzone_service.invalidated)


if __name__ == "__main__":
    unittest.main()



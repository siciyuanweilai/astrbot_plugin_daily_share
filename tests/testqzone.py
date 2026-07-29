import base64
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
MEDIA_UPLOAD_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.upload"
CONSTANTS_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.endpoints"
CLIENT_SERVICE_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.gateway"
COMMENT_SERVICE_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.discussion"
FEED_SERVICE_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.feed"
SERVICE_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.qzone"
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
    _install_stub_module(
        "astrbot", api=_install_stub_module("astrbot.api", logger=_Logger())
    )
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


class _ConfirmedThreadVerificationService:
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
    _load_qzone_parser()
    _load_qzone_relation()
    _load_qzone_entry()
    for module_name, filename in (
        (CONSTANTS_MODULE_NAME, "endpoints.py"),
        (CLIENT_SERVICE_MODULE_NAME, "gateway.py"),
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
        ROOT / "core" / "space" / "qzone.py",
    )
    service_module = importlib.util.module_from_spec(service_spec)
    sys.modules[SERVICE_MODULE_NAME] = service_module
    service_spec.loader.exec_module(service_module)
    return service_module


class _EmptyQzoneContextService:
    bot_map = {}

    def get_bot_instance(self, _adapter_id):
        return None

    def is_onebot_platform(self, _adapter_id):
        return False

    def get_onebot_bot(self, **_kwargs):
        return None

    async def call_onebot_action(self, _bot, _action, **_params):
        raise RuntimeError("测试环境没有 OneBot 客户端")


def _qzone_plugin(**values):
    defaults = {
        "qzone_conf": {},
        "_cached_qq_adapter_id": "",
        "ctx_service": _EmptyQzoneContextService(),
    }
    defaults.update(values)
    return types.SimpleNamespace(**defaults)


def _new_qzone_service(service_module, plugin=None):
    plugin = plugin or _qzone_plugin()
    defaults = _qzone_plugin()
    for name, value in vars(defaults).items():
        if not hasattr(plugin, name):
            setattr(plugin, name, value)
    return service_module.QzoneService(plugin)


def _load_qzone_host():
    _install_stub_module(
        "astrbot", api=_install_stub_module("astrbot.api", logger=_Logger())
    )
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
                            "remark": "测试备注",
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
        self.assertEqual(items[0]["remark"], "测试备注")
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

        result = parser.clean_qzone_text(
            "从美术馆的光影里退场，<br>一出门就被大太阳撞了个满怀。<br>赶紧躲进梧桐树荫底下，<br>翻出收藏夹里那家几百米外的咖啡店。 展开全文"
        )

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
        self.assertEqual(
            posts[0].avatar_url, "https://q.qlogo.cn/headimg_dl?dst_uin=12345&spec=100"
        )
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

    def test_feed_list_keeps_repost_content_from_msglist(self):
        posts = parse_feed_list(
            [
                {
                    "tid": "dca6590585f3486a15890700",
                    "uin": 100000101,
                    "name": "测试用户A",
                    "content": "哟哟哟，切克闹",
                    "created_time": 1783165829,
                    "rt_con": {
                        "conlist": [{"con": "测试转发正文", "type": 2}],
                        "content": "测试转发正文",
                    },
                    "rt_tid": "e9557f351df3486acba60c00",
                    "rt_uin": 100000202,
                    "rt_uinname": "测试用户B",
                    "rt_pic": [{"url1": "https://example.com/repost.jpg"}],
                }
            ]
        )

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].text, "哟哟哟，切克闹")
        self.assertEqual(posts[0].rt_con, "测试转发正文")
        self.assertEqual(posts[0].rt_uin, 100000202)
        self.assertEqual(posts[0].rt_uinname, "测试用户B")
        self.assertEqual(posts[0].rt_tid, "e9557f351df3486acba60c00")
        self.assertEqual(posts[0].rt_images, ["https://example.com/repost.jpg"])
        self.assertEqual(
            posts[0].to_payload()["repost"],
            {
                "uin": 100000202,
                "nickname": "测试用户B",
                "tid": "e9557f351df3486acba60c00",
                "content": "测试转发正文",
                "images": ["https://example.com/repost.jpg"],
            },
        )

    def test_feed_list_classifies_forwarded_top_level_pic_as_repost_image(self):
        posts = parse_feed_list(
            [
                {
                    "tid": "dca659050f10496a7b8b0500",
                    "uin": 100000101,
                    "name": "测试用户A",
                    "content": "这位小姐姐有点眼熟啊",
                    "created_time": 1783173135,
                    "pic": [
                        {
                            "url2": "https://example.com/noodle.jpg",
                            "curlikekey": "http://user.qzone.qq.com/100000101/mood/dca659050f10496a7b8b0500.1^||^https://example.com/noodle.jpg^||^0",
                            "unilikekey": "http://user.qzone.qq.com/100000202/mood/e9557f35de0f496ab1000900.1^||^https://example.com/noodle.jpg^||^0",
                        }
                    ],
                    "rt_con": {"content": "我喜欢这位小姐姐！"},
                    "rt_tid": "e9557f35de0f496ab1000900",
                    "rt_uin": 100000202,
                    "rt_uinname": "测试用户B",
                }
            ]
        )

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].images, [])
        self.assertEqual(posts[0].rt_images, ["https://example.com/noodle.jpg"])

    def test_recent_feed_keeps_structured_repost_content(self):
        payload = {
            "data": {
                "data": [
                    {
                        "appid": "311",
                        "fid": "repost-fid",
                        "uin": 100000101,
                        "nickname": "测试用户A",
                        "content": "哟哟哟，切克闹",
                        "rt_con": {"content": "测试转发正文"},
                        "rt_uin": 100000202,
                        "rt_uinname": "测试用户B",
                        "rt_tid": "source-fid",
                        "rtitem": {
                            "rt_wc_img": "6d7fd401e43d00fbd498a4d90b5397972c6389bea45dff2edc13a471fb90f29f",
                            "pic": [{"url2": "https://example.com/repost-card.jpg"}],
                        },
                    }
                ]
            }
        }

        posts = parse_recent_feed_list(payload)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].text, "哟哟哟，切克闹")
        self.assertEqual(posts[0].rt_con, "测试转发正文")
        self.assertEqual(posts[0].rt_uinname, "测试用户B")
        self.assertEqual(posts[0].rt_images, ["https://example.com/repost-card.jpg"])

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
        self.assertEqual(
            [comment.tid for comment in posts[0].comments], ["11", "11_r_1_2492835361"]
        )
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
                service_module.QzoneComment(
                    uin=20002, nickname="Alice", content="first", tid="c1"
                ),
                service_module.QzoneComment(
                    uin=30003,
                    nickname="Bob",
                    content="reply",
                    tid="r1",
                    parent_tid="c1",
                ),
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
        self.assertEqual(
            posts[0].videos, ["qzone://video/1075_0b53nrbk4cydeuaogbrsobvda3aevz6agbca"]
        )

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

        post = parse_feedinfo_html(
            markup,
            context_uin=100000001,
            context_tid="feedinfo-tid",
            context_time=1781752293,
        )

        self.assertIsNotNone(post)
        self.assertEqual(post.tid, "feedinfo-tid")
        self.assertEqual(post.appid, 311)
        self.assertEqual(post.text, "今天测试一下")
        self.assertEqual(post.videos, ["qzone://video/1075_0b53feedinfovid"])

    def test_self_feed_does_not_use_pic_list_as_avatar(self):
        posts = parse_feed_list(
            [
                {
                    "tid": "mood-1",
                    "uin": 12345,
                    "nickname": "测试用户乙",
                    "content": "今天也很好",
                    "pic": [{"url1": "https://example.com/content.jpg"}],
                    "created_time": 1718000000,
                }
            ]
        )

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].images, ["https://example.com/content.jpg"])
        self.assertEqual(
            posts[0].avatar_url, "https://q.qlogo.cn/headimg_dl?dst_uin=12345&spec=100"
        )

    def test_parse_comments_supports_commentid_and_reply_list(self):
        posts = parse_feed_list(
            [
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
            ]
        )

        comments = posts[0].comments
        self.assertEqual(
            [item.tid for item in comments], ["root-c1", "reply-r2", "reply-r3"]
        )
        self.assertEqual(comments[1].parent_tid, "root-c1")
        self.assertEqual(comments[1].reply_to_tid, "root-c1")
        self.assertEqual(comments[1].uin, 20002)
        self.assertEqual(comments[2].parent_tid, "root-c1")
        self.assertEqual(comments[2].reply_to_tid, "reply-r2")

    def test_parse_comments_reads_reply_target_from_html_params(self):
        posts = parse_feed_list(
            [
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
            ]
        )

        comment = posts[0].comments[1]
        self.assertEqual(comment.parent_tid, "root-c1")
        self.assertEqual(comment.reply_to_tid, "root-c1")
        self.assertEqual(comment.reply_to_uin, 20002)
        self.assertEqual(comment.raw_fields["commentId"], "reply-r2")
        self.assertEqual(comment.raw_fields["commentUin"], "o30003")
        self.assertEqual(comment.raw_fields["extracted_params"]["t2_tid"], "root-c1")
        self.assertEqual(comment.raw_fields["extracted_params"]["t2_uin"], "20002")

    def test_parse_comments_reads_reply_target_from_mention(self):
        posts = parse_feed_list(
            [
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
            ]
        )

        comment = posts[0].comments[1]
        self.assertEqual(comment.parent_tid, "root-c1")
        self.assertEqual(comment.reply_to_uin, 12345)
        self.assertEqual(comment.reply_to_nickname, "Me")

    def test_parse_comments_stabilizes_short_reply_ids(self):
        posts = parse_feed_list(
            [
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
            ]
        )

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
        posts = parse_feed_list(
            [
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
            ]
        )

        comments = posts[0].comments
        self.assertEqual(comments[1].tid, "11_r_1_12345")
        self.assertEqual(comments[1].reply_to_tid, "11")
        self.assertEqual(comments[2].tid, "11_r_1_20002")
        self.assertEqual(comments[2].reply_to_tid, "11_r_1_12345")

    def test_parse_comments_keeps_duplicate_short_ids_unique_for_same_user(self):
        posts = parse_feed_list(
            [
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
                                    "commentUin": "o20002",
                                    "nickname": "Friend",
                                    "commentContent": "one",
                                },
                                {
                                    "commentId": "1",
                                    "commentUin": "o20002",
                                    "nickname": "Friend",
                                    "commentContent": "two",
                                },
                            ],
                        }
                    ],
                }
            ]
        )

        self.assertEqual(
            [comment.tid for comment in posts[0].comments],
            ["11", "11_r_1_20002", "11_r_1_20002_n2"],
        )

    def test_parse_comments_prefers_commentid_as_submit_tid_when_tid_is_short_seq(self):
        posts = parse_feed_list(
            [
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
            ]
        )

        comments = posts[0].comments
        self.assertEqual(comments[0].tid, "11")
        self.assertEqual(comments[0].submit_tid, "root-real-11")
        self.assertEqual(comments[1].tid, "11_r_2_20002")
        self.assertEqual(comments[1].submit_tid, "reply-real-2")

    def test_parse_feed_item_supports_comment_list_alias(self):
        posts = parse_feed_list(
            [
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
            ]
        )

        self.assertEqual(len(posts[0].comments), 1)
        self.assertEqual(posts[0].comments[0].tid, "root-c1")
        self.assertEqual(posts[0].comments[0].content, "first")

    def test_parse_comments_reads_comment_images(self):
        image_url = (
            "http://photogzmaz.photo.store.qq.com/psc?/abc/b&bo=qAOoAwAAAAAWECA!"
        )
        posts = parse_feed_list(
            [
                {
                    "tid": "mood-1",
                    "uin": "o12345",
                    "content": "post text",
                    "commentlist": [
                        {
                            "tid": "1",
                            "uin": "o20002",
                            "nickname": "Alice",
                            "content": "测试评论带图片",
                            "pic": [
                                {
                                    "b_url": image_url,
                                    "hd_url": image_url,
                                    "o_url": image_url,
                                    "s_url": image_url,
                                }
                            ],
                            "rich_info": [{"burl": image_url, "type": 1}],
                        }
                    ],
                }
            ]
        )

        comment = posts[0].comments[0]
        self.assertEqual(comment.images, [image_url])
        self.assertEqual(
            posts[0].to_payload(include_comments=True)["comments"][0]["images"],
            [image_url],
        )


class QzoneServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_bot_prefers_configured_qzone_adapter(self):
        service_module = _load_qzone_service()
        first = object()
        selected = object()

        class CtxService:
            bot_map = {"V": first, "Swan": selected}

            def get_bot_instance(self, adapter_id):
                return self.bot_map.get(adapter_id)

            def is_onebot_platform(self, _key):
                return False

            def get_onebot_bot(self, *args, **kwargs):
                return None

        plugin = types.SimpleNamespace(
            _cached_qq_adapter_id="V",
            qzone_conf={"qzone_adapter_id": "Swan"},
            ctx_service=CtxService(),
        )
        service = _new_qzone_service(service_module, plugin)

        self.assertIs(service._get_bot(), selected)

    async def test_get_bot_rejects_ambiguous_instances_when_adapter_empty(self):
        service_module = _load_qzone_service()
        first = object()
        second = object()

        class CtxService:
            bot_map = {"V": first, "Swan": second}

            def get_bot_instance(self, adapter_id):
                if adapter_id:
                    return self.bot_map.get(adapter_id)
                return next(iter(self.bot_map.values()))

            def is_onebot_platform(self, _key):
                return True

            def get_onebot_bot(self, *args, **kwargs):
                return None

        plugin = types.SimpleNamespace(
            _cached_qq_adapter_id="",
            qzone_conf={"qzone_adapter_id": ""},
            ctx_service=CtxService(),
        )
        service = _new_qzone_service(service_module, plugin)

        self.assertIsNone(service._get_bot())

    async def test_get_bot_reads_live_adapter_cache_after_service_construction(self):
        service_module = _load_qzone_service()
        first = object()
        selected = object()

        class CtxService:
            bot_map = {"V": first, "Swan": selected}

            def get_bot_instance(self, adapter_id):
                return self.bot_map.get(adapter_id)

            def is_onebot_platform(self, _key):
                return True

            def get_onebot_bot(self, *args, **kwargs):
                return None

        plugin = types.SimpleNamespace(
            _cached_qq_adapter_id="",
            qzone_conf={"qzone_adapter_id": ""},
            ctx_service=CtxService(),
        )
        service = _new_qzone_service(service_module, plugin)
        plugin._cached_qq_adapter_id = "Swan"

        self.assertIs(service._get_bot(), selected)

    async def test_query_recent_posts_uses_feeds3_basic_params(self):
        service_module = _load_qzone_service()

        class Service(_ConfirmedThreadVerificationService, service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin(qzone_conf={}))
                self.call = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
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
        self.assertIn(
            "XMLHttpRequest", service.call["headers"].get("X-Requested-With", "")
        )
        self.assertEqual(service.last_friend_feeds_meta["source"], "recent_posts")
        self.assertEqual(service.last_friend_feeds_meta["count"], 1)
        self.assertEqual(service.last_friend_feeds_meta["parsed_count"], 1)
        self.assertTrue(service.last_friend_feeds_meta["has_more"])
        self.assertEqual(
            service.last_friend_feeds_meta["next_cursor"],
            "pagenum=2&basetime=1773990000",
        )

    async def test_query_posts_reuses_short_ttl_cache(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin(qzone_conf={}))
                self.calls = 0

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
                self.calls += 1
                return {
                    "code": 0,
                    "msglist": [
                        {
                            "tid": "mood-1",
                            "uin": 100000001,
                            "content": "今天很开心",
                        }
                    ],
                }

        service = Service()
        first = await service.query_posts(target_id="100000001", num=5)
        second = await service.query_posts(target_id="100000001", num=5)

        self.assertEqual(service.calls, 1)
        self.assertEqual(first[0].key, "100000001:mood-1")
        self.assertEqual(second[0].key, first[0].key)

    async def test_query_posts_with_detail_reuses_detail_cache(self):
        service_module = _load_qzone_service()

        class Service(_ConfirmedThreadVerificationService, service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin(qzone_conf={}))
                self.detail_calls = 0

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
                if url == self.LIST_URL:
                    return {
                        "code": 0,
                        "msglist": [
                            {
                                "tid": "mood-1",
                                "uin": 100000001,
                                "content": "今天很开心",
                            }
                        ],
                    }
                self.detail_calls += 1
                return {
                    "code": 0,
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

        service = Service()
        posts = await service.query_posts(target_id="100000001", with_detail=True)
        detail = await service.detail(posts[0].key)

        self.assertEqual(service.detail_calls, 1)
        self.assertEqual(detail.key, "100000001:mood-1")
        self.assertEqual([comment.tid for comment in detail.comments], ["c1"])

    async def test_query_mention_posts_uses_about_me_notification_feed(self):
        service_module = _load_qzone_service()
        bot_uin = 10001
        friend_uin = 20002

        class Service(_ConfirmedThreadVerificationService, service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin(qzone_conf={}))
                self.call = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=bot_uin,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="BOT_NICK",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
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

        class Service(_ConfirmedThreadVerificationService, service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin(qzone_conf={}))
                self.call = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
                self.call = {"method": method, "url": url, "params": dict(params or {})}
                return {
                    "code": 0,
                    "data": {
                        "items_list": [{"uin": "10001", "name": "好友", "score": "9"}]
                    },
                }

        service = Service()
        result = await service.query_relations(relation_type="care_by")

        self.assertEqual(result["type"], "care_by")
        self.assertEqual(result["items"][0]["uin"], 10001)
        self.assertEqual(service.call["url"], service.RELATION_URL)
        self.assertEqual(service.call["params"]["uin"], 100000001)
        self.assertEqual(service.call["params"]["do"], 2)
        self.assertEqual(service.call["params"]["g_tk"], "337168208")

    async def test_query_posts_with_detail_keeps_list_comments_when_detail_has_none(
        self,
    ):
        service_module = _load_qzone_service()

        class Service(_ConfirmedThreadVerificationService, service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin(qzone_conf={}))

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
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

        class Service(_ConfirmedThreadVerificationService, service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin(qzone_conf={}))

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
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

        self.assertEqual(
            [comment.tid for comment in posts[0].comments], ["c1", "r1", "r2"]
        )
        self.assertEqual(posts[0].comments[1].parent_tid, "c1")
        self.assertEqual(posts[0].comments[2].parent_tid, "c1")

    async def test_query_posts_with_detail_keeps_stable_tid_and_recovers_real_submit_tid(
        self,
    ):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin(qzone_conf={}))

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="测试用户乙",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
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

        self.assertEqual(
            [comment.tid for comment in posts[0].comments], ["11", "11_r_2_10001"]
        )
        self.assertEqual(posts[0].comments[0].submit_tid, "root-real-11")
        self.assertEqual(posts[0].comments[1].submit_tid, "reply-real-2")

    async def test_base64_image_decodes_before_path_check(self):
        service_module = _load_qzone_service()
        service = _new_qzone_service(service_module, types.SimpleNamespace())
        data = b"daily-share-image"

        result = await service._image_bytes(
            f"base64://{base64.b64encode(data).decode('ascii')}"
        )

        self.assertEqual(result, data)

    async def test_base64_image_decode_runs_in_worker_thread(self):
        service_module = _load_qzone_service()
        service = _new_qzone_service(
            service_module, types.SimpleNamespace(qzone_conf={})
        )
        calls = []

        async def fake_to_thread(func, *args):
            calls.append(func)
            return func(*args)

        encoded = base64.b64encode(b"image-data").decode("ascii")
        with patch.object(service_module.asyncio, "to_thread", fake_to_thread):
            result = await service._image_bytes(f"base64://{encoded}")

        self.assertEqual(result, b"image-data")
        self.assertEqual(calls, [base64.b64decode])

    async def test_qzone_upload_base64_encode_runs_in_worker_thread(self):
        service_module = _load_qzone_service()
        service = _new_qzone_service(
            service_module, types.SimpleNamespace(qzone_conf={})
        )
        calls = []

        async def fake_to_thread(func, *args):
            calls.append(func)
            return func(*args)

        async def context():
            return types.SimpleNamespace(skey="s", uin=1, p_skey="p")

        async def image_bytes(image):
            return b"image-data"

        async def request(*args, **kwargs):
            return {"ret": 0}

        service.context = context
        service._image_bytes = image_bytes
        service._request = request
        with (
            patch.object(service_module.asyncio, "to_thread", fake_to_thread),
            patch.object(
                service_module, "parse_upload_result", return_value=("bo", "rv")
            ),
        ):
            result = await service._upload_image(b"image-data")

        self.assertEqual(result, ("bo", "rv"))
        self.assertEqual([call.__name__ for call in calls], ["_base64_ascii"])

    async def test_image_bytes_rejects_oversized_base64_and_raw_bytes(self):
        service_module = _load_qzone_service()
        service = _new_qzone_service(service_module, types.SimpleNamespace())
        service._REMOTE_IMAGE_MAX_BYTES = 4

        with self.assertRaisesRegex(RuntimeError, "图片过大"):
            await service._image_bytes(b"12345")

        encoded = base64.b64encode(b"12345").decode("ascii")
        with self.assertRaisesRegex(RuntimeError, "图片过大"):
            await service._image_bytes(f"base64://{encoded}")

    async def test_remote_image_bytes_streams_response_chunks(self):
        service_module = _load_qzone_service()
        service = _new_qzone_service(service_module, types.SimpleNamespace())

        class FakeContent:
            async def iter_chunked(self, _size):
                yield b"daily-"
                yield b"share"

        class FakeResponse:
            status = 200
            content_length = 11
            content = FakeContent()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

        class FakeSession:
            def get(self, _url):
                return FakeResponse()

        async def fake_http():
            return FakeSession()

        service._http = fake_http

        result = await service._image_bytes("https://example.com/image.jpg")

        self.assertEqual(result, b"daily-share")

    async def test_remote_image_bytes_rejects_oversized_response(self):
        service_module = _load_qzone_service()
        service = _new_qzone_service(service_module, types.SimpleNamespace())

        class FakeContent:
            async def iter_chunked(self, _size):
                yield b""

        class FakeResponse:
            status = 200
            content_length = service._REMOTE_IMAGE_MAX_BYTES + 1
            content = FakeContent()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

        class FakeSession:
            def get(self, _url):
                return FakeResponse()

        async def fake_http():
            return FakeSession()

        service._http = fake_http

        with self.assertRaisesRegex(RuntimeError, "图片过大"):
            await service._image_bytes("https://example.com/image.jpg")

    async def test_api_timeout_reads_qzone_config_and_clamps(self):
        service_module = _load_qzone_service()
        plugin = types.SimpleNamespace(qzone_conf={"qzone_api_timeout_seconds": "180"})
        service = _new_qzone_service(service_module, plugin)

        self.assertEqual(service._api_timeout_seconds(), 180)

        plugin.qzone_conf["qzone_api_timeout_seconds"] = 999
        self.assertEqual(service._api_timeout_seconds(), 300)

        plugin.qzone_conf["qzone_api_timeout_seconds"] = "bad"
        self.assertEqual(service._api_timeout_seconds(), 120)

    async def test_http_rebuilds_session_when_timeout_changes(self):
        service_module = _load_qzone_service()
        client_module = sys.modules[CLIENT_SERVICE_MODULE_NAME]
        plugin = types.SimpleNamespace(qzone_conf={"qzone_api_timeout_seconds": 120})
        service = _new_qzone_service(service_module, plugin)

        class FakeTimeout:
            def __init__(self, *, total):
                self.total = total

        class FakeSession:
            def __init__(self, *, timeout):
                self.timeout = timeout
                self.closed = False

            async def close(self):
                self.closed = True

        fake_aiohttp = types.SimpleNamespace(
            ClientSession=FakeSession, ClientTimeout=FakeTimeout
        )

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
        service = _new_qzone_service(service_module, types.SimpleNamespace())
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
        service = _new_qzone_service(service_module, types.SimpleNamespace())
        ctx = service_module.QzoneContext(
            uin=100000001,
            skey="skey",
            p_skey="p_skey",
            nickname="测试用户乙",
        )

        headers = service._comment_h5_headers(
            ctx, referer="https://h5.qzone.qq.com/100000001/mood/post-1"
        )

        self.assertEqual(headers["Origin"], service.H5_ORIGIN)
        self.assertEqual(
            headers["Referer"], "https://h5.qzone.qq.com/100000001/mood/post-1"
        )
        self.assertEqual(headers["X-Requested-With"], "XMLHttpRequest")
        self.assertEqual(headers["Sec-Fetch-Mode"], "cors")

    async def test_h5_post_json_prefers_http2_and_sends_full_cookie_context(self):
        service_module = _load_qzone_service()
        client_module = sys.modules[CLIENT_SERVICE_MODULE_NAME]
        plugin = types.SimpleNamespace(qzone_conf={"qzone_api_timeout_seconds": 120})
        service = _new_qzone_service(service_module, plugin)
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
                self.calls.append(
                    {
                        "url": url,
                        "params": params,
                        "content": content,
                        "headers": headers,
                    }
                )
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
                patch.object(
                    client_module.importlib.util,
                    "find_spec",
                    lambda name: object() if name == "h2" else None,
                ),
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
            get_bot_instance=lambda adapter_id: bot,
            bot_map={},
            is_onebot_platform=lambda key: False,
            get_onebot_bot=lambda target_umo, adapter_id: bot,
            call_onebot_action=lambda client, action, **params: (
                client.get_cookies(**params)
                if action == "get_cookies"
                else client.get_login_info()
            ),
        )
        plugin = types.SimpleNamespace(
            _cached_qq_adapter_id="", qzone_conf={}, ctx_service=ctx_service
        )
        service = _new_qzone_service(service_module, plugin)

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

        service = _new_qzone_service(service_module, types.SimpleNamespace())
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
        service = _new_qzone_service(service_module, plugin)
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
                self.calls.append(
                    {
                        "url": url,
                        "params": params,
                        "content": content,
                        "headers": headers,
                    }
                )
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
                patch.object(
                    client_module.importlib.util,
                    "find_spec",
                    lambda name: object() if name == "h2" else None,
                ),
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
        service = _new_qzone_service(service_module, plugin)
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
                self.calls.append(
                    {
                        "url": url,
                        "params": params,
                        "content": content,
                        "headers": headers,
                    }
                )
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
                patch.object(
                    client_module.importlib.util,
                    "find_spec",
                    lambda name: object() if name == "h2" else None,
                ),
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
        service = _new_qzone_service(service_module, plugin)
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
                self.calls.append(
                    {
                        "url": url,
                        "params": params,
                        "content": content,
                        "headers": headers,
                    }
                )
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
                patch.object(
                    client_module.importlib.util,
                    "find_spec",
                    lambda name: object() if name == "h2" else None,
                ),
                patch.object(service_module.asyncio, "sleep", no_sleep),
            ):
                result = await service._h5_post_bytes(
                    ctx,
                    "https://h5.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_re_feeds",
                    b"payload-bytes",
                    "application/octet-stream",
                    label="h5-body",
                )

            self.assertEqual(result["ret"], 0)
            self.assertEqual(result["_transport"], "HTTP/1.1")
            self.assertEqual(len(service._h2_session.calls), 1)
            self.assertEqual(len(service._session.calls), 1)
            self.assertEqual(service._session.calls[0]["data"], b"payload-bytes")
            self.assertEqual(
                service._session.calls[0]["headers"]["Content-Type"],
                "application/octet-stream",
            )
        finally:
            await service.close()

    async def test_h5_post_json_native_h2_gateway_timeout_retries_http11(self):
        service_module = _load_qzone_service()
        plugin = types.SimpleNamespace(qzone_conf={"qzone_api_timeout_seconds": 120})
        service = _new_qzone_service(service_module, plugin)
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
        service = _new_qzone_service(service_module, types.SimpleNamespace())

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
                super().__init__(_qzone_plugin())
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

            async def _request(
                self, method, url, *, params=None, data=None, headers=None, retry=True
            ):
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

    async def test_reply_comment_rejects_synthetic_short_own_thread_reply_before_submit(
        self,
    ):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin())
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

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
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
            await service.reply_comment(
                post.key, child, "thread reply", parent_comment=parent
            )

        self.assertIsNone(service.request_data)
        self.assertTrue(getattr(ctx.exception, "reply_verification_failed", False))
        self.assertEqual(
            getattr(ctx.exception, "verification_status"),
            "unsafe_synthetic_thread_target",
        )

    async def test_reply_comment_rejects_synthetic_reused_short_id_before_submit(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin())
                self.request_url = None
                self.request_data = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
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
            await service.reply_comment(
                post.key, child, "third reply", parent_comment=parent
            )

        self.assertIsNone(service.request_data)
        self.assertTrue(getattr(ctx.exception, "reply_verification_failed", False))
        self.assertEqual(
            getattr(ctx.exception, "verification_status"),
            "unsafe_synthetic_thread_target",
        )

    async def test_reply_comment_uses_h5_re_feeds_for_friend_post_self_parent(self):
        service_module = _load_qzone_service()

        class Service(_ConfirmedThreadVerificationService, service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin())
                self.request_url = None
                self.request_data = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
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

        await service.reply_comment(
            post.key, child, "thread reply", parent_comment=parent
        )

        self.assertEqual(service.request_url, service.H5_COMMENT_URL)
        self.assertEqual(service.request_data["topicId"], "30003_post-1__1")
        self.assertEqual(service.request_data["hostUin"], 30003)
        self.assertEqual(service.request_data["uin"], 10001)
        self.assertEqual(service.request_data["commentId"], "root-c1")
        self.assertEqual(service.request_data["commentUin"], 10001)
        self.assertEqual(
            service.request_data["content"],
            "@{uin:30003,nick:Alice,auto:1} thread reply",
        )
        self.assertEqual(service.request_data["format"], "fs")
        self.assertEqual(service.request_data["paramstr"], "2")
        self.assertEqual(
            service.request_data["qzreferrer"], "https://user.qzone.qq.com/30003"
        )
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
                super().__init__(_qzone_plugin())
                self.request_data = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
                self.request_data = dict(data or {})
                return {"code": 0}

        service = Service()
        post = service_module.QzonePost(uin=10001, tid="post-1", appid=311)
        comment = service_module.QzoneComment(
            uin=20002, nickname="Alice", tid="root-c1"
        )
        service._post_cache[post.key] = post

        await service.reply_comment(
            post.key, comment, "@{uin:20002,nick:Alice,auto:1} already mentioned"
        )

        self.assertEqual(
            service.request_data["content"],
            "@{uin:20002,nick:Alice,auto:1} already mentioned",
        )

    async def test_reply_comment_ignores_post_tid_parent_for_top_level_comment(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin())
                self.request_data = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
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
                super().__init__(_qzone_plugin())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
                self.calls.append((url, dict(data or {}), dict(headers or {})))
                return {"code": 0}

        service = Service()
        post = service_module.QzonePost(
            uin=20002, tid="post-1", appid=311, busi_param={"from": "feeds"}
        )
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

    def test_write_response_without_json_success_requires_blank_body(self):
        service_module = _load_qzone_service()

        self.assertTrue(
            service_module.QzoneService._write_response_without_json_ok(
                {
                    "_http_status": 200,
                    "_raw_blank": True,
                    "message": "QQ 空间返回为空",
                }
            )
        )
        self.assertFalse(
            service_module.QzoneService._write_response_without_json_ok(
                {
                    "_http_status": 200,
                    "_raw_blank": False,
                    "message": "QQ 空间返回为空",
                }
            )
        )
        self.assertFalse(
            service_module.QzoneService._write_response_without_json_ok(
                {
                    "_http_status": 200,
                    "_raw_blank": False,
                    "message": "QQ 空间返回内容不是结构化数据",
                }
            )
        )

    async def test_reply_comment_thread_reply_uses_only_addreply_ugc_for_own_post(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
                self.calls.append((url, dict(data or {})))
                return (
                    {"code": -10000, "message": "使用人数过多，请稍后再试"}
                    if len(self.calls) == 1
                    else {"code": 0}
                )

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
            await service.reply_comment(
                post.key, child, "thread reply", parent_comment=parent
            )

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

    async def test_reply_comment_thread_reply_uses_h5_re_feeds_for_friend_post_self_parent(
        self,
    ):
        service_module = _load_qzone_service()

        class Service(_ConfirmedThreadVerificationService, service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
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

        result = await service.reply_comment(
            post.key, child, "thread reply", parent_comment=parent
        )

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

    async def test_reply_comment_rejects_synthetic_sns_stable_reply_id_for_reused_short_id(
        self,
    ):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
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
            await service.reply_comment(
                post.key, child, "third reply", parent_comment=parent
            )

        self.assertEqual(service.calls, [])
        self.assertTrue(getattr(ctx.exception, "reply_verification_failed", False))
        self.assertEqual(
            getattr(ctx.exception, "verification_status"),
            "unsafe_synthetic_thread_target",
        )

    async def test_reply_comment_rejects_synthetic_second_friend_follow_up_before_submit(
        self,
    ):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin())
                self.calls = []
                self.detail_post = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
                self.calls.append((url, dict(data or {})))
                return {"code": 0}

            async def detail(self, post_id):
                return self.detail_post

        service = Service()
        post = service_module.QzonePost(uin=100000001, tid="post-1", appid=311)
        parent = service_module.QzoneComment(
            uin=100000002, nickname="Friend", tid="4", submit_tid="4"
        )
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
        self.assertEqual(
            getattr(ctx.exception, "verification_status"),
            "unsafe_synthetic_thread_target",
        )
        self.assertEqual(
            getattr(ctx.exception, "attempted_targets"),
            [{"comment_id": "4_r_2_100000002", "comment_uin": 100000002}],
        )

    async def test_reply_comment_avoids_short_id_when_parent_and_child_submit_id_collide(
        self,
    ):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin())
                self.calls = []
                self.detail_post = None

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
                self.calls.append((url, dict(data or {})))
                return {"code": 0}

            async def detail(self, post_id):
                return self.detail_post

        service = Service()
        post = service_module.QzonePost(uin=100000001, tid="post-1", appid=311)
        parent = service_module.QzoneComment(
            uin=100000002, nickname="Friend", tid="2", submit_tid="2"
        )
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

    async def test_verify_thread_reply_accepts_stable_target_even_when_raw_short_id_matches_parent(
        self,
    ):
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

    async def test_reply_comment_rejects_unsafe_thread_reply_without_fallback(
        self,
    ):
        service_module = _load_qzone_service()

        class Service(_ConfirmedThreadVerificationService, service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
                self.calls.append((url, dict(data or {})))
                return (
                    {"code": -10049, "message": "该条内容已被删除"}
                    if len(self.calls) == 1
                    else {"code": 0}
                )

        service = Service()
        post = service_module.QzonePost(uin=100000001, tid="post-1", appid=311)
        parent = service_module.QzoneComment(
            uin=100000002, nickname="Friend", tid="4", submit_tid="4"
        )
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
        self.assertEqual(
            getattr(ctx.exception, "verification_status"),
            "unsafe_synthetic_thread_target",
        )

    async def test_reply_comment_accepts_parent_floor_anchor_when_reply_uin_targets_child(
        self,
    ):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
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

        result = await service.reply_comment(
            post.key, child, "reply", parent_comment=parent
        )

        self.assertEqual(result["verification_status"], "confirmed")
        self.assertEqual(result["verified_reply_tid"], "4_r_3_100000001")
        self.assertEqual(result["verified_reply_to_tid"], "4")
        self.assertEqual(result["verified_reply_to_uin"], 100000002)
        self.assertEqual(service.calls[0][0], service.ADD_REPLY_UGC_URL)
        self.assertEqual(service.calls[0][1]["topicId"], "100000001_post-1")
        self.assertEqual(service.calls[0][1]["commentId"], "4")
        self.assertEqual(service.calls[0][1]["commentUin"], 100000002)
        self.assertEqual(
            service.calls[0][1]["content"], "@{uin:100000002,nick:Friend,auto:1} reply"
        )
        self.assertEqual(service.calls[0][1]["format"], "fs")
        self.assertEqual(service.calls[0][1]["code_version"], 1)
        self.assertEqual(service.calls[0][1]["with_fwd"], 0)
        self.assertIn("mood_v6/html/index.html", service.calls[0][1]["qzreferrer"])

    async def test_verify_thread_reply_rejects_parent_anchor_without_target_uin(self):
        service_module = _load_qzone_service()
        post = service_module.QzonePost(
            uin=100000001,
            tid="post-1",
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
                    reply_to_uin=0,
                    content="@{uin:100000002,nick:Friend,auto:1} reply",
                    create_time=2000000000,
                ),
            ],
        )
        parent = post.comments[0]
        target = post.comments[1]

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

        self.assertEqual(result["status"], "parent_target")

    async def test_thread_reply_addreply_ugc_variant_uses_parent_anchor(self):
        service_module = _load_qzone_service()
        post = service_module.QzonePost(
            uin=100000001,
            tid="post-1",
            appid=311,
            comments=[
                service_module.QzoneComment(
                    uin=100000002, nickname="Friend", tid="4", submit_tid="4"
                ),
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

        self.assertEqual(
            [item["name"] for item in variants], ["pc_addreply_ugc_parent"]
        )
        self.assertEqual(variants[0]["comment_id"], "4_r_2_100000002")
        self.assertEqual(variants[0]["comment_uin"], 100000002)
        self.assertEqual(variants[0]["payload_comment_id"], "4")
        self.assertEqual(variants[0]["payload_t2_tid"], "4_r_2_100000002")
        self.assertEqual(variants[0]["topic_id"], "100000001_post-1")

    async def test_thread_reply_addreply_ugc_variant_allows_colliding_parent_and_child_ids(
        self,
    ):
        service_module = _load_qzone_service()
        post = service_module.QzonePost(
            uin=100000001,
            tid="post-1",
            appid=311,
            comments=[
                service_module.QzoneComment(
                    uin=100000002, nickname="Friend", tid="2", submit_tid="2"
                ),
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

        self.assertEqual(
            [item["name"] for item in variants], ["pc_addreply_ugc_parent"]
        )
        self.assertEqual(variants[0]["comment_id"], "2_r_2_100000002")
        self.assertEqual(variants[0]["comment_uin"], 100000002)
        self.assertEqual(variants[0]["payload_comment_id"], "2")
        self.assertEqual(variants[0]["payload_t2_tid"], "2_r_2_100000002")
        self.assertEqual(variants[0]["topic_id"], "100000001_post-1")

    async def test_thread_reply_addreply_ugc_variant_allows_friend_post_bot_parent_short_id_one(
        self,
    ):
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

        self.assertEqual(
            [item["name"] for item in variants], ["pc_addreply_ugc_parent"]
        )
        self.assertEqual(variants[0]["comment_id"], "1_r_1_100000002")
        self.assertEqual(variants[0]["comment_uin"], 100000002)
        self.assertEqual(variants[0]["payload_comment_id"], "1")
        self.assertEqual(variants[0]["payload_t2_tid"], "1_r_1_100000002")
        self.assertEqual(variants[0]["topic_id"], "100000002_post-1")

    async def test_friend_post_thread_reply_h5_re_feeds_uses_bot_parent_anchor(self):
        service_module = _load_qzone_service()

        class Service(_ConfirmedThreadVerificationService, service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
                self.calls.append((url, dict(data or {})))
                return {"code": 0}

        service = Service()
        post = service_module.QzonePost(
            uin=100000003, tid="e9557f35fbc73c6af9a40000", appid=311
        )
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

        result = await service.reply_comment(
            post.key, child, "三级评论", parent_comment=parent
        )

        self.assertEqual(result["transport"], "h5_re_feeds_parent")
        self.assertEqual(len(service.calls), 1)
        self.assertEqual(service.calls[0][0], service.H5_COMMENT_URL)
        data = service.calls[0][1]
        self.assertEqual(data["topicId"], "100000003_e9557f35fbc73c6af9a40000__1")
        self.assertEqual(data["hostUin"], 100000003)
        self.assertEqual(data["uin"], 100000001)
        self.assertEqual(
            data["content"], "@{uin:100000003,nick:测试用户丙,auto:1} 三级评论"
        )
        self.assertEqual(data["commentId"], "1")
        self.assertEqual(data["commentUin"], 100000001)
        self.assertEqual(data["paramstr"], "2")
        self.assertEqual(data["qzreferrer"], "https://user.qzone.qq.com/100000003")

    async def test_reply_comment_thread_reply_rejects_synthetic_short_id_variants(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
                self.calls.append((url, dict(data or {})))
                if len(self.calls) < 3:
                    return {"code": -10049, "message": "该条内容已被删除"}
                return {"code": 0}

        service = Service()
        post = service_module.QzonePost(uin=100000001, tid="post-1", appid=311)
        parent = service_module.QzoneComment(
            uin=100000002, nickname="Friend", tid="4", submit_tid="4"
        )
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
        self.assertEqual(
            getattr(ctx.exception, "verification_status"),
            "unsafe_synthetic_thread_target",
        )

    async def test_reply_comment_thread_reply_submits_parent_anchor_only_with_addreply_ugc(
        self,
    ):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=100000001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
                self.calls.append((url, dict(data or {})))
                return {"code": -10049, "message": "该条内容已被删除"}

        service = Service()
        post = service_module.QzonePost(uin=100000001, tid="post-1", appid=311)
        parent = service_module.QzoneComment(
            uin=100000002, nickname="Friend", tid="4", submit_tid="4"
        )
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
        self.assertEqual(
            getattr(ctx.exception, "attempts")[0]["variant"], "pc_addreply_ugc_parent"
        )
        self.assertEqual(
            getattr(ctx.exception, "attempts")[0]["transport"], "addreply_ugc"
        )
        self.assertEqual(
            getattr(ctx.exception, "attempts")[0]["payload_comment_id"], "4"
        )

    async def test_reply_comment_thread_reply_does_not_fallback_to_parent_comment(self):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
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
            await service.reply_comment(
                post.key, child, "third reply", parent_comment=parent
            )

        self.assertEqual(service.calls, [])
        self.assertTrue(getattr(ctx.exception, "reply_verification_failed", False))
        self.assertEqual(
            getattr(ctx.exception, "verification_status"),
            "unsafe_synthetic_thread_target",
        )

    async def test_reply_comment_thread_reply_filters_parent_target_even_if_builder_regresses(
        self,
    ):
        service_module = _load_qzone_service()

        class Service(service_module.QzoneService):
            def __init__(self):
                super().__init__(_qzone_plugin())
                self.calls = []

            async def context(self):
                return service_module.QzoneContext(
                    uin=10001,
                    skey="skey",
                    p_skey="p_skey",
                    nickname="Me",
                )

            async def _request(
                self,
                method,
                url,
                *,
                params=None,
                data=None,
                headers=None,
                retry=True,
                retry_parse_error=True,
            ):
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
            await service.reply_comment(
                post.key, child, "third reply", parent_comment=parent
            )

        self.assertEqual(service.calls, [])
        self.assertEqual(
            getattr(ctx.exception, "attempted_targets"),
            [
                {"comment_id": "11_r_2_20002", "comment_uin": 20002},
            ],
        )
        self.assertEqual(getattr(ctx.exception, "attempts"), [])
        self.assertEqual(
            getattr(ctx.exception, "verification_status"),
            "unsafe_synthetic_thread_target",
        )


class QzoneHostTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_retries_after_login_failure(self):
        host_module = _load_qzone_host()

        class Service:
            def __init__(self):
                self.publish_calls = 0
                self.invalidated = False

            async def context(self):
                return types.SimpleNamespace(nickname="测试用户乙", uin=100000001)

            async def publish_post(self, *, text="", images=None):
                self.publish_calls += 1
                self.images = list(images or [])
                if self.publish_calls == 1:
                    raise RuntimeError("QQ 空间 Cookie 失效")
                return {"ok": True}

            def invalidate(self):
                self.invalidated = True

        class Plugin(host_module.PluginQzoneService):
            pass

        plugin = Plugin(types.SimpleNamespace(qzone_service=Service()))
        result = await plugin.publish_qzone(
            text="测试",
            images=[b"image"],
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(plugin.qzone_service.publish_calls, 2)
        self.assertEqual(plugin.qzone_service.images, [b"image"])
        self.assertTrue(plugin.qzone_service.invalidated)


if __name__ == "__main__":
    unittest.main()

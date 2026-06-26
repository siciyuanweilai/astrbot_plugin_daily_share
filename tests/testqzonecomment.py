import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "daily_share_auto_comment_testpkg"
CORE_PACKAGE_NAME = f"{PACKAGE_NAME}.core"
SPACE_PACKAGE_NAME = f"{CORE_PACKAGE_NAME}.space"
TASKS_PACKAGE_NAME = f"{CORE_PACKAGE_NAME}.tasks"
PROMPT_MODULE_NAME = f"{CORE_PACKAGE_NAME}.prompt"
MODELS_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.models"
COMMENT_MODULE_NAME = f"{TASKS_PACKAGE_NAME}.comment"
SERVICE_MODULE_NAME = f"{SPACE_PACKAGE_NAME}.service"


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


def _load_auto_comment_module():
    _install_stub_module("astrbot", api=_install_stub_module("astrbot.api", logger=_Logger()))
    for name in [PACKAGE_NAME, CORE_PACKAGE_NAME, SPACE_PACKAGE_NAME, TASKS_PACKAGE_NAME]:
        module = _install_stub_module(name)
        if name == CORE_PACKAGE_NAME:
            module.__path__ = [str(ROOT / "core")]
        elif name == SPACE_PACKAGE_NAME:
            module.__path__ = [str(ROOT / "core" / "space")]
        elif name == TASKS_PACKAGE_NAME:
            module.__path__ = [str(ROOT / "core" / "tasks")]
        else:
            module.__path__ = [str(ROOT)]

    prompt_spec = importlib.util.spec_from_file_location(
        PROMPT_MODULE_NAME,
        ROOT / "core" / "prompt.py",
    )
    prompt_module = importlib.util.module_from_spec(prompt_spec)
    sys.modules[prompt_spec.name] = prompt_module
    prompt_spec.loader.exec_module(prompt_module)

    models_spec = importlib.util.spec_from_file_location(
        MODELS_MODULE_NAME,
        ROOT / "core" / "space" / "models.py",
    )
    models_module = importlib.util.module_from_spec(models_spec)
    sys.modules[models_spec.name] = models_module
    models_spec.loader.exec_module(models_module)

    comment_spec = importlib.util.spec_from_file_location(
        COMMENT_MODULE_NAME,
        ROOT / "core" / "tasks" / "qinteract.py",
    )
    comment_module = importlib.util.module_from_spec(comment_spec)
    sys.modules[comment_spec.name] = comment_module
    comment_spec.loader.exec_module(comment_module)
    return comment_module, models_module


def _load_qzone_service_module():
    _install_stub_module("astrbot", api=_install_stub_module("astrbot.api", logger=_Logger()))
    for name in [PACKAGE_NAME, CORE_PACKAGE_NAME, SPACE_PACKAGE_NAME]:
        module = _install_stub_module(name)
        if name == CORE_PACKAGE_NAME:
            module.__path__ = [str(ROOT / "core")]
        elif name == SPACE_PACKAGE_NAME:
            module.__path__ = [str(ROOT / "core" / "space")]
        else:
            module.__path__ = [str(ROOT)]

    models_spec = importlib.util.spec_from_file_location(
        MODELS_MODULE_NAME,
        ROOT / "core" / "space" / "models.py",
    )
    models_module = importlib.util.module_from_spec(models_spec)
    sys.modules[models_spec.name] = models_module
    models_spec.loader.exec_module(models_module)

    _install_stub_module(
        "aiohttp",
        ClientSession=type("ClientSession", (), {}),
        ClientTimeout=lambda total=None: types.SimpleNamespace(total=total),
        ClientError=Exception,
    )
    _install_stub_module(
        f"{SPACE_PACKAGE_NAME}.upload",
        QzoneMediaUploadMixin=type("QzoneMediaUploadMixin", (), {}),
    )
    _install_stub_module(
        f"{SPACE_PACKAGE_NAME}.parser",
        parse_feed_item=lambda *args, **kwargs: None,
        parse_feed_list=lambda *args, **kwargs: [],
        parse_home_feed_list=lambda *args, **kwargs: [],
        parse_qzone_response=lambda *args, **kwargs: {},
        parse_recent_feed_list=lambda *args, **kwargs: [],
        parse_upload_result=lambda *args, **kwargs: {},
    )
    _install_stub_module(
        f"{SPACE_PACKAGE_NAME}.parse",
        parse_feed_item=lambda *args, **kwargs: None,
        parse_feed_list=lambda *args, **kwargs: [],
        parse_home_feed_list=lambda *args, **kwargs: [],
        parse_qzone_response=lambda *args, **kwargs: {},
        parse_recent_feed_list=lambda *args, **kwargs: [],
        parse_upload_result=lambda *args, **kwargs: {},
    )
    _install_stub_module(
        f"{SPACE_PACKAGE_NAME}.entry",
        parse_about_me=lambda *args, **kwargs: {},
        parse_favorites=lambda *args, **kwargs: {},
        parse_last_year=lambda *args, **kwargs: {},
        parse_message_board=lambda *args, **kwargs: {},
    )
    _install_stub_module(
        f"{SPACE_PACKAGE_NAME}.relation",
        parse_qzone_relations=lambda *args, **kwargs: [],
        parse_qzone_visit_stats=lambda *args, **kwargs: {},
    )

    service_spec = importlib.util.spec_from_file_location(
        SERVICE_MODULE_NAME,
        ROOT / "core" / "space" / "service.py",
    )
    service_module = importlib.util.module_from_spec(service_spec)
    sys.modules[service_spec.name] = service_module
    service_spec.loader.exec_module(service_module)
    return service_module, models_module


class FakeDb:
    def __init__(self, state=None):
        self.state = state or {}

    async def get_state(self, key, default=None):
        return self.state.get(key, default)

    async def set_state(self, key, value):
        self.state[key] = value


class QzoneAutoCommentTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_query_failure_logs_debug(self):
        module, _models = _load_auto_comment_module()
        task_module = sys.modules[f"{TASKS_PACKAGE_NAME}.interact.task"]
        calls = []

        def record(level):
            return lambda message: calls.append((level, message))

        class Owner:
            def __init__(self):
                self.saved = None

            async def _qzone_auto_save_state(self, state_key, state, processed, result, *, run_at=None):
                self.saved = (state_key, state, processed, result, run_at)

        owner = Owner()
        result = task_module._qzone_auto_result(commented=0)
        with patch.object(task_module.logger, "debug", record("debug")):
            with patch.object(task_module.logger, "warning", record("warning")):
                returned = await task_module._qzone_abort_query_failure(
                    owner,
                    state_key="state",
                    state={},
                    processed={},
                    result=result,
                    run_at=123,
                    message="[每日分享] QQ 空间自动评论查询失败",
                    error=RuntimeError("network busy"),
                )

        self.assertIs(returned, result)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(calls, [("debug", "[每日分享] QQ 空间自动评论查询失败: network busy")])
        self.assertIsNotNone(owner.saved)

    def test_reply_submit_targets_prioritize_latest_comment_before_parent(self):
        service_module, models = _load_qzone_service_module()
        post = models.QzonePost(uin=1, tid="self")
        parent = models.QzoneComment(uin=2, nickname="Alice", content="first", tid="c1")
        latest = models.QzoneComment(
            uin=2,
            nickname="Alice",
            content="second",
            tid="r2",
            parent_tid="c1",
            reply_to_tid="r1",
        )

        targets = service_module.QzoneService._reply_submit_targets(
            post,
            latest,
            parent_comment=parent,
        )

        self.assertEqual(
            targets,
            [
                {"comment_id": "r2", "comment_uin": 2},
            ],
        )

    async def test_reply_comment_returns_submitted_target_debug_info(self):
        service_module, models = _load_qzone_service_module()
        service = service_module.QzoneService(plugin=types.SimpleNamespace())
        post = models.QzonePost(uin=1, tid="self")
        comment = models.QzoneComment(uin=2, nickname="Alice", content="second", tid="r2", parent_tid="c1")
        parent = models.QzoneComment(uin=2, nickname="Alice", content="first", tid="c1")
        service._post_cache[post.key] = post
        service.context = lambda: asyncio.sleep(0, result=types.SimpleNamespace(uin=1, gtk="1"))
        payloads = iter([{"code": 0}])
        service._request = lambda *args, **kwargs: asyncio.sleep(0, result=next(payloads))
        service._verify_thread_reply_submission = lambda *args, **kwargs: asyncio.sleep(0, result={
            "status": "confirmed",
            "verified_reply_tid": "r3",
            "verified_reply_to_tid": "r2",
            "verified_reply_to_uin": 2,
            "candidates": [],
        })

        result = await service.reply_comment(post.key, comment, "reply", parent_comment=parent)

        self.assertEqual(result["comment_id"], "r2")
        self.assertEqual(result["comment_uin"], 2)
        self.assertEqual(result["transport"], "addreply_ugc")
        self.assertEqual(
            result["attempted_targets"],
            [
                {"comment_id": "r2", "comment_uin": 2},
            ],
        )
        self.assertEqual(len(result["attempts"]), 1)
        self.assertEqual(result["attempts"][0]["transport"], "addreply_ugc")
        self.assertEqual(result["attempts"][0]["payload_comment_id"], "c1")
        self.assertEqual(result["verification_status"], "confirmed")

    def test_clean_comment_removes_prefix(self):
        module, _models = _load_auto_comment_module()

        result = module._clean_auto_comment_text("评论：\"今天这段真的很有画面感呀\"")

        self.assertEqual(result, "今天这段真的很有画面感呀")

    def test_clean_comment_does_not_truncate_by_default(self):
        module, _models = _load_auto_comment_module()
        text = (
            "既然是真的，那今晚的疯狂星期四就靠你表现了。"
            "不过先说好，排队归你，点单归我。"
        )

        result = module._clean_auto_comment_text(text)

        self.assertEqual(result, text)

    def test_clean_comment_can_fit_thread_reply_byte_limit(self):
        module, _models = _load_auto_comment_module()

        result = module._clean_auto_comment_text(
            "想得美，我这膝盖骨硬得像板砖，怕把你直接硌失忆。",
            max_bytes=60,
        )

        self.assertEqual(result, "想得美，我这膝盖骨硬得像板砖。")
        self.assertLessEqual(len(result.encode("utf-8")), 60)

    def test_clean_comment_normalizes_platform_mention_before_byte_limit(self):
        module, _models = _load_auto_comment_module()

        result = module._clean_auto_comment_text(
            "@{uin:89761500,nick:四次元未来,who:1,auto:1} 想得美，\n"
            "我刚洗完澡，\n膝盖拒绝承重。\n沙发上的靠枕已经帮你拍蓬松了，\n爱躺不躺。",
            max_bytes=60,
        )

        self.assertEqual(result, "想得美，我刚洗完澡，膝盖拒绝承重。")
        self.assertNotIn("@{", result)
        self.assertLessEqual(len(result.encode("utf-8")), 60)

    def test_clean_comment_drops_broken_platform_mention(self):
        module, _models = _load_auto_comment_module()

        result = module._clean_auto_comment_text("@{uin:89761500,nick:四次元未来,who:1。", max_bytes=60)

        self.assertEqual(result, "")

    def test_detects_self_comment(self):
        module, models = _load_auto_comment_module()
        post = models.QzonePost(
            uin=2,
            tid="a",
            comments=[models.QzoneComment(uin=1, content="已经评论过")],
        )

        self.assertTrue(module._post_has_self_comment(post, 1))

    def test_detects_self_reply_to_comment(self):
        module, models = _load_auto_comment_module()
        target_comment = models.QzoneComment(uin=2, nickname="Alice", content="好看", tid="c1")
        post = models.QzonePost(
            uin=1,
            tid="a",
            comments=[
                target_comment,
                models.QzoneComment(uin=1, content="谢谢你呀", tid="r1", parent_tid="c1"),
            ],
        )

        self.assertTrue(module._comment_has_self_reply(post, target_comment, 1))

    def test_detects_reply_targeting_self_by_reply_to_tid(self):
        module, models = _load_auto_comment_module()
        post = models.QzonePost(
            uin=1,
            tid="a",
            comments=[
                models.QzoneComment(uin=2, nickname="Alice", content="好看", tid="c1"),
                models.QzoneComment(uin=1, nickname="Me", content="谢谢", tid="r1", parent_tid="c1"),
                models.QzoneComment(uin=2, nickname="Alice", content="哈哈", tid="r2", parent_tid="c1", reply_to_tid="r1"),
            ],
        )
        index = module.QzoneCommentIndex.build(post, 1)

        self.assertTrue(module._comment_replies_to_self(post.comments[2], 1, index=index))

    def test_detects_reply_targeting_self_by_mention_uin(self):
        module, models = _load_auto_comment_module()
        post = models.QzonePost(
            uin=1,
            tid="a",
            comments=[
                models.QzoneComment(uin=2, nickname="Alice", content="好看", tid="c1"),
                models.QzoneComment(uin=1, nickname="Me", content="谢谢", tid="r1", parent_tid="c1"),
                models.QzoneComment(
                    uin=2,
                    nickname="Alice",
                    content="@{uin:1,nick:Me,auto:1} 哈哈",
                    tid="r2",
                    parent_tid="c1",
                ),
            ],
        )
        index = module.QzoneCommentIndex.build(post, 1)

        self.assertTrue(module._comment_replies_to_self(post.comments[2], 1, index=index))

    def test_infers_thread_parent_from_reply_target(self):
        module, models = _load_auto_comment_module()
        post = models.QzonePost(
            uin=1,
            tid="a",
            comments=[
                models.QzoneComment(uin=2, nickname="Alice", content="好看", tid="c1"),
                models.QzoneComment(uin=1, nickname="Me", content="谢谢", tid="r1", parent_tid="c1"),
                models.QzoneComment(uin=2, nickname="Alice", content="哈哈", tid="r2", reply_to_tid="r1"),
            ],
        )
        index = module.QzoneCommentIndex.build(post, 1)

        self.assertIs(index.parent_of(post.comments[2]), post.comments[0])

    def test_thread_candidate_skips_when_self_already_replied_to_target(self):
        module, models = _load_auto_comment_module()

        class Manager(module.TaskQzoneAutoCommentMixin):
            pass

        post = models.QzonePost(
            uin=1,
            tid="a",
            comments=[
                models.QzoneComment(uin=2, nickname="Alice", content="好看", tid="c1"),
                models.QzoneComment(uin=1, nickname="Me", content="谢谢", tid="r1", parent_tid="c1"),
                models.QzoneComment(uin=2, nickname="Alice", content="哈哈", tid="r2", parent_tid="c1", reply_to_tid="r1"),
                models.QzoneComment(uin=1, nickname="Me", content="我也觉得", tid="r3", parent_tid="c1", reply_to_tid="r2"),
            ],
        )
        index = module.QzoneCommentIndex.build(post, 1)

        self.assertFalse(
            Manager()._qzone_auto_reply_thread_candidate(
                post,
                post.comments[0],
                post.comments[2],
                self_uin=1,
                processed={},
                index=index,
            )
        )

    def test_thread_candidate_skips_older_friend_reply_when_newer_friend_reply_exists(self):
        module, models = _load_auto_comment_module()

        class Manager(module.TaskQzoneAutoCommentMixin):
            pass

        post = models.QzonePost(
            uin=1,
            tid="a",
            comments=[
                models.QzoneComment(uin=2, nickname="Alice", content="首评", tid="c1", create_time=100),
                models.QzoneComment(uin=1, nickname="Me", content="回一嘴", tid="r1", parent_tid="c1", create_time=200),
                models.QzoneComment(uin=2, nickname="Alice", content="第一次追评", tid="r2", parent_tid="c1", create_time=300),
                models.QzoneComment(uin=2, nickname="Alice", content="第二次追评", tid="r3", parent_tid="c1", create_time=400),
            ],
        )
        index = module.QzoneCommentIndex.build(post, 1)

        self.assertEqual(
            Manager()._qzone_auto_reply_thread_skip_reason(
                post,
                post.comments[0],
                post.comments[2],
                self_uin=1,
                processed={},
                index=index,
            ),
            "has_later_nonself_reply",
        )

    def test_summary_generation_failed_suffix_hides_zero_failures(self):
        module, _models = _load_auto_comment_module()

        self.assertEqual(module._qzone_summary_generation_failed_suffix({"generation_failed": 0}), "")
        self.assertEqual(
            module._qzone_summary_generation_failed_suffix({"generation_failed": 2}),
            "，生成/判断失败 2 条",
        )
        self.assertEqual(module._qzone_summary_generation_failed_suffix({"failed": 2}), "")

    def test_auto_interaction_skips_official_qzone_posts(self):
        module, models = _load_auto_comment_module()

        class Manager(module.TaskQzoneAutoCommentMixin):
            pass

        manager = Manager()
        official = models.QzonePost(uin=10000, tid="official", name="官方Qzone", text="活动广告")
        friend = models.QzonePost(uin=2, tid="friend", name="朋友", text="今天去了书店")

        self.assertFalse(manager._qzone_auto_like_candidate(official, self_uin=1, processed={}))
        self.assertFalse(
            manager._qzone_auto_comment_candidate(
                official,
                self_uin=1,
                processed={},
                index=module.QzoneCommentIndex.build(official, 1),
            )
        )
        self.assertTrue(manager._qzone_auto_like_candidate(friend, self_uin=1, processed={}))
        self.assertTrue(
            manager._qzone_auto_comment_candidate(
                friend,
                self_uin=1,
                processed={},
                index=module.QzoneCommentIndex.build(friend, 1),
            )
        )

    async def test_auto_comment_and_reply_system_prompt_includes_persona(self):
        module, models = _load_auto_comment_module()
        persona_prompt = "你的人设是温柔但有点俏皮。"

        class ContentService:
            async def _get_persona_info(self):
                return {"prompt": persona_prompt}

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {}
                self.prompts = []
                self.system_prompts = []
                self.plugin = types.SimpleNamespace(
                    llm_conf={"use_persona": True},
                    content_service=ContentService(),
                )

            async def llm(self, **kwargs):
                self.prompts.append(kwargs.get("prompt", ""))
                self.system_prompts.append(kwargs.get("system_prompt", ""))
                return "这句好有生活感呀"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm
        friend_post = models.QzonePost(uin=2, tid="friend", name="Alice", text="今天去了书店")
        self_post = models.QzonePost(uin=1, tid="self", name="我", text="今天很开心")
        comment = models.QzoneComment(uin=2, nickname="Alice", content="真不错", tid="c1")

        await manager._generate_qzone_auto_comment(friend_post)
        await manager._generate_qzone_auto_reply(self_post, comment)

        self.assertEqual(len(manager.system_prompts), 2)
        for system_prompt in manager.system_prompts:
            self.assertIn(persona_prompt, system_prompt)
            self.assertIn("【QQ 空间互动规则】", system_prompt)
        self.assertIn("真实好友的语气", manager.system_prompts[0])
        self.assertIn("真实 QQ 空间主人身份", manager.system_prompts[1])
        self.assertIn("当前本地时间：", manager.prompts[0])
        self.assertIn("发布时间：", manager.prompts[0])
        self.assertIn("当前本地时间：", manager.prompts[1])
        self.assertIn("评论时间：未知", manager.prompts[1])
        self.assertIn("必须以提示中的【当前本地时间】为准", manager.system_prompts[0])

    async def test_auto_interaction_prompts_include_life_context(self):
        module, models = _load_auto_comment_module()

        class CtxService:
            def __init__(self):
                self.calls = 0

            async def get_life_context(self):
                self.calls += 1
                return "CURRENT_LIFE_CONTEXT weather=rain mood=quiet"

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {}
                self.ctx_service = CtxService()
                self.prompts = []
                self.plugin = types.SimpleNamespace(llm_conf={"use_persona": False})

            async def llm(self, **kwargs):
                self.prompts.append(kwargs.get("prompt", ""))
                return "sounds good"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm
        friend_post = models.QzonePost(uin=2, tid="friend", name="Alice", text="bookstore afternoon")
        self_post = models.QzonePost(uin=1, tid="self", name="Me", text="quiet day")
        parent_comment = models.QzoneComment(uin=2, nickname="Alice", content="nice", tid="c1")
        second_level = models.QzoneComment(
            uin=2,
            nickname="Alice",
            content="same here",
            tid="c2",
            parent_tid="c1",
        )
        await manager._generate_qzone_auto_comment(friend_post)
        await manager._generate_qzone_auto_reply(self_post, parent_comment)
        await manager._generate_qzone_auto_reply_thread(self_post, parent_comment, second_level)

        self.assertEqual(len(manager.prompts), 3)
        self.assertEqual(manager.ctx_service.calls, 3)
        for prompt in manager.prompts:
            self.assertIn("CURRENT_LIFE_CONTEXT", prompt)
            self.assertIn("【当前生活状态参考】", prompt)
            self.assertIn("不要主动透露具体地点、行程、关系、备忘录", prompt)

    async def test_auto_comment_includes_image_vision_context_when_enabled(self):
        module, models = _load_auto_comment_module()

        class Context:
            def __init__(self):
                self.calls = []

            def get_using_provider(self):
                return types.SimpleNamespace(meta=lambda: types.SimpleNamespace(id="default-provider"))

            async def llm_generate(self, **kwargs):
                self.calls.append(kwargs)
                return types.SimpleNamespace(completion_text="桌上有一杯咖啡和一本打开的书")

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {"qzone_enable_auto_comment_image_vision": True}
                self.prompts = []
                self.context = Context()
                self.plugin = types.SimpleNamespace(
                    llm_conf={"use_persona": False, "llm_provider_id": "ignored-provider"},
                    context=self.context,
                )

            async def llm(self, **kwargs):
                self.prompts.append(kwargs.get("prompt", ""))
                return "这下午很有生活感"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm
        state = {}
        post = models.QzonePost(
            uin=2,
            tid="image-post",
            name="FRIEND_NICK",
            text="午后",
            images=["https://example.com/cafe.jpg"],
        )

        result = await manager._generate_qzone_auto_comment(post, state=state)

        self.assertEqual(result, "这下午很有生活感")
        self.assertEqual(manager.context.calls[0]["chat_provider_id"], "default-provider")
        self.assertEqual(manager.context.calls[0]["image_urls"], ["https://example.com/cafe.jpg"])
        self.assertIn("【配图识别】", manager.prompts[0])
        self.assertIn("桌上有一杯咖啡和一本打开的书", manager.prompts[0])
        self.assertIn("image_vision_cache", state)

    async def test_auto_comment_image_vision_logs_debug_path(self):
        module, models = _load_auto_comment_module()

        class Context:
            def get_using_provider(self):
                return types.SimpleNamespace(meta=lambda: types.SimpleNamespace(id="default-provider"))

            async def llm_generate(self, **kwargs):
                return types.SimpleNamespace(completion_text="画面里有人站在阳光下")

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {"qzone_enable_auto_comment_image_vision": True}
                self.plugin = types.SimpleNamespace(
                    llm_conf={"use_persona": False},
                    context=Context(),
                )

            async def llm(self, **kwargs):
                return "这张很有夏天的感觉"

        logs = []
        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm
        post = models.QzonePost(
            uin=2,
            tid="image-post",
            name="FRIEND_NICK",
            text="",
            images=["https://example.com/sun.jpg"],
        )

        vision_module = sys.modules[f"{TASKS_PACKAGE_NAME}.interact.vision"]
        with patch.object(vision_module.logger, "debug", lambda message, *args, **kwargs: logs.append(str(message))):
            await manager._generate_qzone_auto_comment(post, state={})

        self.assertTrue(any("QQ 空间好友动态配图识别开始" in item for item in logs))
        self.assertTrue(any("QQ 空间好友动态配图识别成功" in item for item in logs))

    async def test_auto_comment_image_vision_reuses_state_cache(self):
        module, models = _load_auto_comment_module()

        class Context:
            def __init__(self):
                self.calls = []

            def get_using_provider(self):
                return types.SimpleNamespace(meta=lambda: types.SimpleNamespace(id="default-provider"))

            async def llm_generate(self, **kwargs):
                self.calls.append(kwargs["image_urls"][0])
                return types.SimpleNamespace(completion_text="窗边有一盆绿植")

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {"qzone_enable_auto_comment_image_vision": True}
                self.prompts = []
                self.context = Context()
                self.plugin = types.SimpleNamespace(
                    llm_conf={"use_persona": False},
                    context=self.context,
                )

            async def llm(self, **kwargs):
                self.prompts.append(kwargs.get("prompt", ""))
                return "养得不错嘛"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm
        state = {}
        post = models.QzonePost(
            uin=2,
            tid="cached-image-post",
            name="FRIEND_NICK",
            text="",
            images=["https://example.com/plant.jpg"],
        )

        await manager._generate_qzone_auto_comment(post, state=state)
        await manager._generate_qzone_auto_comment(post, state=state)

        self.assertEqual(manager.context.calls, ["https://example.com/plant.jpg"])
        self.assertEqual(len(manager.prompts), 2)
        self.assertIn("窗边有一盆绿植", manager.prompts[1])

    async def test_auto_comment_image_vision_cache_ignores_volatile_url_query(self):
        module, models = _load_auto_comment_module()

        class Context:
            def __init__(self):
                self.calls = []

            def get_using_provider(self):
                return types.SimpleNamespace(meta=lambda: types.SimpleNamespace(id="default-provider"))

            async def llm_generate(self, **kwargs):
                self.calls.append(kwargs["image_urls"][0])
                return types.SimpleNamespace(completion_text="有人在美术馆看蓝色画作")

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {"qzone_enable_auto_comment_image_vision": True}
                self.prompts = []
                self.context = Context()
                self.plugin = types.SimpleNamespace(
                    llm_conf={"use_persona": False},
                    context=self.context,
                )

            async def llm(self, **kwargs):
                self.prompts.append(kwargs.get("prompt", ""))
                return "这张很文艺"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm
        state = {}
        first = models.QzonePost(
            uin=2,
            tid="same-image-post",
            name="FRIEND_NICK",
            text="",
            images=["https://m.qpic.cn/psc?/V10abc/photo.jpg&token=aaa&_t=1"],
        )
        second = models.QzonePost(
            uin=2,
            tid="same-image-post",
            name="FRIEND_NICK",
            text="",
            images=["https://m.qpic.cn/psc?/V10abc/photo.jpg&token=bbb&_t=2"],
        )

        await manager._generate_qzone_auto_comment(first, state=state)
        await manager._generate_qzone_auto_comment(second, state=state)

        self.assertEqual(manager.context.calls, ["https://m.qpic.cn/psc?/V10abc/photo.jpg&token=aaa&_t=1"])
        self.assertIn("有人在美术馆看蓝色画作", manager.prompts[1])

    async def test_auto_comment_image_vision_cache_survives_changed_post_key(self):
        module, models = _load_auto_comment_module()

        class Context:
            def __init__(self):
                self.calls = []

            def get_using_provider(self):
                return types.SimpleNamespace(meta=lambda: types.SimpleNamespace(id="default-provider"))

            async def llm_generate(self, **kwargs):
                self.calls.append(kwargs["image_urls"][0])
                return types.SimpleNamespace(completion_text="展厅里有人注视蓝色画作")

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {"qzone_enable_auto_comment_image_vision": True}
                self.prompts = []
                self.context = Context()
                self.plugin = types.SimpleNamespace(
                    llm_conf={"use_persona": False},
                    context=self.context,
                )

            async def llm(self, **kwargs):
                self.prompts.append(kwargs.get("prompt", ""))
                return "这张照片很安静"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm
        state = {}
        first = models.QzonePost(
            uin=2,
            tid="friend-feed-key",
            name="FRIEND_NICK",
            text="",
            images=["https://m.qpic.cn/psc?/V10abc/photo.jpg&token=aaa"],
        )
        second = models.QzonePost(
            uin=2,
            tid="recent-feed-key",
            name="FRIEND_NICK",
            text="",
            images=["https://m.qpic.cn/psc?/V10abc/photo.jpg&token=bbb"],
        )

        await manager._generate_qzone_auto_comment(first, state=state)
        await manager._generate_qzone_auto_comment(second, state=state)

        self.assertEqual(manager.context.calls, ["https://m.qpic.cn/psc?/V10abc/photo.jpg&token=aaa"])
        self.assertIn("展厅里有人注视蓝色画作", manager.prompts[1])

    async def test_auto_comment_image_vision_cache_uses_post_context_when_image_url_changes(self):
        module, models = _load_auto_comment_module()

        class Context:
            def __init__(self):
                self.calls = []

            def get_using_provider(self):
                return types.SimpleNamespace(meta=lambda: types.SimpleNamespace(id="default-provider"))

            async def llm_generate(self, **kwargs):
                self.calls.append(kwargs["image_urls"][0])
                return types.SimpleNamespace(completion_text="一名女生在展厅里看蓝色画作")

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {"qzone_enable_auto_comment_image_vision": True}
                self.prompts = []
                self.context = Context()
                self.plugin = types.SimpleNamespace(
                    llm_conf={"use_persona": False},
                    context=self.context,
                )

            async def llm(self, **kwargs):
                self.prompts.append(kwargs.get("prompt", ""))
                return "美术馆氛围感有了"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm
        state = {}
        first = models.QzonePost(
            uin=2,
            tid="friend-feed-key",
            name="会好起来的",
            text="今天去看画",
            create_time=1782467000,
            images=["https://m.qpic.cn/psc?/V10abc/photo-a.jpg&token=aaa"],
        )
        second = models.QzonePost(
            uin=2,
            tid="recent-feed-key",
            name="会好起来的",
            text="今天去看画",
            create_time=1782467000,
            images=["https://r.qzone.qq.com/photo/random-cdn-path.jpg?token=bbb"],
        )

        await manager._generate_qzone_auto_comment(first, state=state)
        await manager._generate_qzone_auto_comment(second, state=state)

        self.assertEqual(manager.context.calls, ["https://m.qpic.cn/psc?/V10abc/photo-a.jpg&token=aaa"])
        self.assertIn("一名女生在展厅里看蓝色画作", manager.prompts[1])

    async def test_auto_comment_image_vision_cache_uses_stable_post_id_without_time(self):
        module, models = _load_auto_comment_module()

        class Context:
            def __init__(self):
                self.calls = []

            def get_using_provider(self):
                return types.SimpleNamespace(meta=lambda: types.SimpleNamespace(id="default-provider"))

            async def llm_generate(self, **kwargs):
                self.calls.append(kwargs["image_urls"][0])
                return types.SimpleNamespace(completion_text="女生在展厅里看蓝色画作")

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {"qzone_enable_auto_comment_image_vision": True}
                self.prompts = []
                self.context = Context()
                self.plugin = types.SimpleNamespace(
                    llm_conf={"use_persona": False},
                    context=self.context,
                )

            async def llm(self, **kwargs):
                self.prompts.append(kwargs.get("prompt", ""))
                return "这张很有氛围"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm
        state = {}
        first = models.QzonePost(
            uin=2,
            tid="stable-post",
            name="会好起来的",
            text="",
            images=["https://m.qpic.cn/psc?/old-cdn/photo-a.jpg&token=aaa"],
        )
        second = models.QzonePost(
            uin=2,
            tid="stable-post",
            name="会好起来的",
            text="",
            images=["https://r.qzone.qq.com/photo/new-cdn-path.jpg?token=bbb"],
        )

        await manager._generate_qzone_auto_comment(first, state=state)
        await manager._generate_qzone_auto_comment(second, state=state)

        self.assertEqual(manager.context.calls, ["https://m.qpic.cn/psc?/old-cdn/photo-a.jpg&token=aaa"])
        self.assertIn("女生在展厅里看蓝色画作", manager.prompts[1])

    async def test_auto_comment_image_vision_cache_is_saved_immediately(self):
        module, models = _load_auto_comment_module()

        class Context:
            def get_using_provider(self):
                return types.SimpleNamespace(meta=lambda: types.SimpleNamespace(id="default-provider"))

            async def llm_generate(self, **kwargs):
                return types.SimpleNamespace(completion_text="画面里有一杯咖啡")

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {"qzone_enable_auto_comment_image_vision": True}
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    llm_conf={"use_persona": False},
                    context=Context(),
                )

            async def llm(self, **kwargs):
                return "这杯咖啡看着很救命"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm
        state = {}
        post = models.QzonePost(
            uin=2,
            tid="save-cache-post",
            name="FRIEND_NICK",
            text="",
            images=["https://example.com/cafe.jpg?token=temporary"],
        )

        await manager._generate_qzone_auto_comment(post, state=state)

        saved = manager.db.state[module.QZONE_AUTO_COMMENT_STATE_KEY]
        self.assertIn("画面里有一杯咖啡", set(saved["image_vision_cache"].values()))

    async def test_auto_comment_image_vision_cache_save_merges_existing_state(self):
        module, models = _load_auto_comment_module()

        class Context:
            def get_using_provider(self):
                return types.SimpleNamespace(meta=lambda: types.SimpleNamespace(id="default-provider"))

            async def llm_generate(self, **kwargs):
                return types.SimpleNamespace(completion_text="画面里有一束花")

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {"qzone_enable_auto_comment_image_vision": True}
                self.db = FakeDb(
                    {
                        module.QZONE_AUTO_COMMENT_STATE_KEY: {
                            "processed": {"old": {"action": "commented"}},
                            "last_result": {"commented": 1},
                        }
                    }
                )
                self.plugin = types.SimpleNamespace(
                    llm_conf={"use_persona": False},
                    context=Context(),
                )

            async def llm(self, **kwargs):
                return "花挺好看"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm
        state = {}
        post = models.QzonePost(
            uin=2,
            tid="save-merge-post",
            name="FRIEND_NICK",
            text="",
            images=["https://example.com/flower.jpg?token=temporary"],
        )

        await manager._generate_qzone_auto_comment(post, state=state)

        saved = manager.db.state[module.QZONE_AUTO_COMMENT_STATE_KEY]
        self.assertEqual(saved["processed"], {"old": {"action": "commented"}})
        self.assertEqual(saved["last_result"], {"commented": 1})
        self.assertIn("画面里有一束花", set(saved["image_vision_cache"].values()))

    async def test_auto_comment_image_vision_provider_overrides_llm_provider(self):
        module, models = _load_auto_comment_module()

        class Context:
            def __init__(self):
                self.calls = []

            async def llm_generate(self, **kwargs):
                self.calls.append(kwargs)
                return types.SimpleNamespace(completion_text="图片里有一只猫")

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "qzone_enable_auto_comment_image_vision": True,
                    "qzone_auto_comment_image_vision_provider": "qzone-vision-provider",
                }
                self.context = Context()
                self.plugin = types.SimpleNamespace(
                    llm_conf={"use_persona": False, "llm_provider_id": "normal-provider"},
                    context=self.context,
                )

            async def llm(self, **kwargs):
                return "猫猫营业了"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm
        post = models.QzonePost(
            uin=2,
            tid="image-post",
            name="FRIEND_NICK",
            text="",
            images=["https://example.com/cat.jpg"],
        )

        await manager._generate_qzone_auto_comment(post, state={})

        self.assertEqual(manager.context.calls[0]["chat_provider_id"], "qzone-vision-provider")

    async def test_auto_comment_image_vision_skips_without_configured_or_default_provider(self):
        module, models = _load_auto_comment_module()

        class Context:
            def __init__(self):
                self.calls = []

            def get_using_provider(self):
                return None

            async def llm_generate(self, **kwargs):
                self.calls.append(kwargs)
                return types.SimpleNamespace(completion_text="不应调用")

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {"qzone_enable_auto_comment_image_vision": True}
                self.prompts = []
                self.context = Context()
                self.plugin = types.SimpleNamespace(
                    llm_conf={"use_persona": False, "llm_provider_id": "ignored-provider"},
                    context=self.context,
                )

            async def llm(self, **kwargs):
                self.prompts.append(kwargs.get("prompt", ""))
                return "按纯文字评论"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm
        post = models.QzonePost(
            uin=2,
            tid="image-post",
            name="FRIEND_NICK",
            text="正文",
            images=["https://example.com/photo.jpg"],
        )

        result = await manager._generate_qzone_auto_comment(post, state={})

        self.assertEqual(result, "按纯文字评论")
        self.assertEqual(manager.context.calls, [])
        self.assertNotIn("【配图识别】", manager.prompts[0])

    async def test_thread_reply_prompt_includes_same_floor_history(self):
        module, models = _load_auto_comment_module()

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {}
                self.prompts = []
                self.plugin = types.SimpleNamespace(llm_conf={"use_persona": False})

            async def llm(self, **kwargs):
                self.prompts.append(kwargs.get("prompt", ""))
                return "那就这么说定了"

        parent = models.QzoneComment(uin=2, nickname="四次元未来", content="到家了吗", tid="c1", create_time=100)
        bot_reply = models.QzoneComment(
            uin=1,
            nickname="Me",
            content="早就到家瘫着了",
            tid="r1",
            parent_tid="c1",
            reply_to_tid="c1",
            reply_to_nickname="四次元未来",
            create_time=200,
        )
        previous_friend_reply = models.QzoneComment(
            uin=2,
            nickname="四次元未来",
            content="那请我喝奶茶",
            tid="r2",
            parent_tid="c1",
            reply_to_tid="r1",
            reply_to_nickname="Me",
            create_time=300,
        )
        target = models.QzoneComment(
            uin=2,
            nickname="四次元未来",
            content="别装没看见",
            tid="r3",
            parent_tid="c1",
            reply_to_tid="r1",
            reply_to_nickname="Me",
            create_time=400,
        )
        later_reply = models.QzoneComment(
            uin=2,
            nickname="四次元未来",
            content="这是之后才出现的内容",
            tid="r4",
            parent_tid="c1",
            reply_to_tid="r3",
            reply_to_nickname="Me",
            create_time=500,
        )
        other_floor = models.QzoneComment(uin=3, nickname="路人", content="隔壁楼内容", tid="c2", create_time=250)
        post = models.QzonePost(
            uin=1,
            tid="self",
            name="Me",
            text="今天很开心",
            comments=[parent, bot_reply, other_floor, previous_friend_reply, target, later_reply],
        )
        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        await manager._generate_qzone_auto_reply_thread(post, parent, target)

        self.assertEqual(len(manager.prompts), 1)
        prompt = manager.prompts[0]
        self.assertIn("同楼前文对话", prompt)
        self.assertIn("早就到家瘫着了", prompt)
        self.assertIn("那请我喝奶茶", prompt)
        self.assertIn("新的二级回复：别装没看见", prompt)
        self.assertIn("只对最后列出的“新的二级回复”", prompt)
        self.assertNotIn("@{", prompt)
        self.assertNotIn("内部格式", prompt)
        self.assertNotIn("这是之后才出现的内容", prompt)
        self.assertNotIn("隔壁楼内容", prompt)

    async def test_thread_reply_generation_keeps_complete_short_sentence(self):
        module, models = _load_auto_comment_module()

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {}
                self.plugin = types.SimpleNamespace(llm_conf={"use_persona": False})

            async def llm(self, **kwargs):
                return "@{uin:89761500,nick:四次元未来,who:1,auto:1} 既然是真的，那今晚的疯狂星期四就靠你表现了。"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm
        post = models.QzonePost(uin=1, tid="self", name="Me", text="今天很开心")
        parent = models.QzoneComment(uin=2, nickname="四次元未来", content="借我膝盖", tid="c1")
        target = models.QzoneComment(uin=2, nickname="四次元未来", content="想靠一下", tid="r1", parent_tid="c1")

        result = await manager._generate_qzone_auto_reply_thread(post, parent, target)

        self.assertEqual(result, "既然是真的，那今晚的疯狂星期四就靠你表现了。")
        self.assertNotIn("@{", result)

    async def test_thread_reply_submit_keeps_pending_reply_complete(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.reply = ""

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.reply = content
                return {
                    "comment_id": str(getattr(comment, "tid", "") or ""),
                    "comment_uin": int(getattr(comment, "uin", 0) or 0),
                    "transport": "addreply_ugc",
                }

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.plugin = types.SimpleNamespace(
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

        manager = Manager()
        processed = {}
        result = {"replied": 0, "skipped": 0}
        post = models.QzonePost(uin=1, tid="self", name="Me", text="今天很开心")
        parent = models.QzoneComment(uin=2, nickname="四次元未来", content="借我膝盖", tid="c1")
        target = models.QzoneComment(uin=2, nickname="四次元未来", content="想靠一下", tid="r1", parent_tid="c1")

        await manager._qzone_send_auto_reply_result(
            post,
            target,
            processed,
            result,
            item_key="1:self:r1",
            reply="既然是真的，那今晚的疯狂星期四就靠你表现了。",
            processed_action="thread_replied",
            dashboard_action="auto_reply",
            log_label="已自动回评 QQ 空间评论",
            parent_comment_id="c1",
            parent_comment=parent,
        )

        self.assertEqual(manager.plugin.qzone_service.reply, "既然是真的，那今晚的疯狂星期四就靠你表现了。")
        self.assertEqual(processed["1:self:r1"]["content"], "既然是真的，那今晚的疯狂星期四就靠你表现了。")

    async def test_auto_interaction_system_prompt_skips_persona_when_disabled(self):
        module, _models = _load_auto_comment_module()

        class ContentService:
            async def _get_persona_info(self):
                return {"prompt": "这段人设不应被注入。"}

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.plugin = types.SimpleNamespace(
                    llm_conf={"use_persona": False},
                    content_service=ContentService(),
                )

        manager = Manager()

        system_prompt = await manager._qzone_auto_interaction_system_prompt("只输出回复正文。")

        self.assertIn("只输出回复正文。", system_prompt)
        self.assertIn("必须以提示中的【当前本地时间】为准", system_prompt)
        self.assertNotIn("这段人设不应被注入。", system_prompt)

    async def test_execute_comments_only_commentable_friend_posts(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.comments = []
                self.posts = [
                    models.QzonePost(uin=1, tid="self", name="我", text="自己的动态"),
                    models.QzonePost(
                        uin=2,
                        tid="done",
                        name="朋友A",
                        text="已经有评论",
                        comments=[models.QzoneComment(uin=1, content="赞")],
                    ),
                    models.QzonePost(
                        uin=3,
                        tid="new",
                        name="朋友B",
                        text="今天去了书店",
                        create_time=12345,
                    ),
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_friend_feeds(self, *, pos=0, num=5, with_detail=False):
                return self.posts

            async def comment(self, post_id, content):
                self.comments.append((post_id, content))

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_comment": True,
                    "qzone_auto_comment_limit": 2,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                return "这家书店听起来好舒服"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_comment()

        self.assertEqual(result["commented"], 1)
        self.assertEqual(manager.plugin.qzone_service.comments, [("3:new", "这家书店听起来好舒服")])
        state = manager.db.state[module.QZONE_AUTO_COMMENT_STATE_KEY]
        self.assertEqual(state["processed"]["3:new"]["action"], "commented")
        self.assertEqual(state["processed"]["3:new"]["content"], "这家书店听起来好舒服")
        self.assertEqual(state["processed"]["3:new"]["author"], "朋友B")

    async def test_auto_comment_prioritizes_mention_posts(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.comments = []
                self.mention_calls = 0
                self.friend_calls = 0
                self.mention_posts = [
                    models.QzonePost(
                        uin=2,
                        tid="mention",
                        name="FRIEND_NICK",
                        text="周末去旧书店吗？@BOT_NICK",
                    ),
                ]
                self.posts = [
                    models.QzonePost(
                        uin=3,
                        tid="normal",
                        name="朋友B",
                        text="今天去了书店",
                    ),
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_mention_posts(self, *, offset=0, count=10, with_detail=True):
                self.mention_calls += 1
                return self.mention_posts

            async def query_friend_feeds(self, *, pos=0, num=5, with_detail=False):
                self.friend_calls += 1
                return self.posts

            async def comment(self, post_id, content):
                self.comments.append((post_id, content))

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_comment": True,
                    "qzone_auto_comment_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                return "去，记得给我留一杯热可可"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_comment()

        self.assertEqual(result["commented"], 1)
        self.assertEqual(manager.plugin.qzone_service.mention_calls, 1)
        self.assertEqual(manager.plugin.qzone_service.friend_calls, 1)
        self.assertEqual(
            manager.plugin.qzone_service.comments,
            [("2:mention", "去，记得给我留一杯热可可")],
        )
        state = manager.db.state[module.QZONE_AUTO_COMMENT_STATE_KEY]
        self.assertEqual(state["processed"]["2:mention"]["action"], "commented")
        self.assertNotIn("3:normal", state["processed"])

    async def test_auto_comment_send_failure_waits_until_next_run(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.attempts = 0
                self.comments = []
                self.posts = [
                    models.QzonePost(uin=3, tid="new", name="朋友B", text="今天去了书店"),
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_friend_feeds(self, *, pos=0, num=5, with_detail=False):
                return self.posts

            async def comment(self, post_id, content):
                self.attempts += 1
                if self.attempts == 1:
                    raise RuntimeError("temporary qzone error")
                self.comments.append((post_id, content))

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_comment": True,
                    "qzone_auto_comment_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                return "这家书店听起来好舒服"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        result = await manager.execute_qzone_auto_comment()

        self.assertEqual(result["commented"], 0)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["generation_failed"], 0)
        self.assertEqual(manager.plugin.qzone_service.attempts, 1)
        self.assertEqual(manager.plugin.qzone_service.comments, [])
        state = manager.db.state[module.QZONE_AUTO_COMMENT_STATE_KEY]
        self.assertNotIn("3:new", state["processed"])

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_comment()

        self.assertEqual(result["commented"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["generation_failed"], 0)
        self.assertEqual(manager.plugin.qzone_service.attempts, 2)
        self.assertEqual(manager.plugin.qzone_service.comments, [("3:new", "这家书店听起来好舒服")])
        state = manager.db.state[module.QZONE_AUTO_COMMENT_STATE_KEY]
        self.assertEqual(state["processed"]["3:new"]["action"], "commented")

    async def test_auto_comment_processed_alias_skips_changed_post_key(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.comments = []
                self.run = 0

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_recent_posts(self, *, pos=0, num=5, with_detail=False):
                self.run += 1
                return [
                    models.QzonePost(
                        uin=3,
                        tid="feed-key" if self.run == 1 else "detail-key",
                        curkey="stable-curkey",
                        unikey="stable-unikey",
                        name="朋友B",
                        text="今天去了展厅",
                        images=["https://example.com/gallery.jpg"],
                    )
                ]

            async def comment(self, post_id, content):
                self.comments.append((post_id, content))

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_comment": True,
                    "qzone_auto_comment_limit": 1,
                    "qzone_enable_auto_comment_image_vision": True,
                }
                self.db = FakeDb()
                self.prompts = []
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                    context=types.SimpleNamespace(),
                )

            async def llm(self, **kwargs):
                self.prompts.append(kwargs.get("prompt", ""))
                return "这张真不错"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            first = await manager.execute_qzone_auto_comment()
            second = await manager.execute_qzone_auto_comment()

        self.assertEqual(first["commented"], 1)
        self.assertEqual(second["commented"], 0)
        self.assertEqual(manager.plugin.qzone_service.comments, [("3:feed-key", "这张真不错")])
        self.assertEqual(len(manager.prompts), 1)
        state = manager.db.state[module.QZONE_AUTO_COMMENT_STATE_KEY]
        self.assertEqual(state["processed"]["3:feed-key"]["action"], "commented")
        self.assertEqual(state["processed"]["post:3:311:curkey:stable-curkey"]["action"], "commented")

    async def test_auto_comment_llm_failure_counts_generation_failure(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.comments = []
                self.posts = [
                    models.QzonePost(uin=3, tid="new", name="朋友B", text="今天去了书店"),
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_friend_feeds(self, *, pos=0, num=5, with_detail=False):
                return self.posts

            async def comment(self, post_id, content):
                self.comments.append((post_id, content))

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_comment": True,
                    "qzone_auto_comment_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                raise RuntimeError("llm timeout")

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        result = await manager.execute_qzone_auto_comment()

        self.assertEqual(result["commented"], 0)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["generation_failed"], 1)
        self.assertEqual(manager.plugin.qzone_service.comments, [])

    async def test_auto_like_likes_friend_post_candidates_directly(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.likes = []
                self.posts = [
                    models.QzonePost(uin=1, tid="self", name="我", text="自己的动态"),
                    models.QzonePost(uin=2, tid="sad", name="朋友A", text="今天生病了好难受"),
                    models.QzonePost(uin=3, tid="happy", name="朋友B", text="今天做的蛋糕成功了"),
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_friend_feeds(self, *, pos=0, num=5, with_detail=False):
                return self.posts

            async def like(self, post_id):
                self.likes.append(post_id)

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.llm_calls = 0
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_like": True,
                    "qzone_auto_like_limit": 2,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                self.llm_calls += 1
                raise AssertionError("auto like should not call llm")

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_like()

        self.assertEqual(result["liked"], 2)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(manager.llm_calls, 0)
        self.assertEqual(manager.plugin.qzone_service.likes, ["2:sad", "3:happy"])
        state = manager.db.state[module.QZONE_AUTO_LIKE_STATE_KEY]
        self.assertEqual(state["processed"]["2:sad"]["action"], "liked")
        self.assertEqual(state["processed"]["3:happy"]["action"], "liked")

    async def test_auto_like_processed_alias_skips_changed_post_key(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.likes = []
                self.run = 0

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_recent_posts(self, *, pos=0, num=5, with_detail=False):
                self.run += 1
                return [
                    models.QzonePost(
                        uin=3,
                        tid="feed-key" if self.run == 1 else "detail-key",
                        curkey="stable-curkey",
                        unikey="stable-unikey",
                        name="朋友B",
                        text="今天去了展厅",
                    )
                ]

            async def like(self, post_id):
                self.likes.append(post_id)

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_like": True,
                    "qzone_auto_like_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

        manager = Manager()

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            first = await manager.execute_qzone_auto_like()
            second = await manager.execute_qzone_auto_like()

        self.assertEqual(first["liked"], 1)
        self.assertEqual(second["liked"], 0)
        self.assertEqual(manager.plugin.qzone_service.likes, ["3:feed-key"])
        state = manager.db.state[module.QZONE_AUTO_LIKE_STATE_KEY]
        self.assertEqual(state["processed"]["3:feed-key"]["action"], "liked")
        self.assertEqual(state["processed"]["post:3:311:curkey:stable-curkey"]["action"], "liked")

    async def test_auto_like_does_not_call_llm(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.likes = []
                self.posts = [
                    models.QzonePost(uin=3, tid="friendly", name="朋友B", text="恬恬，我爱你！"),
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_friend_feeds(self, *, pos=0, num=5, with_detail=False):
                return self.posts

            async def like(self, post_id):
                self.likes.append(post_id)

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.llm_calls = 0
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_like": True,
                    "qzone_auto_like_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                self.llm_calls += 1
                return "skip"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_like()

        self.assertEqual(result["liked"], 1)
        self.assertEqual(manager.llm_calls, 0)
        self.assertEqual(manager.plugin.qzone_service.likes, ["3:friendly"])
        state = manager.db.state[module.QZONE_AUTO_LIKE_STATE_KEY]
        self.assertEqual(state["processed"]["3:friendly"]["action"], "liked")
        self.assertEqual(
            state["processed"]["3:friendly"]["policy_version"],
            module.QZONE_AUTO_LIKE_POLICY_VERSION,
        )

    async def test_auto_like_rechecks_old_skipped_state_after_policy_update(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.likes = []
                self.posts = [
                    models.QzonePost(uin=3, tid="old-skip", name="朋友B", text="今天整理了一下桌面"),
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_friend_feeds(self, *, pos=0, num=5, with_detail=False):
                return self.posts

            async def like(self, post_id):
                self.likes.append(post_id)

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.llm_calls = 0
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_like": True,
                    "qzone_auto_like_limit": 1,
                }
                self.db = FakeDb(
                    {
                        module.QZONE_AUTO_LIKE_STATE_KEY: {
                            "processed": {
                                "3:old-skip": {
                                    "at": 2_000_000_000,
                                    "action": "skipped",
                                    "policy_version": 2,
                                }
                            }
                        }
                    }
                )
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                raise AssertionError("auto like should not call llm")

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep), patch.object(module.time, "time", lambda: 2_000_000_100):
            result = await manager.execute_qzone_auto_like()

        self.assertEqual(result["liked"], 1)
        self.assertEqual(manager.plugin.qzone_service.likes, ["3:old-skip"])
        state = manager.db.state[module.QZONE_AUTO_LIKE_STATE_KEY]
        self.assertEqual(state["processed"]["3:old-skip"]["action"], "liked")
        self.assertEqual(
            state["processed"]["3:old-skip"]["policy_version"],
            module.QZONE_AUTO_LIKE_POLICY_VERSION,
        )

    async def test_auto_like_skips_already_liked_posts(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.likes = []
                self.posts = [
                    models.QzonePost(uin=3, tid="old", name="朋友B", text="今天做的蛋糕成功了", liked=True),
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_friend_feeds(self, *, pos=0, num=5, with_detail=False):
                return self.posts

            async def like(self, post_id):
                self.likes.append(post_id)

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.llm_calls = 0
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_like": True,
                    "qzone_auto_like_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                self.llm_calls += 1
                return "yes"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        result = await manager.execute_qzone_auto_like()

        self.assertEqual(result["liked"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(manager.llm_calls, 0)
        self.assertEqual(manager.plugin.qzone_service.likes, [])
        state = manager.db.state[module.QZONE_AUTO_LIKE_STATE_KEY]
        self.assertNotIn("3:old", state["processed"])

    async def test_auto_like_send_failure_waits_until_next_run(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.attempts = 0
                self.likes = []
                self.posts = [
                    models.QzonePost(uin=3, tid="happy", name="朋友B", text="今天做的蛋糕成功了"),
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_friend_feeds(self, *, pos=0, num=5, with_detail=False):
                return self.posts

            async def like(self, post_id):
                self.attempts += 1
                if self.attempts == 1:
                    raise RuntimeError("temporary qzone error")
                self.likes.append(post_id)

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_like": True,
                    "qzone_auto_like_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                return "yes"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        result = await manager.execute_qzone_auto_like()

        self.assertEqual(result["liked"], 0)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["generation_failed"], 0)
        self.assertEqual(manager.plugin.qzone_service.attempts, 1)
        state = manager.db.state[module.QZONE_AUTO_LIKE_STATE_KEY]
        self.assertNotIn("3:happy", state["processed"])

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_like()

        self.assertEqual(result["liked"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["generation_failed"], 0)
        self.assertEqual(manager.plugin.qzone_service.attempts, 2)
        self.assertEqual(manager.plugin.qzone_service.likes, ["3:happy"])
        state = manager.db.state[module.QZONE_AUTO_LIKE_STATE_KEY]
        self.assertEqual(state["processed"]["3:happy"]["action"], "liked")

    async def test_execute_replies_to_new_comments_on_self_posts(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.replies = []
                self.posts = [
                    models.QzonePost(
                        uin=1,
                        tid="self",
                        name="我",
                        text="今天很开心",
                        comments=[
                            models.QzoneComment(uin=2, nickname="Alice", content="真不错", tid="c1"),
                            models.QzoneComment(uin=1, nickname="Me", content="自己的评论", tid="mine"),
                            models.QzoneComment(uin=3, nickname="Bob", content="已回复", tid="c2"),
                            models.QzoneComment(uin=1, nickname="Me", content="谢谢", tid="r2", parent_tid="c2"),
                        ],
                    ),
                    models.QzonePost(
                        uin=9,
                        tid="friend",
                        name="朋友",
                        text="朋友动态",
                        comments=[models.QzoneComment(uin=2, nickname="Alice", content="路过", tid="c3")],
                    ),
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
                return self.posts

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.replies.append((post_id, comment.tid, content))

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_reply": True,
                    "qzone_auto_reply_limit": 2,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                return "谢谢你呀"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_reply()

        self.assertEqual(result["replied"], 1)
        self.assertEqual(manager.plugin.qzone_service.replies, [("1:self", "c1", "谢谢你呀")])
        state = manager.db.state[module.QZONE_AUTO_REPLY_STATE_KEY]
        self.assertEqual(state["processed"]["1:self:c1"]["action"], "replied")

    async def test_auto_reply_send_failure_waits_until_next_run(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.attempts = 0
                self.replies = []
                self.posts = [
                    models.QzonePost(
                        uin=1,
                        tid="self",
                        name="我",
                        text="今天很开心",
                        comments=[
                            models.QzoneComment(uin=2, nickname="Alice", content="真不错", tid="c1"),
                        ],
                    )
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
                return self.posts

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.attempts += 1
                if self.attempts == 1:
                    raise RuntimeError("temporary qzone error")
                self.replies.append((post_id, comment.tid, content))

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_reply": True,
                    "qzone_auto_reply_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                return "谢谢你呀"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        result = await manager.execute_qzone_auto_reply()

        self.assertEqual(result["replied"], 0)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["generation_failed"], 0)
        self.assertEqual(manager.plugin.qzone_service.attempts, 1)
        self.assertEqual(manager.plugin.qzone_service.replies, [])
        state = manager.db.state[module.QZONE_AUTO_REPLY_STATE_KEY]
        self.assertNotIn("1:self:c1", state["processed"])

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_reply()

        self.assertEqual(result["replied"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["generation_failed"], 0)
        self.assertEqual(manager.plugin.qzone_service.attempts, 2)
        self.assertEqual(manager.plugin.qzone_service.replies, [("1:self", "c1", "谢谢你呀")])
        state = manager.db.state[module.QZONE_AUTO_REPLY_STATE_KEY]
        self.assertEqual(state["processed"]["1:self:c1"]["action"], "replied")

    async def test_auto_reply_rate_limit_reuses_reply_on_next_run(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.attempts = 0
                self.replies = []
                self.posts = [
                    models.QzonePost(
                        uin=1,
                        tid="self",
                        name="我",
                        text="今天很开心",
                        comments=[
                            models.QzoneComment(uin=2, nickname="Alice", content="真不错", tid="c1"),
                        ],
                    )
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
                return self.posts

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.attempts += 1
                if self.attempts == 1:
                    raise RuntimeError("使用人数过多，请稍后再试")
                self.replies.append((post_id, comment.tid, content))

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_reply": True,
                    "qzone_auto_reply_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )
                self.llm_calls = 0

            async def llm(self, **kwargs):
                self.llm_calls += 1
                return "谢谢你呀"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        first = await manager.execute_qzone_auto_reply()

        self.assertEqual(first["replied"], 0)
        self.assertEqual(first["failed"], 0)
        self.assertEqual(first["skipped"], 1)
        self.assertEqual(manager.llm_calls, 1)
        state = manager.db.state[module.QZONE_AUTO_REPLY_STATE_KEY]
        self.assertNotIn("rate_limited_until", state)
        self.assertNotIn("rate_limited_reason", state)
        self.assertEqual(state["processed"]["1:self:c1"]["action"], "retry_later")
        self.assertEqual(state["processed"]["1:self:c1"]["content"], "谢谢你呀")

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            second = await manager.execute_qzone_auto_reply()

        self.assertEqual(second["replied"], 1)
        self.assertEqual(second["failed"], 0)
        self.assertEqual(manager.llm_calls, 1)
        self.assertEqual(manager.plugin.qzone_service.replies, [("1:self", "c1", "谢谢你呀")])
        state = manager.db.state[module.QZONE_AUTO_REPLY_STATE_KEY]
        self.assertEqual(state["processed"]["1:self:c1"]["action"], "replied")

    async def test_auto_reply_deleted_message_waits_until_next_run(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.attempts = 0
                self.replies = []
                self.posts = [
                    models.QzonePost(
                        uin=1,
                        tid="self",
                        name="我",
                        text="今天很开心",
                        comments=[
                            models.QzoneComment(uin=2, nickname="Alice", content="真不错", tid="c1"),
                        ],
                    )
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
                return self.posts

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.attempts += 1
                if self.attempts == 1:
                    raise RuntimeError("该条内容已被删除")
                self.replies.append((post_id, comment.tid, content))

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_reply": True,
                    "qzone_auto_reply_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )
                self.llm_calls = 0

            async def llm(self, **kwargs):
                self.llm_calls += 1
                return "谢谢你呀"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        first = await manager.execute_qzone_auto_reply()

        self.assertEqual(first["replied"], 0)
        self.assertEqual(first["failed"], 0)
        self.assertEqual(first["skipped"], 1)
        self.assertEqual(manager.llm_calls, 1)
        state = manager.db.state[module.QZONE_AUTO_REPLY_STATE_KEY]
        self.assertEqual(state["processed"]["1:self:c1"]["action"], "skipped")
        self.assertEqual(state["processed"]["1:self:c1"]["content"], "谢谢你呀")
        self.assertEqual(state["processed"]["1:self:c1"]["reason"], "该条内容已被删除")
        self.assertEqual(state["processed"]["1:self:c1"]["attempted_targets"], [])
        self.assertEqual(state["processed"]["1:self:c1"]["attempts"], [])

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            second = await manager.execute_qzone_auto_reply()

        self.assertEqual(second["replied"], 0)
        self.assertEqual(second["failed"], 0)
        self.assertEqual(second["skipped"], 1)
        self.assertEqual(manager.llm_calls, 1)
        self.assertEqual(manager.plugin.qzone_service.attempts, 1)
        self.assertEqual(manager.plugin.qzone_service.replies, [])

    async def test_execute_replies_to_second_level_reply_on_self_post(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.replies = []
                self.posts = [
                    models.QzonePost(
                        uin=1,
                        tid="self",
                        name="我",
                        text="今天很开心",
                        comments=[
                            models.QzoneComment(uin=2, nickname="Alice", content="真不错", tid="c1", create_time=1),
                            models.QzoneComment(uin=1, nickname="Me", content="谢谢你呀", tid="r1", parent_tid="c1", create_time=2),
                            models.QzoneComment(uin=2, nickname="Alice", content="哈哈我也觉得", tid="r2", parent_tid="c1", create_time=3),
                            models.QzoneComment(uin=3, nickname="Bob", content="我插一句", tid="c2", create_time=4),
                            models.QzoneComment(uin=4, nickname="Carol", content="确实", tid="r3", parent_tid="c2", create_time=5),
                            models.QzoneComment(uin=5, nickname="Dan", content="已回复楼", tid="c3", create_time=6),
                            models.QzoneComment(uin=5, nickname="Dan", content="再说一句", tid="r4", parent_tid="c3", create_time=7),
                            models.QzoneComment(uin=1, nickname="Me", content="我看到了", tid="r5", parent_tid="c3", create_time=8),
                        ],
                    )
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
                return self.posts

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.replies.append((post_id, comment.tid, content))

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_reply": True,
                    "qzone_auto_reply_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                return "哈哈是呀"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_reply()

        self.assertEqual(result["replied"], 1)
        self.assertEqual(manager.plugin.qzone_service.replies, [("1:self", "r2", "哈哈是呀")])
        state = manager.db.state[module.QZONE_AUTO_REPLY_STATE_KEY]
        self.assertEqual(state["processed"]["1:self:r2"]["action"], "thread_replied")

    async def test_execute_prefers_latest_thread_reply_over_first_comment(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.replies = []
                self.posts = [
                    models.QzonePost(
                        uin=1,
                        tid="self",
                        name="我",
                        text="今天很开心",
                        comments=[
                            models.QzoneComment(uin=2, nickname="Alice", content="第一条老评论", tid="c1", create_time=1),
                            models.QzoneComment(uin=3, nickname="Bob", content="另一楼", tid="c2", create_time=2),
                            models.QzoneComment(uin=1, nickname="Me", content="先回一下", tid="r1", parent_tid="c2", create_time=3),
                            models.QzoneComment(
                                uin=3,
                                nickname="Bob",
                                content="@{uin:1,nick:Me,auto:1} 最新三级",
                                tid="r2",
                                parent_tid="c2",
                                create_time=4,
                            ),
                        ],
                    )
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
                return self.posts

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.replies.append((post_id, comment.tid, content, parent_comment.tid if parent_comment else ""))

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_reply": True,
                    "qzone_auto_reply_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                return "接住了"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_reply()

        self.assertEqual(result["replied"], 1)
        self.assertEqual(manager.plugin.qzone_service.replies, [("1:self", "r2", "接住了", "c2")])
        state = manager.db.state[module.QZONE_AUTO_REPLY_STATE_KEY]
        self.assertEqual(state["processed"]["1:self:r2"]["action"], "thread_replied")

    async def test_execute_detects_third_level_reply_without_parent_tid(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.replies = []
                self.posts = [
                    models.QzonePost(
                        uin=1,
                        tid="self",
                        name="我",
                        text="今天很开心",
                        comments=[
                            models.QzoneComment(uin=2, nickname="Alice", content="第一条老评论", tid="c1", create_time=1),
                            models.QzoneComment(uin=3, nickname="Bob", content="另一楼", tid="c2", create_time=2),
                            models.QzoneComment(uin=1, nickname="Me", content="先回一下", tid="r1", parent_tid="c2", create_time=3),
                            models.QzoneComment(
                                uin=3,
                                nickname="Bob",
                                content="最新三级",
                                tid="r2",
                                reply_to_tid="r1",
                                create_time=4,
                            ),
                        ],
                    )
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
                return self.posts

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.replies.append((post_id, comment.tid, content, parent_comment.tid if parent_comment else ""))

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_reply": True,
                    "qzone_auto_reply_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                return "接住了"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_reply()

        self.assertEqual(result["replied"], 1)
        self.assertEqual(manager.plugin.qzone_service.replies, [("1:self", "r2", "接住了", "c2")])
        state = manager.db.state[module.QZONE_AUTO_REPLY_STATE_KEY]
        self.assertEqual(state["processed"]["1:self:r2"]["action"], "thread_replied")

    async def test_execute_replies_to_parent_comment_without_prior_thread_reply(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.replies = []
                self.posts = [
                    models.QzonePost(
                        uin=1,
                        tid="self",
                        name="我",
                        text="今天很开心",
                        comments=[
                            models.QzoneComment(uin=2, nickname="Alice", content="真不错", tid="c1", create_time=1),
                            models.QzoneComment(uin=3, nickname="Bob", content="我也觉得", tid="r1", parent_tid="c1", create_time=2),
                        ],
                    )
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
                return self.posts

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.replies.append((post_id, comment.tid, content, parent_comment.tid if parent_comment else ""))

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_reply": True,
                    "qzone_auto_reply_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                return "确实挺开心"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_reply()

        self.assertEqual(result["replied"], 1)
        self.assertEqual(manager.plugin.qzone_service.replies, [("1:self", "c1", "确实挺开心", "")])
        state = manager.db.state[module.QZONE_AUTO_REPLY_STATE_KEY]
        self.assertEqual(state["processed"]["1:self:c1"]["action"], "replied")

    async def test_execute_replies_to_second_level_reply_when_qzone_returns_reverse_order(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.replies = []
                self.posts = [
                    models.QzonePost(
                        uin=1,
                        tid="self",
                        name="我",
                        text="今天很开心",
                        comments=[
                            models.QzoneComment(uin=2, nickname="Alice", content="真不错", tid="c1"),
                            models.QzoneComment(uin=2, nickname="Alice", content="哈哈我也觉得", tid="r2", parent_tid="c1"),
                            models.QzoneComment(uin=1, nickname="Me", content="谢谢你呀", tid="r1", parent_tid="c1"),
                        ],
                    )
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
                return self.posts

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.replies.append((post_id, comment.tid, content))

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_reply": True,
                    "qzone_auto_reply_limit": 1,
                }
                self.db = FakeDb(
                    {
                        module.QZONE_AUTO_REPLY_STATE_KEY: {
                            "processed": {
                                "1:self:c1": {
                                    "at": int(module.time.time()),
                                    "action": "replied",
                                    "content": "谢谢你呀",
                                    "commenter": "Alice",
                                }
                            }
                        }
                    }
                )
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                return "哈哈是呀"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_reply()

        self.assertEqual(result["replied"], 1)
        self.assertEqual(manager.plugin.qzone_service.replies, [("1:self", "r2", "哈哈是呀")])
        state = manager.db.state[module.QZONE_AUTO_REPLY_STATE_KEY]
        self.assertEqual(state["processed"]["1:self:r2"]["action"], "thread_replied")

    async def test_execute_replies_to_thread_reply_with_same_timestamp_as_self_reply(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.replies = []
                self.posts = [
                    models.QzonePost(
                        uin=1,
                        tid="self",
                        name="Me",
                        text="post",
                        comments=[
                            models.QzoneComment(uin=2, nickname="Alice", content="first", tid="c1", create_time=100),
                            models.QzoneComment(uin=1, nickname="Me", content="reply 1", tid="r1", parent_tid="c1", create_time=200),
                            models.QzoneComment(uin=2, nickname="Alice", content="second", tid="r2", parent_tid="c1", create_time=300),
                            models.QzoneComment(uin=1, nickname="Me", content="reply 2", tid="r3", parent_tid="c1", create_time=400),
                            models.QzoneComment(uin=2, nickname="Alice", content="third", tid="r4", parent_tid="c1", create_time=400),
                        ],
                    )
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
                return self.posts

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.replies.append((post_id, comment.tid, content, parent_comment.tid if parent_comment else ""))

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_reply": True,
                    "qzone_auto_reply_limit": 1,
                }
                self.db = FakeDb(
                    {
                        module.QZONE_AUTO_REPLY_STATE_KEY: {
                            "processed": {
                                "1:self:c1": {
                                    "at": int(module.time.time()),
                                    "action": "replied",
                                    "content": "reply 1",
                                },
                                "1:self:r2": {
                                    "at": int(module.time.time()),
                                    "action": "thread_replied",
                                    "parent_comment_id": "c1",
                                    "content": "reply 2",
                                },
                            }
                        }
                    }
                )
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                return "reply 3"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_reply()

        self.assertEqual(result["replied"], 1)
        self.assertEqual(manager.plugin.qzone_service.replies, [("1:self", "r4", "reply 3", "c1")])
        state = manager.db.state[module.QZONE_AUTO_REPLY_STATE_KEY]
        self.assertEqual(state["processed"]["1:self:r4"]["action"], "thread_replied")

    async def test_execute_does_not_mark_thread_replied_when_reply_lands_on_wrong_floor(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.replies = []
                self.posts = [
                    models.QzonePost(
                        uin=1,
                        tid="self",
                        name="Me",
                        text="post",
                        comments=[
                            models.QzoneComment(uin=2, nickname="Alice", content="first", tid="c1", create_time=100),
                            models.QzoneComment(
                                uin=1,
                                nickname="Me",
                                content="reply 1",
                                tid="r1",
                                parent_tid="c1",
                                reply_to_tid="c1",
                                reply_to_uin=2,
                                create_time=200,
                            ),
                            models.QzoneComment(
                                uin=2,
                                nickname="Alice",
                                content="second",
                                tid="r2",
                                submit_tid="2",
                                parent_tid="c1",
                                reply_to_tid="r1",
                                reply_to_uin=1,
                                create_time=300,
                            ),
                        ],
                    )
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
                return self.posts

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.replies.append((post_id, comment.tid, content, parent_comment.tid if parent_comment else ""))
                exc = RuntimeError("placement verification failed")
                setattr(exc, "reply_verification_failed", True)
                setattr(exc, "attempted_targets", [{"comment_id": comment.tid, "comment_uin": comment.uin}])
                setattr(exc, "attempts", [{"verification_status": "parent_target"}])
                setattr(exc, "verification_status", "parent_target")
                setattr(exc, "verified_reply_tid", "r3")
                setattr(exc, "verified_reply_to_tid", "c1")
                setattr(exc, "verified_reply_to_uin", 2)
                setattr(exc, "verification_candidates", [{"tid": "r3", "target_status": "parent"}])
                raise exc

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_reply": True,
                    "qzone_auto_reply_limit": 1,
                }
                self.db = FakeDb(
                    {
                        module.QZONE_AUTO_REPLY_STATE_KEY: {
                            "processed": {
                                "1:self:c1": {
                                    "at": int(module.time.time()),
                                    "action": "replied",
                                    "content": "reply 1",
                                }
                            }
                        }
                    }
                )
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                return "reply 2"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_reply()

        self.assertEqual(result["replied"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(manager.plugin.qzone_service.replies, [("1:self", "r2", "reply 2", "c1")])
        state = manager.db.state[module.QZONE_AUTO_REPLY_STATE_KEY]
        item = state["processed"]["1:self:r2"]
        self.assertEqual(item["action"], "skipped")
        self.assertEqual(item["verification_status"], "parent_target")
        self.assertEqual(item["verified_reply_to_tid"], "c1")
        self.assertNotEqual(item["action"], "thread_replied")

    async def test_execute_skips_unsafe_synthetic_thread_reply_before_llm(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.replies = []
                self.posts = [
                    models.QzonePost(
                        uin=1,
                        tid="self",
                        name="Me",
                        text="post",
                        comments=[
                            models.QzoneComment(
                                uin=2,
                                nickname="Friend",
                                content="出门了吗",
                                tid="6",
                                submit_tid="6",
                                raw_tid="6",
                                create_time=100,
                            ),
                            models.QzoneComment(
                                uin=1,
                                nickname="Me",
                                content="马上",
                                tid="6_r_1_1",
                                submit_tid="1",
                                raw_tid="1",
                                parent_tid="6",
                                reply_to_tid="6",
                                raw_reply_to_tid="6",
                                reply_to_uin=2,
                                raw_reply_to_uin=2,
                                create_time=200,
                            ),
                            models.QzoneComment(
                                uin=2,
                                nickname="Friend",
                                content="@{uin:1,nick:Me,auto:1} 哈哈",
                                tid="6_r_2_2",
                                submit_tid="2",
                                raw_tid="2",
                                parent_tid="6",
                                reply_to_tid="6_r_1_1",
                                raw_reply_to_tid="1",
                                reply_to_uin=1,
                                raw_reply_to_uin=1,
                                create_time=300,
                            ),
                        ],
                    )
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
                return self.posts

            def unsafe_thread_reply_target_reason(self, comment, *, parent_comment=None):
                return "synthetic_thread_tid_without_real_submit_id"

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.replies.append((post_id, comment.tid, content))

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.llm_calls = 0
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_reply": True,
                    "qzone_auto_reply_limit": 1,
                }
                self.db = FakeDb(
                    {
                        module.QZONE_AUTO_REPLY_STATE_KEY: {
                            "processed": {
                                "1:self:6": {
                                    "at": int(module.time.time()),
                                    "action": "replied",
                                    "content": "马上",
                                }
                            }
                        }
                    }
                )
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                self.llm_calls += 1
                return "不该生成"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_reply()

        self.assertEqual(result["replied"], 0)
        self.assertEqual(result["skipped"], 3)
        self.assertEqual(manager.llm_calls, 0)
        self.assertEqual(manager.plugin.qzone_service.replies, [])

    async def test_execute_replies_to_new_thread_reply_with_reused_short_id(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.replies = []
                self.posts = [
                    models.QzonePost(
                        uin=1,
                        tid="self",
                        name="Me",
                        text="post",
                        comments=[
                            models.QzoneComment(uin=2, nickname="Friend", content="你好会享受啊", tid="11", create_time=100),
                            models.QzoneComment(
                                uin=1,
                                nickname="Me",
                                content="这叫劳逸结合，懂？",
                                tid="11_r_1_1",
                                submit_tid="1",
                                parent_tid="11",
                                reply_to_tid="11",
                                reply_to_uin=2,
                                create_time=200,
                            ),
                            models.QzoneComment(
                                uin=2,
                                nickname="Friend",
                                content="啊对对对，就你懂！",
                                tid="11_r_1_2",
                                submit_tid="1",
                                parent_tid="11",
                                reply_to_tid="11_r_1_1",
                                reply_to_uin=1,
                                create_time=300,
                            ),
                        ],
                    )
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
                return self.posts

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.replies.append((post_id, comment.tid, getattr(comment, "submit_tid", ""), content))
                return {
                    "comment_id": str(getattr(comment, "submit_tid", "") or getattr(comment, "tid", "") or ""),
                    "comment_uin": int(getattr(comment, "uin", 0) or 0),
                    "transport": "pc",
                    "attempted_targets": [
                        {"comment_id": "1", "comment_uin": 2},
                        {"comment_id": "11_r_1_2", "comment_uin": 2},
                        {"comment_id": "11", "comment_uin": 2},
                    ],
                }

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_reply": True,
                    "qzone_auto_reply_limit": 1,
                }
                self.db = FakeDb(
                    {
                        module.QZONE_AUTO_REPLY_STATE_KEY: {
                            "processed": {
                                "1:self:11": {
                                    "at": int(module.time.time()),
                                    "action": "replied",
                                    "content": "这叫劳逸结合，懂？",
                                }
                            }
                        }
                    }
                )
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                return "就你懂得捧场"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_reply()

        self.assertEqual(result["replied"], 1)
        self.assertEqual(manager.plugin.qzone_service.replies, [("1:self", "11_r_1_2", "1", "就你懂得捧场")])
        state = manager.db.state[module.QZONE_AUTO_REPLY_STATE_KEY]
        self.assertEqual(state["processed"]["1:self:11_r_1_2"]["action"], "thread_replied")
        self.assertEqual(state["processed"]["1:self:11_r_1_2"]["submitted_comment_id"], "1")
        self.assertEqual(state["processed"]["1:self:11_r_1_2"]["submitted_transport"], "pc")
        self.assertEqual(
            state["processed"]["1:self:11_r_1_2"]["attempted_targets"],
            [
                {"comment_id": "1", "comment_uin": 2},
                {"comment_id": "11_r_1_2", "comment_uin": 2},
                {"comment_id": "11", "comment_uin": 2},
            ],
        )

    async def test_execute_replies_to_top_level_comment_with_post_parent_tid(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.replies = []
                self.posts = [
                    models.QzonePost(
                        uin=1,
                        tid="self",
                        name="Me",
                        text="post",
                        comments=[
                            models.QzoneComment(uin=2, nickname="Alice", content="new", tid="c1", parent_tid="self"),
                        ],
                    )
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
                return self.posts

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.replies.append((post_id, comment.tid, content, parent_comment))

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_reply": True,
                    "qzone_auto_reply_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                return "reply"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_reply()

        self.assertEqual(result["replied"], 1)
        self.assertEqual(manager.plugin.qzone_service.replies, [("1:self", "c1", "reply", None)])

    async def test_execute_auto_reply_uses_merged_thread_reply_after_detail_merge(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.replies = []
                self.posts = [
                    models.QzonePost(
                        uin=1,
                        tid="self",
                        name="我",
                        text="今天很开心",
                        comments=[
                            models.QzoneComment(uin=2, nickname="Alice", content="真不错", tid="c1", create_time=1),
                            models.QzoneComment(uin=1, nickname="Me", content="谢谢你呀", tid="r1", parent_tid="c1", create_time=2),
                            models.QzoneComment(uin=2, nickname="Alice", content="哈哈我也觉得", tid="r2", parent_tid="c1", create_time=3),
                        ],
                    )
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
                return self.posts

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.replies.append((post_id, comment.tid, content, parent_comment.tid if parent_comment else ""))

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_reply": True,
                    "qzone_auto_reply_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                return "哈哈是呀"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_reply()

        self.assertEqual(result["replied"], 1)
        self.assertEqual(manager.plugin.qzone_service.replies, [("1:self", "r2", "哈哈是呀", "c1")])

    async def test_execute_auto_comment_continues_friend_thread_under_bot_comment(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.recent_calls = 0
                self.top_comments = []
                self.replies = []
                self.recent_posts = [
                    models.QzonePost(
                        uin=2,
                        tid="friend",
                        name="Friend",
                        text="今天去了书店",
                        comments=[
                            models.QzoneComment(
                                uin=1,
                                nickname="Me",
                                content="这家书店听起来好舒服",
                                tid="c1",
                                create_time=100,
                            ),
                            models.QzoneComment(
                                uin=2,
                                nickname="Friend",
                                content="下次一起去",
                                tid="r1",
                                parent_tid="c1",
                                reply_to_tid="c1",
                                reply_to_uin=1,
                                create_time=200,
                            ),
                        ],
                    )
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_recent_posts(self, *, pos=0, num=5, with_detail=False):
                self.recent_calls += 1
                return self.recent_posts

            async def comment(self, post_id, content):
                self.top_comments.append((post_id, content))

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.recent_posts[0].comments.append(
                    models.QzoneComment(
                        uin=1,
                        nickname="Me",
                        content=content,
                        tid="self-r1",
                        parent_tid=parent_comment.tid if parent_comment else "",
                        reply_to_tid=comment.tid,
                        reply_to_uin=comment.uin,
                        create_time=300,
                    )
                )
                self.replies.append((post_id, comment.tid, content, parent_comment.tid if parent_comment else ""))
                return {"comment_id": "self-r1", "comment_uin": 1, "transport": "addreply_ugc"}

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_comment": True,
                    "qzone_auto_comment_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                return "行，下次一起去"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_comment()

        self.assertEqual(result["scanned"], 1)
        self.assertEqual(result["commented"], 1)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(manager.plugin.qzone_service.recent_calls, 1)
        self.assertEqual(manager.plugin.qzone_service.top_comments, [])
        self.assertEqual(manager.plugin.qzone_service.replies, [("2:friend", "r1", "行，下次一起去", "c1")])
        state = manager.db.state[module.QZONE_AUTO_COMMENT_STATE_KEY]
        self.assertEqual(state["processed"]["2:friend:r1"]["action"], "thread_commented")
        self.assertEqual(state["processed"]["2:friend:r1"]["parent_comment_id"], "c1")

    async def test_execute_auto_comment_does_not_top_comment_same_post_after_thread_reply(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.recent_calls = 0
                self.top_comments = []
                self.replies = []
                self.recent_posts = [
                    models.QzonePost(
                        uin=2,
                        tid="friend",
                        name="Friend",
                        text="今天去了展厅",
                        images=["https://example.com/gallery.jpg"],
                        comments=[
                            models.QzoneComment(
                                uin=1,
                                nickname="Me",
                                content="这张很文艺",
                                tid="c1",
                                create_time=100,
                            ),
                            models.QzoneComment(
                                uin=2,
                                nickname="Friend",
                                content="下次一起去",
                                tid="r1",
                                parent_tid="c1",
                                reply_to_tid="c1",
                                reply_to_uin=1,
                                create_time=200,
                            ),
                        ],
                    )
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_recent_posts(self, *, pos=0, num=5, with_detail=False):
                self.recent_calls += 1
                return self.recent_posts

            async def comment(self, post_id, content):
                self.top_comments.append((post_id, content))

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.replies.append((post_id, comment.tid, content, parent_comment.tid if parent_comment else ""))
                return {"comment_id": "self-r1", "comment_uin": 1, "transport": "addreply_ugc"}

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_comment": True,
                    "qzone_auto_comment_limit": 2,
                    "qzone_enable_auto_comment_image_vision": True,
                }
                self.db = FakeDb()
                self.prompts = []
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                    context=types.SimpleNamespace(),
                )

            async def llm(self, **kwargs):
                self.prompts.append(kwargs.get("prompt", ""))
                return "行，下次一起去"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_comment()

        self.assertEqual(result["commented"], 1)
        self.assertEqual(manager.plugin.qzone_service.top_comments, [])
        self.assertEqual(manager.plugin.qzone_service.replies, [("2:friend", "r1", "行，下次一起去", "c1")])
        self.assertEqual(len(manager.prompts), 1)
        self.assertNotIn("【配图识别】", manager.prompts[0])

    async def test_execute_auto_comment_merges_stale_mention_with_recent_detail(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.top_comments = []
                self.replies = []
                self.mention_post = models.QzonePost(
                    uin=2,
                    tid="friend",
                    name="Friend",
                    text="今天去了展厅",
                    images=["https://example.com/gallery.jpg?stale=1"],
                    comments=[
                        models.QzoneComment(
                            uin=2,
                            nickname="Friend",
                            content="原来是编的吗？",
                            tid="deleted-r0",
                            parent_tid="c1",
                            reply_to_tid="c1",
                            reply_to_uin=1,
                            create_time=150,
                        )
                    ],
                )
                self.recent_post = models.QzonePost(
                    uin=2,
                    tid="friend",
                    name="Friend",
                    text="今天去了展厅",
                    images=["https://example.com/gallery.jpg?fresh=1"],
                    comments=[
                        models.QzoneComment(
                            uin=1,
                            nickname="Me",
                            content="高马尾加蓝色画作，文艺浓度直接超标了",
                            tid="c1",
                            create_time=100,
                        ),
                        models.QzoneComment(
                            uin=2,
                            nickname="Friend",
                            content="还有码？",
                            tid="r1",
                            parent_tid="c1",
                            reply_to_tid="c1",
                            reply_to_uin=1,
                            create_time=200,
                        ),
                    ],
                )

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_mention_posts(self, *, offset=0, count=5, with_detail=False):
                return [self.mention_post]

            async def query_recent_posts(self, *, pos=0, num=5, with_detail=False):
                return [self.recent_post]

            async def comment(self, post_id, content):
                self.top_comments.append((post_id, content))

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.replies.append((post_id, comment.tid, content, parent_comment.tid if parent_comment else ""))
                return {"comment_id": "self-r1", "comment_uin": 1, "transport": "addreply_ugc"}

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_comment": True,
                    "qzone_auto_comment_limit": 2,
                    "qzone_enable_auto_comment_image_vision": True,
                }
                self.db = FakeDb()
                self.prompts = []
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                    context=types.SimpleNamespace(),
                )

            async def llm(self, **kwargs):
                self.prompts.append(kwargs.get("prompt", ""))
                return "有，艺术加工那种码"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_comment()

        service = manager.plugin.qzone_service
        self.assertEqual(result["commented"], 1)
        self.assertEqual(service.top_comments, [])
        self.assertEqual(service.replies, [("2:friend", "r1", "有，艺术加工那种码", "c1")])
        self.assertEqual(len(manager.prompts), 1)
        self.assertNotIn("【配图识别】", manager.prompts[0])

    async def test_execute_auto_comment_continues_latest_friend_thread_reply(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.recent_calls = 0
                self.top_comments = []
                self.replies = []
                self.recent_posts = [
                    models.QzonePost(
                        uin=2,
                        tid="friend",
                        name="Friend",
                        text="今天去了书店",
                        comments=[
                            models.QzoneComment(
                                uin=1,
                                nickname="Me",
                                content="这家书店听起来好舒服",
                                tid="c1",
                                create_time=100,
                            ),
                            models.QzoneComment(
                                uin=2,
                                nickname="Friend",
                                content="下次一起去",
                                tid="r1",
                                parent_tid="c1",
                                reply_to_tid="c1",
                                reply_to_uin=1,
                                create_time=200,
                            ),
                            models.QzoneComment(
                                uin=2,
                                nickname="Friend",
                                content="我刚买了票",
                                tid="r2",
                                parent_tid="c1",
                                reply_to_tid="c1",
                                reply_to_uin=1,
                                create_time=300,
                            ),
                        ],
                    )
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_recent_posts(self, *, pos=0, num=5, with_detail=False):
                self.recent_calls += 1
                return self.recent_posts

            async def comment(self, post_id, content):
                self.top_comments.append((post_id, content))

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.recent_posts[0].comments.append(
                    models.QzoneComment(
                        uin=1,
                        nickname="Me",
                        content=content,
                        tid="self-r2",
                        parent_tid=parent_comment.tid if parent_comment else "",
                        reply_to_tid=comment.tid,
                        reply_to_uin=comment.uin,
                        create_time=400,
                    )
                )
                self.replies.append((post_id, comment.tid, content, parent_comment.tid if parent_comment else ""))
                return {"comment_id": "self-r2", "comment_uin": 1, "transport": "addreply_ugc"}

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_comment": True,
                    "qzone_auto_comment_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )
                self.prompts = []

            async def llm(self, **kwargs):
                prompt = str(kwargs.get("prompt") or "")
                self.prompts.append(prompt)
                return "那到时候门口见"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_comment()

        service = manager.plugin.qzone_service
        self.assertEqual(result["scanned"], 1)
        self.assertEqual(result["commented"], 1)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(len(manager.prompts), 1)
        self.assertIn("我刚买了票", manager.prompts[0])
        self.assertEqual(service.recent_calls, 1)
        self.assertEqual(service.top_comments, [])
        self.assertEqual(service.replies, [("2:friend", "r2", "那到时候门口见", "c1")])
        state = manager.db.state[module.QZONE_AUTO_COMMENT_STATE_KEY]
        self.assertEqual(state["processed"]["2:friend:r2"]["action"], "thread_commented")

    async def test_execute_auto_comment_continues_friend_thread_with_colliding_short_id(self):
        module, models = _load_auto_comment_module()
        service_module, _service_models = _load_qzone_service_module()

        class Service:
            def __init__(self):
                self.recent_calls = 0
                self.replies = []
                self.recent_posts = [
                    models.QzonePost(
                        uin=89761500,
                        tid="dca659054aad3c6a8d8e0600",
                        name="四次元未来",
                        text="嘿嘿，我喜欢你！",
                        comments=[
                            models.QzoneComment(
                                uin=188852752,
                                nickname="Me",
                                content="大中午的抽什么风",
                                tid="1",
                                submit_tid="1",
                                raw_tid="1",
                                create_time=1782361485,
                            ),
                            models.QzoneComment(
                                uin=89761500,
                                nickname="四次元未来",
                                content="@{uin:188852752,nick:Me,who:1,auto:1}输给你了",
                                tid="1_r_1_89761500",
                                submit_tid="1",
                                raw_tid="1",
                                parent_tid="1",
                                reply_to_tid="1",
                                raw_reply_to_tid="1",
                                reply_to_uin=188852752,
                                raw_reply_to_uin=188852752,
                                create_time=1782361510,
                            ),
                        ],
                    )
                ]

            async def context(self):
                return types.SimpleNamespace(uin=188852752)

            async def query_recent_posts(self, *, pos=0, num=5, with_detail=False):
                self.recent_calls += 1
                return self.recent_posts

            async def comment(self, post_id, content):
                raise AssertionError("thread continuation should not post a top-level comment")

            def _reply_submit_targets(self, post, comment, *, parent_comment=None):
                return [
                    {
                        "comment_id": str(getattr(comment, "tid", "") or ""),
                        "comment_uin": int(getattr(comment, "uin", 0) or 0),
                    },
                    {
                        "comment_id": str(getattr(comment, "submit_tid", "") or ""),
                        "comment_uin": int(getattr(comment, "uin", 0) or 0),
                    },
                ]

            def _filter_thread_reply_targets(self, post, comment, *, parent_comment=None, targets=None):
                return service_module.QzoneService._filter_thread_reply_targets(
                    post,
                    comment,
                    parent_comment=parent_comment,
                    targets=targets,
                )

            def _thread_reply_payload_variants(self, post, comment, parent_comment, targets):
                return service_module.QzoneService._thread_reply_payload_variants(post, comment, parent_comment, targets)

            def unsafe_thread_reply_target_reason(self, comment, *, parent_comment=None):
                return service_module.QzoneService.unsafe_thread_reply_target_reason(
                    comment,
                    parent_comment=parent_comment,
                )

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.replies.append(
                    (
                        post_id,
                        comment.tid,
                        comment.submit_tid,
                        content,
                        parent_comment.tid if parent_comment else "",
                    )
                )
                return {"comment_id": comment.tid, "comment_uin": comment.uin, "transport": "addreply_ugc"}

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_comment": True,
                    "qzone_auto_comment_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                return "这就算我赢了"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_comment()

        service = manager.plugin.qzone_service
        self.assertEqual(result["scanned"], 1)
        self.assertEqual(result["commented"], 1)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(service.recent_calls, 1)
        self.assertEqual(
            service.replies,
            [
                (
                    "89761500:dca659054aad3c6a8d8e0600",
                    "1_r_1_89761500",
                    "1",
                    "这就算我赢了",
                    "1",
                )
            ],
        )
        state = manager.db.state[module.QZONE_AUTO_COMMENT_STATE_KEY]
        self.assertEqual(state["processed"]["89761500:dca659054aad3c6a8d8e0600:1_r_1_89761500"]["action"], "thread_commented")

    async def test_execute_auto_comment_skips_friend_post_with_self_comment_but_no_new_thread_reply(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.recent_calls = 0
                self.top_comments = []
                self.replies = []
                self.recent_posts = [
                    models.QzonePost(
                        uin=2,
                        tid="friend",
                        name="Friend",
                        text="今天去了书店",
                        comments=[
                            models.QzoneComment(
                                uin=1,
                                nickname="Me",
                                content="这家书店听起来好舒服",
                                tid="c1",
                                create_time=100,
                            )
                        ],
                    )
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_recent_posts(self, *, pos=0, num=5, with_detail=False):
                self.recent_calls += 1
                return self.recent_posts

            async def comment(self, post_id, content):
                self.top_comments.append((post_id, content))

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.replies.append((post_id, comment.tid, content, parent_comment.tid if parent_comment else ""))

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_comment": True,
                    "qzone_auto_comment_limit": 2,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                raise AssertionError("friend post with existing self comment should not ask LLM")

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        result = await manager.execute_qzone_auto_comment()

        self.assertEqual(result["scanned"], 1)
        self.assertEqual(result["commented"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(manager.plugin.qzone_service.recent_calls, 1)
        self.assertEqual(manager.plugin.qzone_service.top_comments, [])
        self.assertEqual(manager.plugin.qzone_service.replies, [])

    async def test_execute_auto_reply_does_not_scan_friend_sources(self):
        module, models = _load_auto_comment_module()

        friend_post = models.QzonePost(
            uin=2,
            tid="friend",
            name="Friend",
            text="今天去了书店",
            comments=[
                models.QzoneComment(
                    uin=1,
                    nickname="Me",
                    content="这家书店听起来好舒服",
                    tid="c1",
                    create_time=100,
                ),
                models.QzoneComment(
                    uin=2,
                    nickname="Friend",
                    content="下次一起去",
                    tid="r1",
                    parent_tid="c1",
                    reply_to_tid="c1",
                    reply_to_uin=1,
                    create_time=200,
                ),
            ],
        )

        class Service:
            def __init__(self):
                self.friend_feed_calls = 0
                self.recent_calls = 0
                self.home_calls = 0
                self.about_calls = 0
                self.detail_calls = []
                self.replies = []

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_posts(self, *, target_id="", pos=0, num=5, with_detail=False):
                return []

            async def query_friend_feeds(self, *, pos=0, num=5, with_detail=False):
                self.friend_feed_calls += 1
                raise AssertionError("auto reply should not query friend feeds")

            async def query_recent_posts(self, *, pos=0, num=5, with_detail=False):
                self.recent_calls += 1
                raise AssertionError("auto reply should not query friend recent posts")

            async def query_home_posts(self, *, pos=0, num=5):
                self.home_calls += 1
                raise AssertionError("auto reply should not query friend home posts")

            async def query_about_me(self, *, offset=0, count=10):
                self.about_calls += 1
                raise AssertionError("auto reply should not query about-me friend source")

            async def detail(self, post_id):
                self.detail_calls.append(post_id)
                return friend_post

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.replies.append((post_id, comment.tid, content, parent_comment.tid if parent_comment else ""))

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_reply": True,
                    "qzone_auto_reply_limit": 2,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                return "行，下次一起去"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        result = await manager.execute_qzone_auto_reply()

        service = manager.plugin.qzone_service
        self.assertEqual(result["scanned"], 0)
        self.assertEqual(result["replied"], 0)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual((service.friend_feed_calls, service.recent_calls, service.home_calls, service.about_calls), (0, 0, 0, 0))
        self.assertEqual(service.detail_calls, [])
        self.assertEqual(service.replies, [])

    async def test_execute_auto_comment_uses_recent_posts_for_thread_continuation(self):
        module, models = _load_auto_comment_module()

        class Service:
            def __init__(self):
                self.recent_calls = 0
                self.replies = []
                self.friend_post = models.QzonePost(
                    uin=2,
                    tid="friend",
                    name="Friend",
                    text="今天去了书店",
                    comments=[
                        models.QzoneComment(
                            uin=1,
                            nickname="Me",
                            content="这家书店听起来好舒服",
                            tid="c1",
                            create_time=100,
                        ),
                        models.QzoneComment(
                            uin=2,
                            nickname="Friend",
                            content="下次一起去",
                            tid="r1",
                            parent_tid="c1",
                            reply_to_tid="c1",
                            reply_to_uin=1,
                            create_time=200,
                        )
                    ],
                )

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_recent_posts(self, *, pos=0, num=5, with_detail=False):
                self.recent_calls += 1
                return [self.friend_post]

            async def comment(self, post_id, content):
                raise AssertionError("thread continuation should not post a top-level comment")

            async def reply_comment(self, post_id, comment, content, *, parent_comment=None):
                self.replies.append((post_id, comment.tid, content, parent_comment.tid if parent_comment else ""))
                return {"comment_id": "self-r1", "comment_uin": 1, "transport": "addreply_ugc"}

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_comment": True,
                    "qzone_auto_comment_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )

            async def llm(self, **kwargs):
                return "行，下次一起去"

        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        async def no_sleep(_seconds):
            return None

        with patch.object(module.asyncio, "sleep", no_sleep):
            result = await manager.execute_qzone_auto_comment()

        service = manager.plugin.qzone_service
        self.assertEqual(result["scanned"], 1)
        self.assertEqual(result["commented"], 1)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(service.recent_calls, 1)
        self.assertEqual(service.replies, [("2:friend", "r1", "行，下次一起去", "c1")])

    async def test_auto_comment_rate_limit_records_retry_without_warning_failure(self):
        module, models = _load_auto_comment_module()
        discuss_module = sys.modules[f"{TASKS_PACKAGE_NAME}.interact.executors.discuss"]

        class Service:
            def __init__(self):
                self.comments = []
                self.posts = [
                    models.QzonePost(
                        uin=2,
                        tid="friend",
                        name="Friend",
                        text="今天太阳真大",
                    )
                ]

            async def context(self):
                return types.SimpleNamespace(uin=1)

            async def query_friend_feeds(self, *, pos=0, num=5, with_detail=False):
                return self.posts

            async def comment(self, post_id, content):
                self.comments.append((post_id, content))
                raise RuntimeError("使用人数过多，请稍后再试")

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_comment": True,
                    "qzone_auto_comment_limit": 1,
                }
                self.db = FakeDb()
                self.plugin = types.SimpleNamespace(
                    _is_terminated=False,
                    qzone_service=Service(),
                    _page_emit_dashboard_event=lambda *args, **kwargs: None,
                )
                self.llm_calls = 0

            async def llm(self, **kwargs):
                self.llm_calls += 1
                return "路上记得补水"

        logs = []
        manager = Manager()
        manager.plugin._call_llm_wrapper = manager.llm

        with patch.object(discuss_module.logger, "debug", lambda message, *args, **kwargs: logs.append(("debug", str(message)))):
            with patch.object(discuss_module.logger, "warning", lambda message, *args, **kwargs: logs.append(("warning", str(message)))):
                result = await manager.execute_qzone_auto_comment()

        self.assertEqual(result["commented"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertTrue(result["rate_limited"])
        self.assertTrue(any("QQ 空间自动评论稍后重试" in message for level, message in logs if level == "debug"))
        self.assertFalse(any("QQ 空间自动评论失败" in message for level, message in logs if level == "warning"))
        state = manager.db.state[module.QZONE_AUTO_COMMENT_STATE_KEY]
        self.assertNotIn("rate_limited_until", state)
        self.assertNotIn("rate_limited_reason", state)
        self.assertEqual(state["processed"]["2:friend"]["action"], "retry_later")
        self.assertEqual(state["processed"]["2:friend"]["content"], "路上记得补水")

    async def test_execute_auto_interaction_aggregates_comment_and_reply_results(self):
        module, _models = _load_auto_comment_module()

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_interaction": True,
                    "qzone_enable_auto_like": True,
                    "qzone_enable_auto_comment": True,
                    "qzone_enable_auto_reply": True,
                }
                self.plugin = types.SimpleNamespace(_is_terminated=False)
                self.calls = []

            async def execute_qzone_auto_like(self, *, emit_summary=True):
                self.calls.append(("like", emit_summary))
                return {"enabled": True, "scanned": 2, "liked": 1, "skipped": 1, "failed": 0, "generation_failed": 0}

            async def execute_qzone_auto_comment(self, *, emit_summary=True):
                self.calls.append(("comment", emit_summary))
                return {"enabled": True, "scanned": 3, "commented": 1, "skipped": 1, "failed": 0, "generation_failed": 0}

            async def execute_qzone_auto_reply(self, *, emit_summary=True):
                self.calls.append(("reply", emit_summary))
                return {"enabled": True, "scanned": 4, "replied": 2, "skipped": 1, "failed": 1, "generation_failed": 1}

        manager = Manager()

        result = await manager.execute_qzone_auto_interaction()

        self.assertEqual(manager.calls, [("like", False), ("comment", False), ("reply", False)])
        self.assertEqual(result["scanned"], 9)
        self.assertEqual(result["liked"], 1)
        self.assertEqual(result["commented"], 1)
        self.assertEqual(result["replied"], 2)
        self.assertEqual(result["skipped"], 3)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["generation_failed"], 1)

    async def test_execute_auto_interaction_stops_after_comment_rate_limit(self):
        module, _models = _load_auto_comment_module()

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_interaction": True,
                    "qzone_enable_auto_like": True,
                    "qzone_enable_auto_comment": True,
                    "qzone_enable_auto_reply": True,
                }
                self.plugin = types.SimpleNamespace(_is_terminated=False)
                self.calls = []

            async def execute_qzone_auto_like(self, *, emit_summary=True):
                self.calls.append(("like", emit_summary))
                return {"enabled": True, "scanned": 1, "liked": 0, "skipped": 1, "failed": 0, "generation_failed": 0}

            async def execute_qzone_auto_comment(self, *, emit_summary=True):
                self.calls.append(("comment", emit_summary))
                return {
                    "enabled": True,
                    "scanned": 1,
                    "commented": 0,
                    "skipped": 1,
                    "failed": 0,
                    "generation_failed": 0,
                    "rate_limited": True,
                    "rate_limited_reason": "使用人数过多，请稍后再试",
                }

            async def execute_qzone_auto_reply(self, *, emit_summary=True):
                self.calls.append(("reply", emit_summary))
                raise AssertionError("reply should be skipped after Qzone rate limit")

        manager = Manager()

        result = await manager.execute_qzone_auto_interaction()

        self.assertEqual(manager.calls, [("like", False), ("comment", False)])
        self.assertEqual(result["commented"], 0)
        self.assertEqual(result["replied"], 0)
        self.assertEqual(result["skipped"], 2)

    async def test_execute_auto_interaction_skips_summary_when_no_success(self):
        module, _models = _load_auto_comment_module()

        class Manager(module.TaskQzoneAutoCommentMixin):
            def __init__(self):
                self.qzone_conf = {
                    "enable_qzone": True,
                    "qzone_enable_auto_interaction": True,
                    "qzone_enable_auto_like": True,
                    "qzone_enable_auto_comment": True,
                    "qzone_enable_auto_reply": True,
                }
                self.plugin = types.SimpleNamespace(_is_terminated=False)
                self.calls = []

            async def execute_qzone_auto_like(self, *, emit_summary=True):
                self.calls.append(("like", emit_summary))
                return {"enabled": True, "scanned": 2, "liked": 0, "skipped": 2, "failed": 0, "generation_failed": 0}

            async def execute_qzone_auto_comment(self, *, emit_summary=True):
                self.calls.append(("comment", emit_summary))
                return {"enabled": True, "scanned": 3, "commented": 0, "skipped": 3, "failed": 0, "generation_failed": 0}

            async def execute_qzone_auto_reply(self, *, emit_summary=True):
                self.calls.append(("reply", emit_summary))
                return {"enabled": True, "scanned": 4, "replied": 0, "skipped": 4, "failed": 0, "generation_failed": 0}

        manager = Manager()

        result = await manager.execute_qzone_auto_interaction()

        self.assertEqual(manager.calls, [("like", False), ("comment", False), ("reply", False)])
        self.assertEqual(result["liked"], 0)
        self.assertEqual(result["commented"], 0)
        self.assertEqual(result["replied"], 0)


if __name__ == "__main__":
    unittest.main()



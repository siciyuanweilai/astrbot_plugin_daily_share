import importlib.util
import asyncio
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PERMISSION_MODULE_PATH = ROOT / "core" / "host" / "permission.py"
TOOLS_MODULE_PATH = ROOT / "core" / "host" / "tools.py"
TOOLS_PACKAGE_NAME = "daily_share_permission_tool_testpkg"
TOOLS_CORE_PACKAGE_NAME = f"{TOOLS_PACKAGE_NAME}.core"
TOOLS_HOST_PACKAGE_NAME = f"{TOOLS_CORE_PACKAGE_NAME}.host"
TOOLS_DATABASE_PACKAGE_NAME = f"{TOOLS_CORE_PACKAGE_NAME}.database"
TOOLS_KEYS_MODULE_NAME = f"{TOOLS_DATABASE_PACKAGE_NAME}.keys"
TOOLS_MODULE_NAME = f"{TOOLS_HOST_PACKAGE_NAME}.tools"


class _Logger:
    def debug(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None


def _install_stub_module(name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _install_astrbot_stub():
    event_module = _install_stub_module("astrbot.api.event")
    event_module.AstrMessageEvent = object
    api_module = _install_stub_module("astrbot.api", logger=_Logger())
    api_module.event = event_module
    _install_stub_module("astrbot", api=api_module)


def _load_module(module_name: str, module_path: Path):
    _install_astrbot_stub()
    package_name = f"daily_share_{module_name}"
    package_paths = {
        package_name: ROOT,
        f"{package_name}.core": ROOT / "core",
        f"{package_name}.core.host": ROOT / "core" / "host",
    }
    for name, path in package_paths.items():
        module = _install_stub_module(name)
        module.__path__ = [str(path)]
    return _exec_module(f"{package_name}.core.host.permission", module_path)


def _exec_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_tools_module():
    _install_astrbot_stub()
    package_paths = {
        TOOLS_PACKAGE_NAME: ROOT,
        TOOLS_CORE_PACKAGE_NAME: ROOT / "core",
        TOOLS_HOST_PACKAGE_NAME: ROOT / "core" / "host",
        TOOLS_DATABASE_PACKAGE_NAME: ROOT / "core" / "database",
        f"{TOOLS_CORE_PACKAGE_NAME}.tasks": ROOT / "core" / "tasks",
        f"{TOOLS_CORE_PACKAGE_NAME}.tasks.interact": ROOT
        / "core"
        / "tasks"
        / "interact",
    }
    for name, path in package_paths.items():
        module = _install_stub_module(name)
        module.__path__ = [str(path)]
    _exec_module(TOOLS_KEYS_MODULE_NAME, ROOT / "core" / "database" / "keys.py")
    return _exec_module(TOOLS_MODULE_NAME, TOOLS_MODULE_PATH)


class _Event:
    def __init__(
        self, *, role="member", is_admin_error=False, sender_id="10001", message_str=""
    ):
        self.role = role
        self.is_admin_error = is_admin_error
        self.sender_id = str(sender_id or "")
        self.unified_msg_origin = f"aiocqhttp:FriendMessage:{self.sender_id or '10001'}"
        self.message_str = message_str
        self.extras = {}

    def is_admin(self):
        if self.is_admin_error:
            raise RuntimeError("boom")
        return self.role == "admin"

    def get_sender_id(self):
        return self.sender_id

    def set_extra(self, key, value):
        self.extras[key] = value


class _EmojiBot:
    def __init__(self):
        self.calls = []

    async def set_msg_emoji_like(self, **kwargs):
        self.calls.append(kwargs)


def _event_with_emoji(**kwargs):
    event = _Event(**kwargs)
    event.bot = _EmojiBot()
    event.message_obj = types.SimpleNamespace(message_id=9001)
    return event


class _AgentContext:
    def __init__(self, event):
        self.event = event


class _ContextWrapper:
    def __init__(self, event):
        self.context = _AgentContext(event)


class PermissionTests(unittest.TestCase):
    def setUp(self):
        module = _load_module("permission_test", PERMISSION_MODULE_PATH)

        class PermissionHost(module.PluginPermissionService):
            pass

        self.host = PermissionHost(types.SimpleNamespace())

    def test_respects_astrbot_event_admin_role(self):
        event = _Event(role="admin")

        self.assertTrue(self.host._is_admin_event(event))

    def test_rejects_member_role(self):
        event = _Event(role="member")

        self.assertFalse(self.host._is_admin_event(event))

    def test_rejects_when_astrbot_admin_check_fails(self):
        event = _Event(role="admin", is_admin_error=True)

        self.assertFalse(self.host._is_admin_event(event))

    def test_accepts_only_astrbot_message_event_contract(self):
        event = _Event(role="admin")
        wrapper = _ContextWrapper(event)

        self.assertNotIn("_resolve_message_event", type(self.host).__mro__[1].__dict__)
        self.assertFalse(self.host._is_admin_event(wrapper))

    def test_configured_receiver_requires_exact_platform_instance(self):
        class Targets:
            @staticmethod
            def parse_targets_config(entries, *, expected_group=None):
                expected_type = "GroupMessage" if expected_group else "FriendMessage"
                return {
                    entry: {"cron": None, "seq": None}
                    for entry in entries
                    if f":{expected_type}:" in entry
                }

        self.host.task_manager = types.SimpleNamespace(targets=Targets())
        self.host.receiver_conf = {
            "groups": [],
            "users": ["bot-main:FriendMessage:user-test-001"],
        }
        self.host.extra_shares_conf = {
            "briefing_groups": [],
            "briefing_users": [],
        }
        self.host.ctx_service = types.SimpleNamespace(
            is_group_chat=lambda target: ":GroupMessage:" in target,
            is_weixin_event=lambda event: False,
            is_weixin_platform=lambda target: False,
        )
        same_instance = _Event(sender_id="user-test-001")
        same_instance.unified_msg_origin = "bot-main:FriendMessage:user-test-001"
        other_instance = _Event(sender_id="user-test-001")
        other_instance.unified_msg_origin = "bot-backup:FriendMessage:user-test-001"

        self.assertTrue(self.host._is_configured_receiver_event(same_instance))
        self.assertFalse(self.host._is_configured_receiver_event(other_instance))


class _TaskManager:
    def __init__(self):
        self.calls = []
        self.snapshots = self
        self.snapshot_store = self

    async def get_cached_news_link(self, target_uid, **kwargs):
        self.calls.append((target_uid, kwargs))
        return "第5条链接：https://example.com/news"


class _QzoneAutoTaskManager:
    def __init__(self):
        self.calls = []
        self._qzone_auto_interaction_lock = asyncio.Lock()
        self.qzone_interaction = self

    @property
    def qzone_auto_interaction_lock(self):
        return self._qzone_auto_interaction_lock

    async def execute_qzone_auto_interaction(self):
        self.calls.append(("all", None))
        return {
            "enabled": True,
            "scanned": 4,
            "liked": 1,
            "commented": 1,
            "replied": 1,
            "skipped": 1,
            "failed": 0,
            "generation_failed": 0,
        }

    async def execute_qzone_auto_like(self, *, emit_summary=True, target_id=""):
        self.calls.append(("like", emit_summary, target_id))
        return {
            "enabled": True,
            "scanned": 2,
            "liked": 1,
            "skipped": 1,
            "failed": 0,
            "generation_failed": 0,
        }

    async def execute_qzone_auto_comment(
        self, *, emit_summary=True, target_id="", target_umo=""
    ):
        self.calls.append(("comment", emit_summary, target_id, target_umo))
        return {
            "enabled": True,
            "scanned": 3,
            "commented": 1,
            "skipped": 2,
            "failed": 0,
            "generation_failed": 0,
        }

    async def execute_qzone_auto_reply(self, *, emit_summary=True):
        self.calls.append(("reply", emit_summary))
        return {
            "enabled": True,
            "scanned": 1,
            "replied": 1,
            "skipped": 0,
            "failed": 0,
            "generation_failed": 0,
        }


class NewsLinkToolPermissionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tools_module = _load_tools_module()
        runtime = types.SimpleNamespace(
            task_manager=_TaskManager(),
            _is_terminated=False,
            permissions=types.SimpleNamespace(
                _is_admin_event=lambda event: bool(event and event.is_admin()),
                _is_configured_receiver_event=lambda event: False,
                _remember_event_adapter=lambda event: None,
            ),
            tool_context=types.SimpleNamespace(
                _resolve_news_source_name=lambda source: source,
                _extract_news_link_urls=lambda result: (
                    ["https://example.com/news"] if "https://" in result else []
                ),
            ),
        )
        runtime._is_admin_event = runtime.permissions._is_admin_event
        runtime._is_configured_receiver_event = (
            runtime.permissions._is_configured_receiver_event
        )
        runtime._remember_event_adapter = runtime.permissions._remember_event_adapter
        runtime._resolve_news_source_name = (
            runtime.tool_context._resolve_news_source_name
        )
        runtime._extract_news_link_urls = runtime.tool_context._extract_news_link_urls
        self.host = tools_module.PluginToolService(runtime)
        runtime.tools = self.host

    async def test_member_can_query_current_session_news_link(self):
        result = await self.host.query_news_link(_Event(role="member"), index="5")

        self.assertIn("https://example.com/news", result)
        self.assertEqual(
            self.host.task_manager.calls[0][0], "aiocqhttp:FriendMessage:10001"
        )

    async def test_news_link_rejects_index_and_query_together(self):
        result = await self.host.query_news_link(
            _Event(role="member"),
            index="5",
            query="第五条新闻标题",
        )

        self.assertIn("index 和 query 不能同时填写", result)
        self.assertEqual(self.host.task_manager.calls, [])

    async def test_news_link_ignores_source_without_explicit_flag(self):
        await self.host.query_news_link(
            _Event(role="member"), index="2", source="zhihu"
        )

        self.assertIsNone(self.host.task_manager.calls[0][1]["source_key"])

    async def test_news_link_uses_source_with_explicit_flag(self):
        await self.host.query_news_link(
            _Event(role="member"),
            index="2",
            source="zhihu",
            source_explicit=True,
        )

        self.assertEqual(self.host.task_manager.calls[0][1]["source_key"], "zhihu")

    async def test_news_link_accepts_astrbot_message_event(self):
        result = await self.host.query_news_link(_Event(role="member"), index="6")

        self.assertIn("https://example.com/news", result)
        self.assertEqual(
            self.host.task_manager.calls[0][0], "aiocqhttp:FriendMessage:10001"
        )

    async def test_member_cannot_query_qzone_news_link(self):
        result = await self.host.query_news_link(_Event(role="member"), to_qzone=True)

        self.assertEqual(result, "QQ空间新闻链接仅管理员可查询。")
        self.assertEqual(self.host.task_manager.calls, [])


class QzoneAutoInteractToolPermissionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tools_module = _load_tools_module()
        runtime = types.SimpleNamespace(
            task_manager=_QzoneAutoTaskManager(),
            _is_terminated=False,
            permissions=types.SimpleNamespace(
                _is_admin_event=lambda event: bool(event and event.is_admin()),
                _event_sender_id=lambda event: event.get_sender_id() if event else "",
                _remember_event_adapter=lambda event: None,
            ),
        )
        runtime._is_admin_event = runtime.permissions._is_admin_event
        runtime._event_sender_id = runtime.permissions._event_sender_id
        runtime._remember_event_adapter = runtime.permissions._remember_event_adapter
        self.host = tools_module.PluginToolService(runtime)
        runtime.tools = self.host

    async def test_member_cannot_trigger_qzone_auto_interaction(self):
        result = await self.host.run_qzone_auto_interaction_tool(
            _Event(role="member"), action="all"
        )

        self.assertIn("仅管理员", result)
        self.assertEqual(self.host.task_manager.calls, [])

    async def test_member_can_trigger_scoped_comment_for_own_qzone(self):
        result = await self.host.run_qzone_auto_interaction_tool(
            _Event(role="member", sender_id="10001"),
            action="comment",
            target_id="10001",
        )

        self.assertIn("自动评论", result)
        self.assertEqual(
            self.host.task_manager.calls,
            [("comment", True, "10001", "aiocqhttp:FriendMessage:10001")],
        )

    async def test_member_can_trigger_scoped_like_for_own_qzone(self):
        result = await self.host.run_qzone_auto_interaction_tool(
            _Event(role="member", sender_id="10001"),
            action="like",
            target_id="10001",
        )

        self.assertIn("自动点赞", result)
        self.assertEqual(self.host.task_manager.calls, [("like", True, "10001")])

    async def test_member_cannot_trigger_scoped_comment_for_other_qzone(self):
        result = await self.host.run_qzone_auto_interaction_tool(
            _Event(role="member", sender_id="10001"),
            action="comment",
            target_id="20002",
        )

        self.assertIn("只能触发自己 QQ 空间", result)
        self.assertEqual(self.host.task_manager.calls, [])

    async def test_member_cannot_trigger_scoped_like_for_other_qzone(self):
        result = await self.host.run_qzone_auto_interaction_tool(
            _Event(role="member", sender_id="10001"),
            action="like",
            target_id="20002",
        )

        self.assertIn("只能触发自己 QQ 空间", result)
        self.assertEqual(self.host.task_manager.calls, [])

    async def test_admin_can_trigger_all_qzone_auto_interaction(self):
        result = await self.host.run_qzone_auto_interaction_tool(
            _Event(role="admin"), action="all"
        )

        self.assertIn("查询 4 条", result)
        self.assertIn("点赞 1 条", result)
        self.assertEqual(self.host.task_manager.calls, [("all", None)])

    async def test_admin_can_trigger_like_action(self):
        result = await self.host.run_qzone_auto_interaction_tool(
            _Event(role="admin"), action="like"
        )

        self.assertIn("自动点赞", result)
        self.assertEqual(self.host.task_manager.calls, [("like", True, "")])

    async def test_auto_interaction_marks_processing_and_success(self):
        event = _event_with_emoji(role="admin")

        await self.host.run_qzone_auto_interaction_tool(event, action="all")

        self.assertEqual([call["emoji_id"] for call in event.bot.calls], [125, 79])

    async def test_rejects_non_standard_natural_language_action(self):
        result = await self.host.run_qzone_auto_interaction_tool(
            _Event(role="admin"), action="点赞"
        )

        self.assertIn("all、like、comment、reply", result)
        self.assertEqual(self.host.task_manager.calls, [])

    async def test_rejects_unknown_action(self):
        result = await self.host.run_qzone_auto_interaction_tool(
            _Event(role="admin"), action="delete"
        )

        self.assertIn("all、like、comment、reply", result)
        self.assertEqual(self.host.task_manager.calls, [])

    async def test_rejects_when_qzone_auto_interaction_is_running(self):
        lock = self.host.task_manager.qzone_auto_interaction_lock
        await lock.acquire()
        try:
            result = await self.host.run_qzone_auto_interaction_tool(
                _Event(role="admin"), action="all"
            )
        finally:
            lock.release()

        self.assertIn("正在执行", result)
        self.assertEqual(self.host.task_manager.calls, [])


class _QzonePost:
    def __init__(self, key="10001:tid-1", uin=10001, text="测试说说"):
        self.key = key
        self.uin = uin
        self.tid = key.split(":", 1)[-1]
        self.name = "测试用户A"
        self.text = text
        self.rt_con = ""
        self.rt_images = []
        self.images = []
        self.videos = []
        self.comments = []
        self.create_time = 1700000000


class _QzoneService:
    def __init__(self):
        self.calls = []

    async def context(self):
        return types.SimpleNamespace(uin=100000303)

    async def query_posts(self, **kwargs):
        self.calls.append(("query_posts", kwargs))
        target = int(kwargs.get("target_id") or 10001)
        return [_QzonePost(key=f"{target}:tid-1", uin=target)]

    async def detail(self, post_id):
        self.calls.append(("detail", post_id))
        owner = int(str(post_id).split(":", 1)[0])
        return _QzonePost(key=post_id, uin=owner)

    async def comment(self, post_id, content):
        self.calls.append(("comment", post_id, content))

    async def like(self, post_id):
        self.calls.append(("like", post_id))


class _Db:
    def __init__(self):
        self.state = {}

    async def get_qzone_state(self, key, default=None):
        return self.state.get(key, default if default is not None else {})

    async def set_qzone_state(self, key, value):
        self.state[key] = value


class _QzoneCommentTaskManager:
    def __init__(self):
        self.calls = []
        self.qzone_interaction = self

    async def generate_qzone_auto_comment(self, post, *, state=None, target_umo=""):
        self.calls.append(("generate", post.key, state, target_umo))
        return "自动生成评论"


class QzoneToolPermissionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tools_module = _load_tools_module()
        focus = []
        snapshots = []
        events = []

        async def remember_posts(*args, **kwargs):
            snapshots.append((args, kwargs))

        async def remember_focus(*args, **kwargs):
            focus.append((args, kwargs))

        runtime = types.SimpleNamespace(
            qzone_service=_QzoneService(),
            db=_Db(),
            task_manager=_QzoneCommentTaskManager(),
            _is_terminated=False,
            permissions=types.SimpleNamespace(
                _is_admin_event=lambda event: bool(event and event.is_admin()),
                _event_sender_id=lambda event: event.get_sender_id() if event else "",
                _remember_event_adapter=lambda event: None,
            ),
            tool_context=types.SimpleNamespace(
                _remember_qzone_context_posts=remember_posts,
                _remember_qzone_context_focus=remember_focus,
            ),
            emit_dashboard_event=lambda *args, **kwargs: events.append((args, kwargs)),
        )
        runtime._is_admin_event = runtime.permissions._is_admin_event
        runtime._event_sender_id = runtime.permissions._event_sender_id
        runtime._remember_event_adapter = runtime.permissions._remember_event_adapter
        runtime._remember_qzone_context_posts = (
            runtime.tool_context._remember_qzone_context_posts
        )
        runtime._remember_qzone_context_focus = (
            runtime.tool_context._remember_qzone_context_focus
        )
        self.host = tools_module.PluginToolService(runtime)
        runtime.tools = self.host
        self.host.focus = focus
        self.host.snapshots = snapshots
        self.host.events = events

    async def test_member_can_list_own_qzone_without_admin(self):
        result = await self.host.run_qzone_tool(
            _Event(role="member", sender_id="10001"), action="list"
        )

        self.assertIn("当前查看：你的说说", result)
        self.assertEqual(self.host.qzone_service.calls[0][1]["target_id"], "10001")

    async def test_member_cannot_list_other_qzone(self):
        result = await self.host.run_qzone_tool(
            _Event(role="member", sender_id="10001"),
            action="list",
            target_id="20002",
        )

        self.assertIn("只能查看自己的 QQ 空间", result)
        self.assertEqual(self.host.qzone_service.calls, [])

    async def test_member_can_comment_own_qzone_post(self):
        result = await self.host.run_qzone_tool(
            _Event(
                role="member", sender_id="10001", message_str="把这条评论为：测试评论"
            ),
            action="comment",
            post_id="10001:tid-1",
            content="测试评论",
        )

        self.assertEqual(result, "评论已发送。")
        self.assertIn(
            ("comment", "10001:tid-1", "测试评论"), self.host.qzone_service.calls
        )

    async def test_rejects_generated_comment_content_not_supplied_by_user(self):
        result = await self.host.run_qzone_tool(
            _Event(role="member", sender_id="10001", message_str="快去评论下我的说说"),
            action="comment",
            post_id="10001:tid-1",
            content="少来这套，明天你死定了。",
        )

        self.assertIn("未检测到用户提供这段固定评论正文", result)
        self.assertIn("action=auto_comment", result)
        self.assertEqual(self.host.qzone_service.calls, [])

    async def test_rejects_direct_comment_when_user_plain_text_unavailable(self):
        result = await self.host.run_qzone_tool(
            _Event(role="member", sender_id="10001"),
            action="comment",
            post_id="10001:tid-1",
            content="测试评论",
        )

        self.assertIn("未检测到用户提供这段固定评论正文", result)
        self.assertIn("action=auto_comment", result)
        self.assertEqual(self.host.qzone_service.calls, [])

    async def test_member_can_auto_comment_own_qzone_post(self):
        result = await self.host.run_qzone_tool(
            _Event(role="member", sender_id="10001"),
            action="auto_comment",
            post_id="10001:tid-1",
        )

        self.assertEqual(result, "自动评论已发送：自动生成评论")
        self.assertIn(("detail", "10001:tid-1"), self.host.qzone_service.calls)
        self.assertIn(
            ("comment", "10001:tid-1", "自动生成评论"), self.host.qzone_service.calls
        )
        self.assertEqual(self.host.task_manager.calls[0][0], "generate")
        state = self.host.db.state["qzone_auto_comment"]
        self.assertEqual(state["processed"]["10001:tid-1"]["action"], "commented")
        self.assertEqual(state["processed"]["10001:tid-1"]["content"], "自动生成评论")

    async def test_member_can_like_own_qzone_post(self):
        result = await self.host.run_qzone_tool(
            _Event(role="member", sender_id="10001"),
            action="like",
            post_id="10001:tid-1",
        )

        self.assertEqual(result, "已点赞。")
        self.assertIn(("like", "10001:tid-1"), self.host.qzone_service.calls)

    async def test_mutating_qzone_tool_marks_processing_and_success(self):
        event = _event_with_emoji(role="member", sender_id="10001")

        result = await self.host.run_qzone_tool(
            event, action="like", post_id="10001:tid-1"
        )

        self.assertEqual(result, "已点赞。")
        self.assertEqual([call["emoji_id"] for call in event.bot.calls], [125, 79])

    async def test_mutating_qzone_tool_marks_failure(self):
        async def fail_like(_post_id):
            raise RuntimeError("点赞失败")

        self.host.qzone_service.like = fail_like
        event = _event_with_emoji(role="member", sender_id="10001")

        result = await self.host.run_qzone_tool(
            event, action="like", post_id="10001:tid-1"
        )

        self.assertIn("QQ 空间操作失败", result)
        self.assertEqual([call["emoji_id"] for call in event.bot.calls], [125, 106])

    async def test_readonly_qzone_tool_does_not_mark_emoji(self):
        event = _event_with_emoji(role="member", sender_id="10001")

        await self.host.run_qzone_tool(event, action="list")

        self.assertEqual(event.bot.calls, [])

    async def test_member_cannot_comment_other_qzone_post(self):
        result = await self.host.run_qzone_tool(
            _Event(role="member", sender_id="10001"),
            action="comment",
            post_id="20002:tid-1",
            content="测试评论",
        )

        self.assertIn("只能查看、点赞、评论或自动评论自己的 QQ 空间", result)
        self.assertEqual(self.host.qzone_service.calls, [])

    async def test_member_cannot_auto_comment_other_qzone_post(self):
        result = await self.host.run_qzone_tool(
            _Event(role="member", sender_id="10001"),
            action="auto_comment",
            post_id="20002:tid-1",
        )

        self.assertIn("只能查看、点赞、评论或自动评论自己的 QQ 空间", result)
        self.assertEqual(self.host.qzone_service.calls, [])

    async def test_member_cannot_like_other_qzone_post(self):
        result = await self.host.run_qzone_tool(
            _Event(role="member", sender_id="10001"),
            action="like",
            post_id="20002:tid-1",
        )

        self.assertIn("只能查看、点赞、评论或自动评论自己的 QQ 空间", result)
        self.assertEqual(self.host.qzone_service.calls, [])

    async def test_member_cannot_publish_qzone_post(self):
        result = await self.host.run_qzone_tool(
            _Event(role="member", sender_id="10001"),
            action="publish",
            content="测试说说",
        )

        self.assertIn("仅管理员", result)
        self.assertEqual(self.host.qzone_service.calls, [])


if __name__ == "__main__":
    unittest.main()

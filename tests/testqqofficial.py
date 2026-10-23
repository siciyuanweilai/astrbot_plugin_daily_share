import types
import unittest
from unittest.mock import AsyncMock

from .testfailure import (
    _Event,
    _MessageChain,
    _Plugin,
    _load_tasks_module,
    _new_manager,
)


class _Platform:
    def __init__(self, platform_id="official-main", platform_type="qq_official"):
        self.platform_id = platform_id
        self.platform_type = platform_type
        self.client = object()
        self._session_scene = {"GROUPOPENID": "group"}
        self._session_last_message_id = {}
        self._allow_group_proactive_send = True

    def meta(self):
        return types.SimpleNamespace(
            id=self.platform_id,
            name=self.platform_type,
            support_proactive_message=True,
        )

    def get_client(self):
        return self.client


def _manager(*platforms):
    mod = _load_tasks_module()
    plugin = _Plugin()
    plugin.context = types.SimpleNamespace(
        platform_manager=types.SimpleNamespace(get_insts=lambda: list(platforms)),
        send_message=AsyncMock(return_value=True),
    )
    plugin.daily_life_bridge = types.SimpleNamespace(record_delivery=AsyncMock())
    return _new_manager(mod, plugin), plugin


class QQOfficialDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def test_official_targets_preserve_openid_instance_and_independent_schedule(self):
        manager, _ = _manager(_Platform())
        for group, session_id in ((True, "GROUPOPENID"), (False, "USER_OPENID")):
            with self.subTest(group=group):
                target = manager.targets.resolve_target_input(
                    session_id, expected_group=group, adapter_id="official-main"
                )
                kind = "GroupMessage" if group else "FriendMessage"
                self.assertEqual(target, f"official-main:{kind}:{session_id}")
                self.assertEqual(
                    manager.targets.parse_targets_config(
                        [f"{target}:08:30:心情"], expected_group=group
                    ),
                    {target: {"cron": "30 8 * * *", "seq": "心情"}},
                )

    async def test_background_text_and_media_use_original_official_session(self):
        manager, plugin = _manager(_Platform())
        for kind, session_id in (
            ("GroupMessage", "GROUPOPENID"),
            ("FriendMessage", "USER_OPENID"),
        ):
            for content in (
                "分享正文",
                ("image", "photo.png"),
                ("record", "voice.wav"),
                ("video", "video.mp4"),
            ):
                with self.subTest(kind=kind, content=content):
                    target = f"official-main:{kind}:{session_id}"
                    chain = _MessageChain().message(content)
                    await manager.delivery.send_message_chain(target, chain)
                    plugin.context.send_message.assert_awaited_with(target, chain)

    async def test_matching_event_can_reply_without_background_scene_cache(self):
        platform = _Platform()
        platform._session_scene.clear()
        manager, plugin = _manager(platform)
        target = "official-main:GroupMessage:GROUPOPENID"
        event = _Event(unified_msg_origin=target)
        event.send = AsyncMock()
        chain = _MessageChain().message("当前会话分享")
        await manager.delivery.send_message_chain(target, chain, event)
        event.send.assert_awaited_once_with(chain)
        plugin.context.send_message.assert_not_awaited()

    async def test_other_official_event_cannot_redirect_background_delivery(self):
        manager, plugin = _manager(_Platform())
        target = "official-main:FriendMessage:USER_OPENID"
        event = _Event(unified_msg_origin="other-account:FriendMessage:USER_OPENID")
        event.send = AsyncMock()
        chain = _MessageChain().message("定向分享")
        await manager.delivery.send_message_chain(target, chain, event)
        event.send.assert_not_awaited()
        plugin.context.send_message.assert_awaited_once_with(target, chain)

    async def test_missing_group_scene_is_failure_without_delivery_receipt(self):
        platform = _Platform()
        platform._session_scene.clear()
        manager, plugin = _manager(platform)
        result = {}
        with self.assertRaisesRegex(RuntimeError, "尚未识别此群会话"):
            await manager.delivery.chains.send_chain_stage(
                "official-main:GroupMessage:GROUPOPENID",
                _MessageChain().message("分享"),
                "text",
                media_result=result,
            )
        self.assertFalse(result.get("text_sent"))
        plugin.context.send_message.assert_not_awaited()
        plugin.daily_life_bridge.record_delivery.assert_not_awaited()

    async def test_old_group_adapter_requires_message_reference(self):
        platform = _Platform()
        platform._allow_group_proactive_send = False
        manager, plugin = _manager(platform)
        target = "official-main:GroupMessage:GROUPOPENID"
        chain = _MessageChain().message("分享")
        with self.assertRaisesRegex(RuntimeError, "缺少可用的群消息引用"):
            await manager.delivery.send_message_chain(target, chain)
        plugin.context.send_message.assert_not_awaited()
        platform._session_last_message_id["GROUPOPENID"] = "received-message-id"
        await manager.delivery.send_message_chain(target, chain)
        plugin.context.send_message.assert_awaited_once_with(target, chain)

    async def test_platform_rejection_does_not_create_success_or_life_receipt(self):
        manager, plugin = _manager(_Platform())
        plugin.context.send_message.side_effect = RuntimeError("主动发送权限不足")
        result = {}
        with self.assertRaisesRegex(RuntimeError, "权限不足"):
            await manager.delivery.chains.send_chain_stage(
                "official-main:FriendMessage:USER_OPENID",
                _MessageChain().message("分享"),
                "text",
                media_result=result,
            )
        self.assertFalse(result.get("text_sent"))
        plugin.daily_life_bridge.record_delivery.assert_not_awaited()

    def test_shared_instance_id_cannot_lose_official_account_binding(self):
        manager, _ = _manager(_Platform("same-id"), _Platform("same-id", "aiocqhttp"))
        with self.assertRaisesRegex(ValueError, "独立 ID"):
            manager.targets.resolve_target_input(
                "123456", expected_group=False, adapter_id="qq_official!same-id"
            )

    def test_other_duplicate_ids_do_not_block_unique_official_target(self):
        manager, _ = _manager(
            _Platform(),
            _Platform("same-id", "aiocqhttp"),
            _Platform("same-id", "qq_official"),
        )
        self.assertEqual(
            manager.targets.resolve_target_input(
                "GROUPOPENID", expected_group=True, adapter_id="official-main"
            ),
            "official-main:GroupMessage:GROUPOPENID",
        )
        binding = manager.targets.ensure_target_platform_routable(
            "same-id:GroupMessage:123456"
        )
        self.assertEqual(binding.platform_type, "aiocqhttp")


class QQOfficialContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_numeric_and_openid_official_history_never_query_onebot(self):
        from .testcontext import _PlatformHistoryManager, _service

        for group in (False, True):
            for session_id in ("123456", "USER_OPENID"):
                with self.subTest(group=group, session_id=session_id):
                    _, service = _service()
                    kind = "GroupMessage" if group else "FriendMessage"
                    target = f"official-main:{kind}:{session_id}"
                    service.context.platform_manager = types.SimpleNamespace(
                        get_insts=lambda: [
                            _Platform("onebot-main", "aiocqhttp"),
                            _Platform(),
                        ]
                    )
                    service.context.message_history_manager = _PlatformHistoryManager()
                    service.onebot_history._get_onebot_history_data = AsyncMock(
                        side_effect=AssertionError("官方平台不能调用 OneBot 历史")
                    )
                    await service.get_history_data(target, is_group=group)
                    service.onebot_history._get_onebot_history_data.assert_not_awaited()
                    self.assertIsNone(service.get_onebot_bot(target))
                    self.assertIsNone(
                        service.get_onebot_bot("0", adapter_id="official-main")
                    )
                    self.assertIsNone(
                        service.get_onebot_bot("0", adapter_id="missing-account")
                    )
                    self.assertTrue(service.context.message_history_manager.calls)
                    self.assertEqual(
                        service.context.message_history_manager.calls[0]["platform_id"],
                        "official-main",
                    )

    async def test_qzone_cannot_use_cached_official_client_or_other_account(self):
        from .testqzonerelationship import Platform, qzone_service

        official = object()
        other_onebot = object()
        service = qzone_service(
            [
                Platform("official-main", official, "qq_official"),
                Platform("onebot-main", other_onebot),
            ],
            cached="official-main",
        )
        self.assertIs(service.ctx_service.get_bot_instance("official-main"), official)
        self.assertIsNone(service._get_bot())

    async def test_qzone_auto_detection_uses_onebot_only(self):
        from .testqzonerelationship import Platform, qzone_service

        official, onebot = object(), object()
        service = qzone_service(
            [Platform("official-main", official, "qq_official")], cached=""
        )
        self.assertIsNone(service._get_bot())
        service = qzone_service(
            [
                Platform("official-main", official, "qq_official"),
                Platform("onebot-main", onebot),
            ],
            cached="",
        )
        self.assertIs(service._get_bot(), onebot)


if __name__ == "__main__":
    unittest.main()

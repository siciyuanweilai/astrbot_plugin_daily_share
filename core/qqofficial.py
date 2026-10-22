from __future__ import annotations

from collections.abc import Mapping

from .platform import (
    QQ_OFFICIAL_PLATFORM_TYPES,
    PlatformBinding,
    parse_platform_session,
)


def ensure_qq_official_background_send(
    binding: PlatformBinding, target_umo: str
) -> None:
    """拦截官方适配器已知会静默跳过的群聊发送条件。"""
    if binding.platform_type not in QQ_OFFICIAL_PLATFORM_TYPES:
        return
    session = parse_platform_session(target_umo)
    if not session or not session.is_group:
        return

    # 与框架 send_by_session 的群会话归一化保持一致。只读缓存，
    # 不伪造场景或 msg_id；不同 AstrBot 版本没有该缓存时交给框架发送。
    session_id = session.session_id.rsplit("_", 1)[-1]
    instance = binding.instance
    scenes = getattr(instance, "_session_scene", None)
    if isinstance(scenes, Mapping) and not scenes.get(session_id):
        raise RuntimeError(
            "QQ 官方机器人尚未识别此群会话，请先在目标群 @机器人发送一条消息，"
            "再重试分享（适配器重启后也需重新接收群消息）"
        )
    proactive_group = (
        isinstance(scenes, Mapping)
        and scenes.get(session_id) == "group"
        and getattr(instance, "_allow_group_proactive_send", False)
    )
    message_ids = getattr(instance, "_session_last_message_id", None)
    if (
        isinstance(message_ids, Mapping)
        and not message_ids.get(session_id)
        and not proactive_group
    ):
        raise RuntimeError(
            "QQ 官方机器人缺少可用的群消息引用，请先在目标群 @机器人发送一条消息；"
            "定时主动分享需使用支持群主动发送的 AstrBot 适配器并开启群内主动发言"
        )

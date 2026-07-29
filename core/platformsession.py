from __future__ import annotations


def create_message_session(
    platform_id: str, message_type: str, session_id: str
) -> object:
    """按框架会话契约创建主动发送会话。"""
    from astrbot.core.platform.astr_message_event import MessageSession

    return MessageSession.from_str(f"{platform_id}:{message_type}:{session_id}")


__all__ = ["create_message_session"]

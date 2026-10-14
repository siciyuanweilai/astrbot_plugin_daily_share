"""主动分享与正常聊天共用目标会话的人设选择；公开空间使用全局身份。"""

from .database.keys import is_public_share_target


async def selected_share_persona(context, target_umo: str | None = None) -> dict:
    manager = context.persona_manager
    target = str(target_umo or "").strip()
    if not target or is_public_share_target(target):
        return await manager.get_default_persona_v3() or {}

    conversation_persona_id = None
    conversations = getattr(context, "conversation_manager", None)
    if conversations is not None:
        conversation_id = await conversations.get_curr_conversation_id(target)
        if conversation_id:
            conversation = await conversations.get_conversation(target, conversation_id)
            if conversation is not None:
                conversation_persona_id = conversation.persona_id

    persona_id, persona, _, _ = await manager.resolve_selected_persona(
        umo=target,
        conversation_persona_id=conversation_persona_id,
        platform_name=target.split(":", 1)[0],
    )
    if persona_id == "[%None]":
        return {}
    if persona:
        return persona
    return await manager.get_default_persona_v3(umo=target) or {}

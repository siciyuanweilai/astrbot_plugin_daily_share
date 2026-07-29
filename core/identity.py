def compact_identity_text(value: str, limit: int = 1000) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def build_content_system_prompt(persona_text: str) -> str:
    text = compact_identity_text(persona_text)
    identity_rule = (
        "【身份边界】系统人设描述的是你本人，不是聊天对象或关系档案中的其他人；"
        "人物身份和称谓只采用原文明确提供的信息。"
    )
    return f"{text}\n\n{identity_rule}" if text else identity_rule


def build_persona_figure_prompt(persona_text: str) -> str:
    text = compact_identity_text(persona_text, 500)
    if not text:
        return ""
    return f"人物形象遵循角色人设原文：{text}, 1个人物, 独奏"

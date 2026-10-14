def compact_identity_text(value: str) -> str:
    # 人设是稳定前缀。只归一化空白，不截掉末尾的身份、称谓和禁用条件。
    return " ".join(str(value or "").split())


def build_content_system_prompt(persona_text: str) -> str:
    text = compact_identity_text(persona_text)
    identity_rule = (
        "【身份边界】系统人设描述的是你本人，不是聊天对象或关系档案中的其他人；"
        "人物身份和称谓只采用原文明确提供的信息。"
    )
    return f"{text}\n\n{identity_rule}" if text else identity_rule


def build_persona_figure_prompt(persona_text: str) -> str:
    text = compact_identity_text(persona_text)
    if not text:
        return ""
    return f"人物形象遵循角色人设原文：{text}, 1个人物, 独奏"

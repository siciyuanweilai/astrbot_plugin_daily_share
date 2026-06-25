def compact_identity_text(value: str, limit: int = 1000) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def build_self_identity_prompt(persona_text: str) -> str:
    text = compact_identity_text(persona_text)
    if not text:
        return ""

    return (
        "\n\n【角色本人原文约束】\n"
        "下面这段人设原文描述的是“你本人”，不是聊天对象，也不是日程或关系档案里的其他人。\n"
        f"{text}\n"
        "生成文案、动作、称谓、配图和语气时必须遵守这段原文，不要自行改写或补全其中没有写明的身份细节。\n"
    )


def build_persona_figure_prompt(persona_text: str) -> str:
    text = compact_identity_text(persona_text, 500)
    if not text:
        return ""
    return f"人物形象遵循角色人设原文：{text}, 1个人物, 独奏"

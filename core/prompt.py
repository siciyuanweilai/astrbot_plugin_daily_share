import re


TOPIC_CATEGORY_RULES = {
    "美食": {
        "target_desc": "具体食物名称",
        "rules": [
            "目标必须是现实中可食用的具体食物、饮品、菜品或点心。",
            "不要把以食物为主题的影视、动漫、游戏、书籍等作品当作美食推荐。",
        ],
    },
    "游戏": {
        "target_desc": "具体游戏名称",
        "rules": [
            "目标必须是可游玩的软件游戏或游戏作品。",
            "不要推荐游戏机、外设、平台会员等硬件或服务。",
        ],
    },
    "好物": {
        "target_desc": "具体物品/产品名称",
        "rules": [
            "目标必须是具体物品、产品品类或知名单品。",
            "不要推荐过于抽象的生活方式、理念或泛泛的消费建议。",
        ],
    },
}


def compact_prompt(*parts: str) -> str:
    """拼接提示词片段并清理多余空行。"""
    text = "\n".join(str(part or "").strip() for part in parts if str(part or "").strip())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def split_identity_names(value: str) -> list[str]:
    names = [
        item.strip()
        for item in re.split(r"[、,，/|]+", str(value or ""))
        if item.strip()
    ]
    return list(dict.fromkeys(names))


def build_private_target_prompt(call_name: str = "", detect_name: str = "") -> str:
    names = split_identity_names(detect_name or call_name)
    display_names = "、".join(names) or str(detect_name or call_name or "").strip()
    call_name = str(call_name or "").strip()
    if not display_names and not call_name:
        return ""

    call_rule = ""
    if call_name:
        call_rule = (
            f"对方的人设称呼：【{call_name}】\n"
            "- 如果系统人设已经规定了对对方的称呼，优先遵循系统人设；否则可以自然使用这个称呼。"
        )

    return compact_prompt(
        "【当前私聊对象关系规则】",
        call_rule,
        f"当前私聊对象的可能识别名/本地昵称：【{display_names or '未提供'}】",
        "- 这些名字只用于判断“正在和谁说话”，不要把它们当成第三者写进正文。",
        "- 检查【生活状态】、【关系档案】、【聊天记忆摘要】、【近期事件】和【今日完整时间轴及计划】；如果其中的人就是当前私聊对象，必须改成面向“你/我们”的表达。",
        "- 禁止把TA写成第三者；适合时使用“你”“我们”“刚才我们”“等下见你”“和你一起”等关系表达。",
    )


def build_private_recipient_identity_prompt(target_text: str) -> str:
    target_text = str(target_text or "").strip()
    if not target_text:
        return ""
    return compact_prompt(
        "【当前私聊对象身份规则】",
        f"当前这条分享正在发给同一个私聊对象：{target_text}",
        "- 如果【关系档案】、【聊天记忆摘要】、【近期事件】或【今日完整时间轴及计划】里的人名、备注或标识与当前私聊对象匹配，必须把这个人视为正在和你对话的“你”。",
        "- 不要把当前私聊对象写成第三者；不要写成与无关第三人一起活动的旁白。",
        "- 应改成第二人称或共同经历表达，例如“和你一起”“刚才我们”“等下见你”“你上次说的”。",
        "- 只有无法确认匹配时，才把关系档案中的其他人当作第三者。",
    )


def build_audience_rule(*, is_group: bool, is_qzone: bool, action: str = "分享") -> str:
    if is_qzone:
        return (
            f"QQ 空间：这是你的个人动态，按第一人称记录或表达{action}；"
            "不要写成群公告、私聊消息或向某个特定对象喊话。"
        )
    if is_group:
        return (
            f"群聊：面向群友自然{action}，可以使用“大家”或省略称呼；"
            "不要评价群氛围，也不要假装正在回应群里刚发生的事。"
        )
    return (
        f"私聊：面向当前这一个人自然{action}，优先使用“你/我们”；"
        "不要使用“大家”“你们”“各位”。"
    )


def build_common_content_rules(
    *,
    is_group: bool,
    is_qzone: bool,
    date_text: str,
    time_text: str,
    period_label: str,
    action: str,
    allow_detail: bool = False,
) -> str:
    privacy_rule = (
        "群聊里可以轻量提及适合公开的状态，但不要暴露具体地点、行程、关系和备忘录。"
        if is_group and allow_detail
        else "生活状态、日程、聊天记忆只作为语气和场景参考；不确定或偏隐私的细节不要主动写出。"
    )
    scene_rule = (
        "如果引用当下状态，必须和生活状态/日程一致；联系不上就直接进入主题，不要强行编造理由。"
    )
    return compact_prompt(
        "【通用表达规则】",
        f"- 当前本地时间：{date_text} {time_text}（{period_label}）。涉及早晚、白天、夜晚、晚安等表达时，以这个时间为准。",
        "- 系统人设描述的是“你本人”，不是聊天对象，也不是关系档案中的其他人。",
        f"- 目标关系：{build_audience_rule(is_group=is_group, is_qzone=is_qzone, action=action)}",
        f"- 隐私边界：{privacy_rule}",
        f"- 场景一致性：{scene_rule}",
        "- 表达方式：自然、具体、有人味；不要像客服、营销号、机器人或模板文案。",
        "- 事实边界：资料没有给出的细节不要补全；可以概括，但不要编造人物、地点、关系和事件。",
    )


def build_scene_consistency_rule(action: str = "分享") -> str:
    return compact_prompt(
        "【场景融合与一致性】",
        f"- 可以参考当前状态自然引出{action}；如果状态与主题无关，直接进入主题。",
        "- 不要为了制造场景而补写资料没有支持的动作、地点或状态；文案场景必须与日程、穿搭、天气和时间一致。",
    )


def build_opening_integrity_rule(guidance: str = "") -> str:
    return compact_prompt(
        "【开头方式】",
        "- 开头应来自当前材料、主题或真实状态；不要伪造心理活动、偶然触发、临时想到等原因。",
        "- 如果没有合适引子，直接进入主题。",
        guidance,
    )


def build_topic_category_boundary(category_type: str) -> tuple[str, str]:
    category_type = str(category_type or "").strip()
    rule = TOPIC_CATEGORY_RULES.get(category_type)
    if not rule:
        return "具体作品名称", ""

    lines = [
        "【类别边界】",
        f"当前推荐类别：{category_type}",
        *[f"- {item}" for item in rule["rules"]],
    ]
    return str(rule["target_desc"]), "\n".join(lines)


def build_qzone_diary_prompt() -> str:
    return compact_prompt(
        "【QQ 空间说说任务边界】",
        "这是一条个人 QQ 空间动态，请按第一人称写成自然说说。",
        "可以记录自己的状态、感受、见闻或观点；不要写成群聊通知、私聊回复、营销安利或对某个人喊话。",
        "生活状态只用于判断时间感、语气和场景一致性，不要主动透露具体地点、行程、关系、备忘录等隐私细节。",
    )


def build_qzone_interaction_rules(task_prompt: str) -> str:
    task_prompt = str(task_prompt or "").strip()
    return compact_prompt(
        "【QQ 空间互动规则】",
        task_prompt,
        "通用要求：自然、简短、贴合上下文；不要像客服、营销号、机器人或 AI。",
        "时间要求：涉及早晚、白天、夜晚、晚安等时间表达时，必须以提示中的【当前本地时间】为准；上下文没有明确夜晚时，不要把白天写成晚上。",
        "关系要求：明确区分自己、动态作者、评论人和被回复的人；不要把当前互动对象写成无关第三者。",
        "隐私要求：不要追问隐私，不要主动透露生活状态里的具体地点、行程、关系、备忘录等细节。",
        "事实要求：只依据给出的动态、评论和上下文接话；不确定、敏感或没必要互动时输出“跳过”。",
        "输出要求：只输出评论/回复正文或“跳过”，不要解释，不要编号。",
    )


def build_smart_schedule_rules() -> str:
    return compact_prompt(
        "你是谨慎的定时计划助手。你只能建议时间，不能突破用户配置。",
        "必须只输出 JSON 数组。时间必须是今天，不能安排已经过去的时间，必须避开勿扰时间。",
        "根据任务目标、生活/日程摘要、近期分享记录和用户偏好选择自然时间；不要把计划写成固定时段模板。",
        "如果今天剩余时间没有合适计划，可以输出空数组。",
        "时间必须带秒，秒数使用 05-55 的自然随机秒，不要使用整分 :00。",
    )

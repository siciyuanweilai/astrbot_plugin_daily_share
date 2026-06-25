from .config import NEWS_SOURCE_MAP, ShareType, TimePeriod

# 类型中文映射表
TYPE_CN_MAP = {
    "greeting": "问候",
    "news": "新闻",
    "mood": "心情",
    "knowledge": "知识",
    "recommendation": "推荐"
}

PERIOD_CN_MAP = {
    "dawn": "凌晨",
    "morning": "早晨",
    "forenoon": "上午",
    "noon": "中午",
    "afternoon": "下午",
    "evening": "傍晚",
    "night": "晚上",
    "late_night": "深夜",
}


def share_type_label(value) -> str:
    raw = value.value if isinstance(value, ShareType) else str(value or "").strip()
    return TYPE_CN_MAP.get(raw, raw)


def period_label(value) -> str:
    raw = value.value if isinstance(value, TimePeriod) else str(value or "").strip()
    return PERIOD_CN_MAP.get(raw, raw)

# 输入指令映射表
CMD_CN_MAP = {
    "问候": ShareType.GREETING,
    "新闻": ShareType.NEWS,
    "心情": ShareType.MOOD,
    "知识": ShareType.KNOWLEDGE,
    "推荐": ShareType.RECOMMENDATION
}

SHARE_TYPE_CN_VALUE_MAP = {
    label: value
    for value, label in TYPE_CN_MAP.items()
}
SHARE_TYPE_CN_SET = set(SHARE_TYPE_CN_VALUE_MAP)


def normalize_share_type_token(value, *, allow_auto: bool = False) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw == "自动":
        return "auto" if allow_auto else ""
    normalized = SHARE_TYPE_CN_VALUE_MAP.get(raw)
    return normalized or ""


def canonical_share_type_token(value, *, allow_auto: bool = False) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw == "自动":
        return "自动" if allow_auto else ""
    return raw if raw in SHARE_TYPE_CN_SET else ""


def normalize_share_type_sequence(value, *, allow_auto: bool = False) -> list[str]:
    if isinstance(value, (list, tuple)):
        raw_items = value
    else:
        raw_items = str(value or "").replace("，", ",").split(",")
    result = []
    for item in raw_items:
        normalized = normalize_share_type_token(item, allow_auto=allow_auto)
        if normalized:
            result.append(normalized)
    return result


def canonical_share_type_sequence(value, *, allow_auto: bool = False) -> list[str]:
    if isinstance(value, (list, tuple)):
        raw_items = value
    else:
        raw_items = str(value or "").replace("，", ",").split(",")
    result = []
    for item in raw_items:
        normalized = canonical_share_type_token(item, allow_auto=allow_auto)
        if normalized:
            result.append(normalized)
    return result

# 新闻源中文映射表
SOURCE_CN_MAP = {v['name']: k for k, v in NEWS_SOURCE_MAP.items()}
SOURCE_CN_MAP.update({
    "知乎": "zhihu", 
    "微博": "weibo", 
    "B站": "bili", 
    "小红书": "xiaohongshu", 
    "抖音": "douyin", 
    "快手": "kuaishou",
    "头条": "toutiao", 
    "百度": "baidu", 
    "腾讯": "tencent",
    "夸克": "quark",
    "36氪": "36kr",
    "51CTO": "51cto",
    "A站": "acfun",     
    "爱范儿": "ifanr",
    "网易": "netease",
    "新浪": "sina",
    "澎湃": "thepaper",
    "第一财经": "yicai",
    "财联社": "cls"       
})

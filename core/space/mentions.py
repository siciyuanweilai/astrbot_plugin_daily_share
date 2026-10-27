from __future__ import annotations

import re
from typing import Any


_MENTION = re.compile(r"@\{uin:([1-9][0-9]*),nick:[^{}\r\n]*\}")
_UNSAFE_NICK = re.compile(r"[,{}\x00-\x1f\x7f]")


def normalize_qzone_mentions(value: Any) -> list[dict[str, str]]:
    """校验显式提供的 QQ 号和昵称，按 QQ 号去重。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("@ 好友必须是包含 uin 和 nick 的列表")
    result = []
    seen: set[str] = set()
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 个 @ 好友必须包含 uin 和 nick")
        raw_uin = item.get("uin")
        uin = str(raw_uin).strip() if type(raw_uin) in (str, int) else ""
        raw_nick = item.get("nick")
        nick = raw_nick.strip() if isinstance(raw_nick, str) else ""
        if not re.fullmatch(r"[1-9][0-9]*", uin) or len(uin) > 20:
            raise ValueError(
                f"第 {index} 个 @ 好友的 QQ 号必须为非零开头的数字，最多 20 位"
            )
        if not nick or _UNSAFE_NICK.search(raw_nick):
            raise ValueError(
                f"第 {index} 个 @ 好友的昵称不能为空，且不能包含英文逗号、花括号或控制字符"
            )
        if uin not in seen:
            seen.add(uin)
            result.append({"uin": uin, "nick": nick})
    return result


def qzone_publish_text(text: str = "", mentions: Any = None) -> str:
    """将提及添加到正文末尾，保留手写标记且不重复添加同一 QQ 号。"""
    content = str(text or "")
    existing = {match.group(1) for match in _MENTION.finditer(content)}
    markers = [
        f"@{{uin:{item['uin']},nick:{item['nick']}}}"
        for item in normalize_qzone_mentions(mentions)
        if item["uin"] not in existing
    ]
    if not markers:
        return content
    suffix = " ".join(markers)
    return f"{content.rstrip()}\n{suffix}" if content.strip() else suffix


def normalized_qzone_publish_text(text: str) -> str:
    """核验发布结果时忽略 QQ 空间改写的昵称和 who 等字段，保留提及对象。"""
    content = _MENTION.sub(lambda match: f"@{{uin:{match.group(1)}}}", str(text or ""))
    return " ".join(content.strip().split())

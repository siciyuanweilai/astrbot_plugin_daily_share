from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, List


ONEBOT_PLATFORM_TYPES = frozenset({"aiocqhttp", "onebot"})
WEIXIN_PLATFORM_TYPE = "weixin_oc"
PRIVATE_ONLY_PLATFORM_TYPES = frozenset({"webchat", WEIXIN_PLATFORM_TYPE})
SESSION_MESSAGE_TYPES = frozenset({"GroupMessage", "FriendMessage"})


@dataclass(frozen=True, slots=True)
class PlatformSession:
    """插件使用的框架消息会话字符串视图。"""

    platform_id: str
    message_type: str
    session_id: str

    @property
    def is_group(self) -> bool:
        return self.message_type == "GroupMessage"

    def __str__(self) -> str:
        return f"{self.platform_id}:{self.message_type}:{self.session_id}"


@dataclass(frozen=True, slots=True)
class PlatformBinding:
    """主动发送所需的平台实例能力和冲突状态。"""

    platform_id: str
    platform_type: str
    route_id: str
    supports_proactive: bool
    supports_group: bool
    shared_id: bool
    conflicted: bool
    instance: Any


def get_platform_bindings(context_obj) -> list[PlatformBinding]:
    """读取全部已启用实例，并为跨平台同名实例生成内部路由标识。"""
    records: list[tuple[str, str, bool, Any]] = []
    for instance in iter_platform_instances(context_obj):
        meta = get_platform_meta(instance)
        platform_id = get_platform_id(instance)
        if not meta or not platform_id:
            continue
        platform_type = get_platform_type(instance).lower()
        records.append(
            (
                platform_id,
                platform_type,
                bool(meta.support_proactive_message),
                instance,
            )
        )

    id_counts = Counter(platform_id for platform_id, *_rest in records)
    binding_counts = Counter(
        (platform_id, platform_type) for platform_id, platform_type, *_rest in records
    )
    return [
        PlatformBinding(
            platform_id=platform_id,
            platform_type=platform_type,
            route_id=(
                f"{platform_type}!{platform_id}"
                if id_counts[platform_id] > 1
                else platform_id
            ),
            supports_proactive=supports_proactive,
            supports_group=platform_type not in PRIVATE_ONLY_PLATFORM_TYPES,
            shared_id=id_counts[platform_id] > 1,
            conflicted=binding_counts[(platform_id, platform_type)] > 1,
            instance=instance,
        )
        for platform_id, platform_type, supports_proactive, instance in records
    ]


def parse_platform_session(value: str) -> PlatformSession | None:
    """按框架消息会话契约解析正式统一消息来源标识。"""
    text = str(value or "").strip().replace("：", ":")
    parts = text.split(":", 2)
    if len(parts) != 3:
        return None
    platform_id, message_type, session_id = (part.strip() for part in parts)
    if not platform_id or message_type not in SESSION_MESSAGE_TYPES or not session_id:
        return None
    return PlatformSession(platform_id, message_type, session_id)


def iter_platform_instances(context_obj) -> List[Any]:
    """从当前框架平台管理器返回平台实例列表。"""
    return list(context_obj.platform_manager.get_insts())


def get_platform_meta(inst):
    return inst.meta() if inst else None


def get_platform_id(inst) -> str:
    meta = get_platform_meta(inst)
    return str(meta.id or "").strip() if meta else ""


def get_platform_type(inst) -> str:
    meta = get_platform_meta(inst)
    return str(meta.name or "").strip() if meta else ""


def get_platform_client(inst):
    return inst.get_client() if inst else None


def find_platform_instance_by_types(context_obj, platform_types: Iterable[str]):
    """按框架平台元数据中的正式类型精确查找实例。"""
    expected = {
        str(platform_type or "").strip().lower()
        for platform_type in platform_types
        if str(platform_type or "").strip()
    }
    matches = [
        binding
        for binding in get_platform_bindings(context_obj)
        if binding.platform_type in expected and not binding.conflicted
    ]
    return matches[0].instance if len(matches) == 1 else None


def is_onebot_instance(inst) -> bool:
    return get_platform_type(inst).lower() in ONEBOT_PLATFORM_TYPES


def is_weixin_oc_instance(inst) -> bool:
    return get_platform_type(inst).lower() == WEIXIN_PLATFORM_TYPE

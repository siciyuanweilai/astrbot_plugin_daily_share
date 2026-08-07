import asyncio

from astrbot.api import logger

from ..integrations import DailyLifeBridge
from ..platform import (
    ONEBOT_PLATFORM_TYPES,
    find_platform_instance_by_types,
    get_platform_bindings,
    get_platform_client,
    parse_platform_session,
)
from .analysis import ContextHistoryAnalysisService
from .daily.memos import ContextLifeMemoryService
from .daily.narrate import ContextLifeFormatService
from .daily.parse import ContextLifeParseService
from .daily.plugin import ContextLifePluginService
from .memory import ContextMemoryService
from .normalize import ContextHistoryNormalizeService
from .records.conversation import ContextHistoryConversationFetchService
from .records.onebot import ContextHistoryOnebotFetchService
from .records.router import ContextHistoryFetchRouterService
from .records.source import ContextHistoryPlatformFetchService
from .shared import (
    DAILY_SHARE_MEMORY_PROMPT as DAILY_SHARE_MEMORY_PROMPT,
)
from .shared import (
    DAILY_SHARE_SOURCE as DAILY_SHARE_SOURCE,
)
from .tts import ContextTtsService

ONEBOT_API_TIMEOUT_SECONDS = 30


class ContextService:
    """聚合上下文、历史、生活状态和语音组件。"""

    def __init__(self, context_obj, config, daily_life_bridge=None):
        self.context = context_obj
        self.config = config
        self.bot_map = {}

        unified_conf = self.config.get("context_conf", {})

        self.life_conf = unified_conf
        self.history_conf = unified_conf
        self.memory_conf = unified_conf

        self.image_conf = self.config.get("image_conf", {})
        self.tts_conf = self.config.get("tts_conf", {})
        self.daily_life_bridge = daily_life_bridge or DailyLifeBridge(context_obj)

        self.memory = ContextMemoryService(self)
        self.analysis = ContextHistoryAnalysisService(self)
        self.normalize = ContextHistoryNormalizeService(self)
        self.conversation = ContextHistoryConversationFetchService(self)
        self.platform_history = ContextHistoryPlatformFetchService(self)
        self.onebot_history = ContextHistoryOnebotFetchService(self)
        self.history_router = ContextHistoryFetchRouterService(self)
        self.life_memory = ContextLifeMemoryService(self)
        self.life_parse = ContextLifeParseService(self)
        self.life_format = ContextLifeFormatService(self)
        self.life_plugin = ContextLifePluginService(self)
        self.tts = ContextTtsService(self)

    async def record_bot_reply_to_history(self, *args, **kwargs):
        return await self.memory.record_bot_reply_to_history(*args, **kwargs)

    async def record_external_share(self, *args, **kwargs):
        return await self.memory.record_external_share(*args, **kwargs)

    def format_structured_history_context(self, *args, **kwargs):
        return self.analysis.format_structured_history_context(*args, **kwargs)

    def check_group_strategy(self, *args, **kwargs):
        return self.analysis.check_group_strategy(*args, **kwargs)

    async def get_history_data(self, *args, **kwargs):
        return await self.history_router.get_history_data(*args, **kwargs)

    def format_life_context(self, *args, **kwargs):
        return self.life_format.format_life_context(*args, **kwargs)

    async def get_life_context(self, target_umo: str = ""):
        return await self.life_plugin.get_life_context(target_umo)

    async def text_to_speech(self, *args, **kwargs):
        return await self.tts.text_to_speech(*args, **kwargs)

    def is_group_chat(self, target_umo: str) -> bool:
        """按框架的统一消息来源标识判断群聊。"""
        session = parse_platform_session(target_umo)
        return bool(session and session.is_group)

    def parse_umo(self, target_umo: str):
        """解析运行时会话标识。"""
        session = parse_platform_session(target_umo)
        if session:
            return session.platform_id, session.session_id
        return None, None

    def is_onebot_platform(self, adapter_id: str) -> bool:
        return str(adapter_id or "").strip().lower() in ONEBOT_PLATFORM_TYPES

    def is_onebot_adapter(self, adapter_id: str) -> bool:
        """按平台类型或适配器实例元数据判断 OneBot。"""
        if self.is_onebot_platform(adapter_id):
            return True
        return self._onebot_bot_for_adapter(adapter_id) is not None

    def is_onebot_event(self, event) -> bool:
        try:
            return self.is_onebot_platform(event.get_platform_name())
        except Exception:
            return False

    def _get_history_max_count(
        self, is_group: bool, group_default: int = 50, private_default: int = 20
    ) -> int:
        default = group_default if is_group else private_default
        key = "deep_history_max_count" if is_group else "private_history_count"
        try:
            return max(0, int(self.history_conf.get(key, default)))
        except Exception:
            return default

    def is_weixin_event(self, event) -> bool:
        if not event:
            return False
        try:
            names = [
                str(event.get_platform_name() or ""),
                str(event.get_platform_id() or ""),
            ]
        except Exception as e:
            logger.debug(f"[日常分享] 读取事件平台名失败: {e}")
            return False
        return any(str(name).strip().lower() == "weixin_oc" for name in names)

    def get_onebot_bot(self, target_umo: str = "", event=None, adapter_id: str = ""):
        """获取 QQ 机器人客户端。运行时会话标识第一段是平台标识，不能当成平台类型判断。"""
        if event and self.is_onebot_event(event):
            bot = event.bot
            if bot:
                return bot

        if adapter_id and self.is_onebot_platform(adapter_id):
            bot = self.get_bot_instance(adapter_id)
            if bot:
                return bot

        target_s = str(target_umo or "").strip()
        umo_adapter_id, real_id = self.parse_umo(target_s)
        bot = self._onebot_bot_for_adapter(umo_adapter_id)
        if bot:
            return bot
        if umo_adapter_id:
            return None

        probe = real_id or target_s
        if str(probe).isdigit():
            inst = find_platform_instance_by_types(self.context, ONEBOT_PLATFORM_TYPES)
            bot = get_platform_client(inst)
            if bot:
                return bot

        return None

    def _onebot_bot_for_adapter(self, adapter_id: str):
        if not adapter_id:
            return None
        try:
            matches = [
                binding
                for binding in get_platform_bindings(self.context)
                if adapter_id in {binding.platform_id, binding.route_id}
                and self.is_onebot_platform(binding.platform_type)
            ]
            if len(matches) == 1 and not matches[0].conflicted:
                return get_platform_client(matches[0].instance)
        except Exception as exc:
            logger.debug(f"[日常分享] 读取 OneBot 适配器实例失败: {exc}")
        return None

    async def call_onebot_action(self, bot, action: str, **params):
        try:
            return await asyncio.wait_for(
                bot.call_action(action=action, **params),
                timeout=ONEBOT_API_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise TimeoutError(
                f"OneBot 操作 {action} 超时（{ONEBOT_API_TIMEOUT_SECONDS}秒）"
            ) from exc

    def is_weixin_platform(self, target_umo: str) -> bool:
        raw = str(target_umo or "").lower()
        adapter_id, real_id = self.parse_umo(raw)
        session_id = real_id or raw
        return (
            session_id.endswith("@im.wechat")
            or session_id.endswith("@chatroom")
            or bool(adapter_id and adapter_id.strip().lower() == "weixin_oc")
        )

    async def init_bots(self):
        """
        初始化机器人实例缓存
        """
        logger.debug("[日常分享] 正在初始化机器人实例缓存...")
        try:
            self.bot_map.clear()
            count = 0
            for binding in get_platform_bindings(self.context):
                if binding.conflicted:
                    logger.error(
                        f"[日常分享] 同平台机器人实例 ID 重复，已停止缓存: {binding.platform_id}（{binding.platform_type}）"
                    )
                    continue
                platform = binding.instance
                bot_client = get_platform_client(platform)
                route_id = binding.route_id
                if bot_client and route_id:
                    self.bot_map[route_id] = bot_client
                    count += 1
                    logger.debug(
                        f"[日常分享] 发现并缓存机器人实例: {binding.platform_id}（{binding.platform_type}），实例类型: {type(bot_client).__name__}"
                    )

            logger.debug(f"[日常分享] 机器人缓存初始化完成，共发现 {count} 个实例。")

        except Exception as e:
            logger.error(f"[日常分享] 机器人初始化失败: {e}")

    def get_bot_instance(self, adapter_id: str):
        """
        从缓存中获取机器人实例
        """
        if adapter_id:
            return self.bot_map.get(adapter_id)

        if len(self.bot_map) == 1:
            return next(iter(self.bot_map.values()))
        if self.bot_map:
            logger.warning(
                f"[日常分享] 存在多个机器人实例 {list(self.bot_map.keys())}，必须明确指定实例 ID"
            )
            return None

        logger.debug("[日常分享] 当前机器人缓存为空，可能仍在等待适配器初始化。")
        return None

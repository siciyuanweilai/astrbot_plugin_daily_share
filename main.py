import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools

from .core.commands import CommandHandler
from .core.container import PluginServices
from .core.content import ContentService
from .core.context import ContextService
from .core.db import DatabaseManager
from .core.host.lifecycle import RuntimeService
from .core.host.model import LlmService
from .core.image import ImageService
from .core.integrations import DailyLifeBridge
from .core.news import NewsService
from .core.panel import PAGE_PREFERENCES_FILE, DashboardService
from .core.panel.common import (
    _PAGE_MEDIA_CACHE_SECONDS as _PAGE_MEDIA_CACHE_SECONDS,
)
from .core.space import QzoneService
from .core.support import SupportService
from .core.tasks import TaskManager


class DailySharePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.scheduler = AsyncIOScheduler()

        # 配置引用
        self.basic_conf = self.config.get("basic_conf", {})
        self.image_conf = self.config.get("image_conf", {})
        self.tts_conf = self.config.get("tts_conf", {})
        self.qzone_conf = self.config.get("qzone_conf", {})
        self.receiver_conf = self.config.get("receiver", {})
        self.extra_shares_conf = self.config.get("extra_shares", {})
        self.context_conf = self.config.get("context_conf", {})
        self.news_conf = self.config.get("news_conf", {})
        self.contact_aliases = self.config.get("contact_aliases", [])

        # 分享内容记录条数
        self.history_limit = 100

        # 锁与防抖
        self._lock = asyncio.Lock()
        self._target_locks = {}

        # 生命周期标志位
        self._is_initialized = False
        self._is_terminated = False
        self._runtime_state = "created"
        self._runtime_error = ""

        # 缓存适配器标识
        self._cached_adapter_id = None
        self._cached_qq_adapter_id = None
        self._cached_weixin_adapter_id = None

        # 任务追踪 (用于生命周期清理)
        self._bg_tasks = set()

        # 数据路径
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_daily_share")

        self.page_preferences_file = self.data_dir / PAGE_PREFERENCES_FILE

        # 数据库初始化
        self.db = DatabaseManager(self.data_dir, initialize=False)

        # 初始化服务层
        self.daily_life_bridge = DailyLifeBridge(context)
        self.ctx_service = ContextService(context, config, self.daily_life_bridge)
        self.qzone_service = QzoneService(self)
        self.news_service = NewsService(config)
        self.llm_service = LlmService(
            context,
            self.basic_conf,
            lambda: self._is_terminated,
        )
        self.image_service = ImageService(
            context, config, self.llm_service.call, self.daily_life_bridge
        )

        # 初始化内容服务
        self.content_service = ContentService(
            config,
            self.llm_service.call,
            context,
            self.db,
            self.news_service,
            self.daily_life_bridge,
        )

        self.services = PluginServices(
            scheduler=self.scheduler,
            db=self.db,
            ctx_service=self.ctx_service,
            news_service=self.news_service,
            image_service=self.image_service,
            content_service=self.content_service,
            qzone_service=self.qzone_service,
            lock=self._lock,
            target_locks=self._target_locks,
            basic_conf=self.basic_conf,
            extra_shares_conf=self.extra_shares_conf,
            qzone_conf=self.qzone_conf,
            image_conf=self.image_conf,
            tts_conf=self.tts_conf,
            context_conf=self.context_conf,
            receiver_conf=self.receiver_conf,
            daily_life_bridge=self.daily_life_bridge,
        )

        # 核心逻辑解耦器
        self.task_manager = TaskManager(self)
        self.runtime_service = RuntimeService(self)
        self.support_service = SupportService(self)
        self.command_handler = CommandHandler(self.support_service)
        self.dashboard_service = DashboardService(self)

    async def initialize(self) -> None:
        try:
            await self.dashboard_service.load_config_schema()
            await self.runtime_service.initialize()
            self.dashboard_service.register_web_apis()
        except BaseException:
            self.dashboard_service.shutdown()
            if not self._is_terminated:
                await self.runtime_service.terminate()
            raise

    async def terminate(self) -> None:
        try:
            await self.runtime_service.terminate()
        finally:
            self.dashboard_service.shutdown()

    def track_task(self, coro):
        return self.runtime_service.track_task(coro)

    async def cancel_background_tasks(self, *, timeout: float = 5.0) -> None:
        await self.runtime_service.cancel_background_tasks(timeout=timeout)

    def get_share_lock(
        self, target_uid: str | None = None, *, global_scope: bool = False
    ):
        return self.runtime_service.get_share_lock(
            target_uid, global_scope=global_scope
        )

    def is_share_busy(
        self, target_uid: str | None = None, *, global_scope: bool = False
    ) -> bool:
        return self.runtime_service.is_share_busy(target_uid, global_scope=global_scope)

    def release_idle_share_lock(self, target_uid: str | None = None) -> None:
        self.runtime_service.release_idle_share_lock(target_uid)

    async def save_config_file(self) -> None:
        await self.runtime_service.save_config_file()

    def emit_dashboard_event(
        self, event_type: str = "status", data: dict | None = None
    ) -> None:
        self.dashboard_service.emit_dashboard_event(event_type, data)

    async def publish_qzone(self, text: str = "", images: list | None = None):
        return await self.support_service.publish_qzone(text=text, images=images)

    def target_entry_matches(
        self, item, origin: str, real_id: str, candidates: set[str]
    ) -> bool:
        return self.support_service.target_entry_matches(
            item, origin, real_id, candidates
        )

    def get_contact_alias(
        self, target_uid: str, event: AstrMessageEvent | None = None
    ) -> str:
        """读取目标联系人别名，供任务目标解析统一调用。"""
        return self.support_service.get_contact_alias(target_uid, event=event)

    def set_contact_alias(
        self, target_uid: str, alias: str, event: AstrMessageEvent | None = None
    ) -> str:
        """保存目标联系人别名，保持插件入口与服务实现一致。"""
        return self.support_service.set_contact_alias(target_uid, alias, event=event)

    def remove_contact_alias(
        self, target_uid: str, event: AstrMessageEvent | None = None
    ) -> list:
        """删除目标联系人别名，供命令和面板共用。"""
        return self.support_service.remove_contact_alias(target_uid, event=event)

    async def save_config_and_refresh_runtime(
        self,
        *,
        clear_pending_when_disabled: bool = False,
        mutation=None,
        rebuild_scheduler: bool = True,
    ):
        return await self.dashboard_service.save_config_and_refresh_runtime(
            clear_pending_when_disabled=clear_pending_when_disabled,
            mutation=mutation,
            rebuild_scheduler=rebuild_scheduler,
        )

    async def call_llm(
        self,
        prompt: str,
        system_prompt: str | None = None,
        timeout: int = 60,
        max_retries: int = 2,
        tools: list | None = None,
        umo: str | None = None,
    ):
        return await self.llm_service.call(
            prompt=prompt,
            system_prompt=system_prompt,
            timeout=timeout,
            max_retries=max_retries,
            tools=tools,
            umo=umo,
        )

    @filter.llm_tool(name="daily_share")
    async def daily_share_tool(
        self,
        event: AstrMessageEvent,
        share_type: str,
        source: str | None = None,
        get_image: bool = True,
        need_image: bool = False,
        need_video: bool = False,
        need_voice: bool = False,
        to_qzone: bool = False,
    ):
        """
        生成并发送每日分享内容。
        用于明确的主动分享请求，可生成文字、新闻长图、AI 配图、视频或语音，也可发布到 QQ 空间。
        不用于普通聊天、开放问答或未要求发送/分享的内容讨论。

        Args:
            share_type (string): 标准分享类型。支持：自动、问候、新闻、心情、知识、推荐、60秒新闻、AI 资讯。无法确定时填自动。
            source (string): 新闻源名称，仅新闻类型有效；未指定新闻源时留空。
            get_image (boolean): 新闻类型是否优先发送热搜长图；需要文字新闻时设为否。
            need_image (boolean): 是否生成 AI 配图。
            need_video (boolean): 是否生成 AI 视频；QQ 空间发布不支持视频。
            need_voice (boolean): 是否生成语音。
            to_qzone (boolean): 是否发布到 QQ 空间。
        """
        return await self.support_service.run_daily_share_tool(
            event,
            share_type,
            source,
            get_image,
            need_image,
            need_video,
            need_voice,
            to_qzone,
        )

    @filter.on_llm_request(priority=-1000)
    async def inject_tool_context(self, event: AstrMessageEvent, req):
        """在模型请求前注入临时工具上下文，帮助大语言模型稳定调用缓存型工具。"""
        await self.support_service.inject_tool_context(event, req)

    @filter.llm_tool(name="news_link")
    async def news_link_tool(
        self,
        event: AstrMessageEvent,
        action: str = "link",
        index: str = "",
        query: str = "",
        source: str | None = None,
        source_explicit: bool = False,
        to_qzone: bool = False,
    ):
        """
        查询最近新闻分享缓存中的链接、摘要、来源或可查询列表。
        用于新闻分享后的后续查询，不用于重新生成新闻分享。
        序号、新闻源和查询词由大语言模型理解用户意图后转换为结构化参数。


        Args:
            action (string): 标准查询动作。link 表示链接；summary 表示摘要或详情；source 表示来源；list 表示可查询列表。无法确定时填 link。
            index (string): 本轮用户明确说出的新闻序号，使用阿拉伯数字字符串；必须与用户原话一致，不得根据标题、历史或列表内容改成其他序号；没有明确序号时留空；不得与 query 同时填写。
            query (string): 标题查询内容；本轮用户已经明确说出序号时必须留空；不得与 index 同时填写。
            source (string): 新闻源名称；本轮没有明确指定新闻源时留空。
            source_explicit (boolean): source 是否来自本轮明确指定。
            to_qzone (boolean): 是否查询最近一次 QQ 空间新闻缓存。
        """
        return await self.support_service.query_news_link(
            event,
            action=action,
            index=index,
            query=query,
            source=source,
            source_explicit=source_explicit,
            to_qzone=to_qzone,
        )

    @filter.llm_tool(name="qzone")
    async def qzone_tool(
        self,
        event: AstrMessageEvent,
        action: str = "list",
        post_id: str = "",
        target_id: str = "",
        content: str = "",
        images: list | None = None,
        pos: int = 0,
        num: int = 5,
    ):
        """
        QQ 空间说说工具：查看、详情、发布、点赞、评论。
        动作选择：list=获取最新列表；comment=直发用户给出的原话；auto_comment=让机器人按自动评论配置代写，支持正文配图和转发配图；publish=发布说说。
        所有权：用户说“我的说说”指当前说话用户的 QQ 空间；只有明确说“你的/机器人自己的说说”才指机器人自己的空间。
        串台边界：好友动态续评用 qzone_auto_interact.comment；机器人自己说说的评论回评用 qzone_auto_interact.reply。
        权限：普通用户只能查看、详情、点赞、评论自己 QQ 号的说说；发布和操作其他 QQ 号仅管理员可用。

        Args:
            action (string): 标准动作枚举。list 表示查看说说；detail 表示查看详情；publish 表示发布文字或图片说说；like 表示点赞指定说说；comment 表示按用户给出的正文直发一级评论；auto_comment 表示对指定说说自动生成并发送一级评论。只能填写 list、detail、publish、like、comment、auto_comment。
            post_id (string): 说说 ID，来自 list/detail 返回中的 ID，格式为 uin:tid。点赞、评论、自动评论、详情必填。
            target_id (string): 可选，要查看的 QQ 号。留空表示查看自己的 QQ 空间说说；填 QQ 号表示查看该 QQ 空间说说。
            content (string): 发布说说或评论的正文。publish/comment 必填。comment 时必须是用户明确要求发送的原文；需要模型代写评论时不要填写本参数直发，改用 action=auto_comment。
            images (list): 发布说说附带的图片路径或图片 URL 列表，可留空。
            pos (number): 查看说说起始位置，默认 0。
            num (number): 查看说说数量，默认 5，最多 10。
        """
        return await self.support_service.run_qzone_tool(
            event,
            action=action,
            post_id=post_id,
            target_id=target_id,
            content=content,
            images=images,
            pos=pos,
            num=num,
        )

    @filter.llm_tool(name="qzone_auto_interact")
    async def qzone_auto_interact_tool(
        self,
        event: AstrMessageEvent,
        action: str = "all",
        target_id: str = "",
    ):
        """
        QQ 空间自动互动扫描工具。
        动作选择：like=自动点赞；comment=好友动态自动评论/续评；reply=机器人自己说说的评论回评；all=管理员全局自动互动。
        单条说说固定评论用 qzone.comment；单条说说自动生成一级评论用 qzone.auto_comment。
        所有权：用户说“我的说说”时 target_id 填该用户 QQ；reply 只在明确指向“你的/机器人自己的说说”时使用。
        权限：普通用户只能触发 like/comment 且 target_id 为自己的 QQ；管理员可触发全局自动互动。

        Args:
            action (string): 标准动作枚举。all 表示执行全部已启用子任务；like 表示只执行自动点赞；comment 表示只执行好友动态自动评论和续评；reply 表示只执行自己说说评论回评。只能填写 all、like、comment、reply。
            target_id (string): 可选，要定向扫描的 QQ 号；普通用户触发“点赞/评论/回评我的说说”时填写自己的 QQ，管理员留空表示全局扫描。
        """
        return await self.support_service.run_qzone_auto_interaction_tool(
            event, action=action, target_id=target_id
        )

    @filter.on_llm_response(priority=-10000)
    async def clean_news_link_llm_references(self, event: AstrMessageEvent, resp):
        """保留大语言模型自然回复，只移除 news_link 场景下模型补出的参考链接尾部。"""
        await self.support_service.clean_news_link_llm_references(event, resp)

    @filter.on_decorating_result(priority=-10000)
    async def clean_news_link_decorating_references(self, event: AstrMessageEvent):
        """发送前清理参考链接尾部，但不覆盖大语言模型正文。"""
        await self.support_service.clean_news_link_decorating_references(event)

    @filter.permission_type(filter.PermissionType.MEMBER)
    @filter.command("分享")
    async def handle_share_main(self, event: AstrMessageEvent):
        """每日分享统一命令入口。"""
        async for result in self.support_service.handle_share_command(event):
            yield result

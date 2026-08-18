import asyncio

from .components import TaskConfigState, TaskServices, TaskSharedState
from .runtime import TaskRuntime


class TaskManager:
    """持有任务服务，不承载或动态代理业务方法。"""

    def __init__(self, plugin):
        self.runtime = TaskRuntime.from_plugin(plugin)
        self.config = TaskConfigState.from_runtime(self.runtime)
        self.state = TaskSharedState(
            qzone_auto_interaction_lock=asyncio.Lock(),
            briefing_share_lock=asyncio.Lock(),
        )
        self.services = TaskServices.build(self.runtime, self.config, self.state)

        self.snapshot_store = self.services.snapshots
        self.targets = self.services.targets
        self.schedule = self.services.schedule
        self.progress = self.services.progress
        self.qzone_interaction = self.services.qzone_interaction
        self.executor_helpers = self.services.executor_helpers
        self.type_selector = self.services.type_selector
        self.briefing = self.services.briefing
        self.qzone_share = self.services.qzone_share
        self.command_share = self.services.command_share
        self.share = self.services.share
        self.delivery_assets = self.services.delivery_assets
        self.weixin_delivery = self.services.weixin_delivery
        self.delivery = self.services.delivery
        self.xiaohongshu_share = self.services.xiaohongshu_share

    def update_configs(
        self,
        *,
        basic: dict | None = None,
        extra_shares: dict | None = None,
        qzone: dict | None = None,
        image: dict | None = None,
        tts: dict | None = None,
        context: dict | None = None,
        receiver: dict | None = None,
        xiaohongshu: dict | None = None,
    ) -> None:
        """原子替换所有任务服务读取的配置引用。"""

        if basic is not None:
            self.config.basic = basic
        if extra_shares is not None:
            self.config.extra_shares = extra_shares
        if qzone is not None:
            self.config.qzone = qzone
        if image is not None:
            self.config.image = image
        if tts is not None:
            self.config.tts = tts
        if context is not None:
            self.config.context = context
        if receiver is not None:
            self.config.receiver = receiver
        if xiaohongshu is not None:
            self.config.xiaohongshu = xiaohongshu

    @property
    def qzone_auto_interaction_lock(self):
        """QQ 空间自动互动的全局互斥锁。"""
        return self.state.qzone_auto_interaction_lock

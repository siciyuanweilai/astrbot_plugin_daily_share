from __future__ import annotations


class SchedulerComponent:
    """调度组件访问任务运行时与其他调度组件的显式契约。"""

    def __init__(self, schedule):
        self.schedule = schedule

    @property
    def services(self):
        return self.schedule.services

    @property
    def state(self):
        """读取任务管理器持有的共享运行状态。"""
        return self.schedule.state

    @property
    def plugin(self):
        return self.schedule.plugin

    @property
    def scheduler(self):
        return self.schedule.scheduler

    @property
    def db(self):
        return self.schedule.db

    @property
    def ctx_service(self):
        return self.schedule.ctx_service

    @property
    def content_service(self):
        return self.schedule.content_service

    @property
    def _lock(self):
        return self.schedule._lock

    @property
    def _qzone_auto_interaction_lock(self):
        return self.schedule._qzone_auto_interaction_lock

    @property
    def _briefing_share_lock(self):
        return self.schedule._briefing_share_lock

    @property
    def basic_conf(self):
        return self.schedule.basic_conf

    @property
    def extra_shares_conf(self):
        return self.schedule.extra_shares_conf

    @property
    def qzone_conf(self):
        return self.schedule.qzone_conf

    @property
    def xiaohongshu_conf(self):
        return self.schedule.xiaohongshu_conf

    @property
    def receiver_conf(self):
        return self.schedule.receiver_conf


__all__ = ["SchedulerComponent"]

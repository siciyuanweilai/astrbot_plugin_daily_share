from __future__ import annotations

from ..panelcomponent import PanelComponent

from ..common import _PAGE_RECENT_SHARE_LIMIT
from ...config import NEWS_SOURCE_MAP


class DashboardRouteStatusService(PanelComponent):
    async def _build_page_status(self) -> dict:
        period = self.task_manager.executor_helpers.get_curr_period()
        qzone_status = await self.qzone_service.status()
        targets = await self.targets._page_targets()
        jobs = self.jobs._page_jobs(targets)
        target_stats = await self.db.get_target_stats(days=30, briefing=False)
        briefing_target_stats = await self.db.get_target_stats(days=30, briefing=True)
        await self.targets._enrich_page_targets(
            targets, target_stats, briefing_target_stats
        )
        history = await self.labels._page_prepare_history_items(
            await self.db.get_recent_history(limit=_PAGE_RECENT_SHARE_LIMIT)
        )
        failures = await self.labels._page_prepare_history_items(
            await self.db.get_recent_failures(limit=6)
        )
        dynamic_days = self.media_page._page_dashboard_dynamic_days()
        history_summary = await self.db.get_history_summary()
        history_summary.update(
            await self.db.get_dashboard_dynamic_summary(days=dynamic_days)
        )
        history_summary["dashboard_dynamic_days"] = dynamic_days
        media_page = await self.media_page._page_media_page(9, days=dynamic_days)
        preferences = await self.server._load_page_preferences()
        runtime_status = self.plugin.runtime_service.runtime_status()
        return {
            "ok": True,
            "data": {
                "enabled": bool(self.config.get("enable_auto_share", False)),
                "terminated": self._is_terminated,
                "runtime": runtime_status,
                "busy": self.is_share_busy(global_scope=True),
                "preferences": preferences,
                "scheduler": {
                    "running": bool(self.scheduler.running),
                    "job_count": len(jobs),
                    "jobs": jobs,
                    "calendar": self.jobs._page_calendar(jobs),
                },
                "period": {
                    "key": period.value,
                    "range": self.task_manager.executor_helpers.get_period_range_str(
                        period
                    ),
                },
                "config": {
                    "trigger_mode": self.basic_conf.get("trigger_mode", "llm_smart"),
                    "fixed_times": list(
                        self.basic_conf.get("fixed_times") or ["08:00", "20:00"]
                    ),
                    "random_periods": list(
                        self.basic_conf.get("random_periods")
                        or ["08:00-10:00", "19:00-21:00"]
                    ),
                    "share_cron": self.basic_conf.get("share_cron", "0 8,20 * * *"),
                    "smart_schedule_max_count": int(
                        self.basic_conf.get("smart_schedule_max_count", 2) or 2
                    ),
                    "smart_schedule_quiet_hours": list(
                        self.basic_conf.get(
                            "smart_schedule_quiet_hours", ["23:30-07:30"]
                        )
                        or []
                    ),
                    "share_type": self.basic_conf.get("share_type", "自动"),
                    "qzone_enabled": bool(self.qzone_conf.get("enable_qzone", False)),
                    "qzone_trigger_mode": self.qzone_conf.get(
                        "qzone_trigger_mode", "llm_smart"
                    ),
                    "qzone_fixed_times": list(
                        self.qzone_conf.get("qzone_fixed_times") or ["20:00"]
                    ),
                    "qzone_random_periods": list(
                        self.qzone_conf.get("qzone_random_periods") or ["19:00-21:00"]
                    ),
                    "qzone_cron": self.qzone_conf.get("qzone_cron", "0 20 * * *"),
                    "qzone_smart_schedule_max_count": int(
                        self.qzone_conf.get("qzone_smart_schedule_max_count", 1) or 1
                    ),
                    "qzone_smart_schedule_quiet_hours": list(
                        self.qzone_conf.get(
                            "qzone_smart_schedule_quiet_hours", ["23:30-07:30"]
                        )
                        or []
                    ),
                    "ai_image_enabled": bool(
                        self.image_conf.get("enable_ai_image", False)
                    ),
                    "ai_video_enabled": bool(
                        self.image_conf.get("enable_ai_video", False)
                    ),
                    "tts_enabled": bool(self.tts_conf.get("enable_tts", False)),
                    "web_search_enabled": bool(
                        self.news_conf.get("enable_web_search", True)
                    ),
                    "web_search_available": bool(
                        self.content_service.daily_life_bridge.search_available()
                    ),
                    "briefing_60s": bool(
                        self.extra_shares_conf.get("enable_60s_news", False)
                    ),
                    "briefing_ai": bool(
                        self.extra_shares_conf.get("enable_ai_news", False)
                    ),
                    "briefing_qzone_sync": bool(
                        self.extra_shares_conf.get("sync_briefing_to_qzone", False)
                    ),
                    "briefing_schedule_mode": self.extra_shares_conf.get(
                        "briefing_schedule_mode", "llm_smart"
                    ),
                    "briefing_fixed_times": list(
                        self.extra_shares_conf.get("briefing_fixed_times") or ["08:00"]
                    ),
                    "briefing_random_periods": list(
                        self.extra_shares_conf.get("briefing_random_periods")
                        or ["08:00-09:00"]
                    ),
                    "cron_briefing": self.extra_shares_conf.get(
                        "cron_briefing", "0 8 * * *"
                    ),
                    "briefing_smart_schedule_max_count": int(
                        self.extra_shares_conf.get(
                            "briefing_smart_schedule_max_count", 1
                        )
                        or 1
                    ),
                    "briefing_smart_schedule_quiet_hours": list(
                        self.extra_shares_conf.get(
                            "briefing_smart_schedule_quiet_hours", ["23:30-07:30"]
                        )
                        or []
                    ),
                },
                "targets": targets,
                "target_platforms": [
                    option
                    for option in self.meta._page_adapter_options()
                    if str(option.get("value") or "").strip()
                ],
                "states": await self.activity._page_states(),
                "qzone": {
                    "available": bool(qzone_status.get("available")),
                    "configured": bool(qzone_status.get("configured")),
                    "uin": qzone_status.get("uin", 0),
                    "nickname": qzone_status.get("nickname", ""),
                    "error": qzone_status.get("error", ""),
                },
                "news_sources": [
                    {
                        "key": key,
                        "name": str(value.get("name") or key),
                    }
                    for key, value in NEWS_SOURCE_MAP.items()
                ],
                "history": history,
                "history_summary": history_summary,
                "failures": failures,
                "media": media_page["items"],
                "media_limit": media_page["limit"],
                "media_has_more": media_page["has_more"],
                "progress": self.task_manager.progress.get_share_progress_snapshot(),
                "target_stats": target_stats,
                "briefing_target_stats": briefing_target_stats,
                "actions": self.activity._page_recent_actions(),
                "recent_shares": self.activity._page_recent_shares(history, targets),
            },
        }

    async def page_status(self):
        return await self.server._page_json(self.status_routes._build_page_status)

import re

from .panelcomponent import PanelComponent

CALENDAR_DELAYED_SOURCE_JOB_IDS = {
    "delayed_auto_share": "auto_share",
    "delayed_qzone_share": "qzone_share",
    "delayed_qzone_auto_interaction": "qzone_auto_interaction",
    "delayed_briefing_share": "share_briefing",
}


class DashboardJobsService(PanelComponent):
    """仪表盘任务和日历数据。"""

    def _page_job_display_name(
        self,
        job_id: str,
        job_name: str = "",
        target_labels: dict | None = None,
        random_share_label: str = "",
    ) -> str:
        job_id = str(job_id or "")
        job_name = str(job_name or "")
        target_labels = target_labels or {}

        def clean_smart_name(value: str) -> str:
            return re.sub(
                r"(智能定时)\s+\d{1,2}:\d{2}(?=\s*·|$)", r"\1", str(value or "")
            ).strip()

        static_names = {
            "auto_share": "全局定时分享",
            "qzone_share": "QQ 空间定时分享",
            "qzone_auto_interaction": "QQ 空间自动互动",
            "share_briefing": "早报分享",
            "weixin_temp_cleanup": "微信临时图片清理",
            "news_image_cleanup": "新闻源图片清理",
            "daily_random_scheduler": "每日随机分享排程",
            "daily_qzone_random_scheduler": "每日 QQ 空间随机排程",
            "daily_smart_scheduler": "每日智能分享排程",
            "daily_briefing_smart_scheduler": "每日早报智能排程",
            "daily_qzone_smart_scheduler": "每日 QQ 空间智能排程",
            "delayed_auto_share": "全局分享延迟分享",
            "delayed_qzone_share": "QQ 空间延迟分享",
            "delayed_qzone_auto_interaction": "QQ 空间自动互动延迟",
            "delayed_briefing_share": "早报延迟分享",
            "resume_auto_share": "恢复全局延迟分享",
            "resume_qzone_share": "恢复 QQ 空间延迟分享",
            "resume_briefing_share": "恢复早报延迟分享",
        }
        if job_id in static_names:
            return static_names[job_id]

        patterns = (
            (r"^auto_share_fixed_(\d+)$", "auto_share_fixed", 1, False),
            (r"^share_briefing_fixed_(\d+)$", "briefing_fixed", 1, False),
            (r"^qzone_share_fixed_(\d+)$", "qzone_fixed", 1, False),
            (r"^random_share_(\d+)$", "random", 1, False),
            (r"^qzone_random_share_(\d+)$", "qzone_random", 1, False),
            (r"^smart_share_(\d+)$", "smart", 1, False),
            (r"^briefing_smart_share_(\d+)$", "briefing_smart", 1, False),
            (r"^qzone_smart_share_(\d+)$", "qzone_smart", 1, False),
            (r"^custom_share_(.+)$", "custom", 0, True),
            (r"^delayed_custom_share_(.+)$", "custom_delayed", 0, True),
            (r"^resume_custom_share_(.+)$", "custom_resume", 0, True),
        )
        for pattern, kind, offset, is_target in patterns:
            match = re.match(pattern, job_id)
            if not match:
                continue
            value = match.group(1)
            if job_id.startswith("random_share_") and random_share_label:
                return f"{random_share_label} · 随机分享"
            if is_target:
                value = target_labels.get(value, value)
            elif offset:
                try:
                    value = str(int(value) + offset)
                except ValueError:
                    pass
            smart_fallbacks = {
                "smart": f"全局智能定时 {value}",
                "briefing_smart": f"早报智能定时 {value}",
                "qzone_smart": f"QQ 空间 · 智能定时 {value}",
            }
            if kind in smart_fallbacks:
                return clean_smart_name(job_name) or smart_fallbacks[kind]
            templates = {
                "auto_share_fixed": "全局固定时间 {value}",
                "briefing_fixed": "早报固定时间 {value}",
                "qzone_fixed": "QQ 空间固定时间 {value}",
                "random": "随机分享 {value}",
                "qzone_random": "QQ 空间 · 随机分享 {value}",
                "custom": "{value} · 独立分享",
                "custom_delayed": "{value} · 延迟独立分享",
                "custom_resume": "{value} · 恢复延迟独立分享",
            }
            return templates[kind].format(value=value)

        return job_name or job_id or "任务"

    def _page_jobs(self, targets: dict | None = None) -> list:
        jobs = []
        targets = targets or {}
        target_labels = self.labels._page_target_label_map(targets)
        random_share_label = self.labels._page_random_share_target_label(targets)
        for job in self.scheduler.get_jobs():
            next_run_time = getattr(job, "next_run_time", None)
            job_id = str(getattr(job, "id", ""))
            job_name = str(getattr(job, "name", ""))
            jobs.append(
                {
                    "id": job_id,
                    "name": job_name,
                    "display_name": self.jobs._page_job_display_name(
                        job_id, job_name, target_labels, random_share_label
                    ),
                    "trigger": str(getattr(job, "trigger", "")),
                    "next_run_time": (
                        next_run_time.isoformat(timespec="seconds")
                        if next_run_time
                        else ""
                    ),
                }
            )
        return sorted(jobs, key=lambda item: item["next_run_time"] or "9999")

    def _page_calendar_hidden_source_jobs(self, jobs: list) -> set[str]:
        next_run_by_id = {
            str(job.get("id") or ""): str(job.get("next_run_time") or "")
            for job in jobs
            if str(job.get("id") or "") and str(job.get("next_run_time") or "")
        }
        hidden = set()

        def hide_source_when_delayed(source_id: str, delayed_id: str):
            source_time = next_run_by_id.get(source_id, "")
            delayed_time = next_run_by_id.get(delayed_id, "")
            if source_time and delayed_time and source_time <= delayed_time:
                hidden.add(source_id)

        for delayed_id, source_id in CALENDAR_DELAYED_SOURCE_JOB_IDS.items():
            hide_source_when_delayed(source_id, delayed_id)

        for delayed_id in next_run_by_id:
            if delayed_id.startswith("delayed_custom_share_"):
                source_id = "custom_share_" + delayed_id.removeprefix(
                    "delayed_custom_share_"
                )
                hide_source_when_delayed(source_id, delayed_id)

        return hidden

    def _page_calendar(self, jobs: list) -> list:
        calendar: dict[str, list] = {}
        hidden_source_jobs = self.jobs._page_calendar_hidden_source_jobs(jobs)
        for job in jobs:
            if str(job.get("id") or "") in hidden_source_jobs:
                continue
            next_run_time = str(job.get("next_run_time") or "")
            if not next_run_time:
                continue
            date_key = next_run_time[:10]
            time_key = next_run_time[11:16] if len(next_run_time) >= 16 else ""
            calendar.setdefault(date_key, []).append(
                {
                    "id": job.get("id", ""),
                    "name": job.get("display_name")
                    or job.get("name")
                    or job.get("id")
                    or "任务",
                    "time": time_key,
                    "next_run_time": next_run_time,
                    "trigger": job.get("trigger", ""),
                }
            )
        return [
            {
                "date": date,
                "items": sorted(items, key=lambda item: item["next_run_time"]),
            }
            for date, items in sorted(calendar.items())
        ]

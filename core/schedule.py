from __future__ import annotations

from dataclasses import dataclass


SCHEDULE_MODE_OPTIONS = frozenset({"fixed_time", "random_period", "llm_smart", "cron"})


@dataclass(frozen=True)
class ScheduleDefinition:
    mode_key: str
    mode_default: str
    mode_label: str
    fixed_key: str
    fixed_default: tuple[str, ...]
    fixed_label: str
    random_key: str
    random_default: tuple[str, ...]
    random_label: str
    cron_key: str
    cron_default: str
    cron_label: str
    smart_max_key: str
    smart_max_default: int
    smart_quiet_key: str
    smart_quiet_default: tuple[str, ...]
    smart_quiet_label: str
    smart_prompt_key: str
    mode_options: frozenset[str] = SCHEDULE_MODE_OPTIONS


GLOBAL_SCHEDULE = ScheduleDefinition(
    mode_key="trigger_mode",
    mode_default="llm_smart",
    mode_label="全局触发模式",
    fixed_key="fixed_times",
    fixed_default=("08:00", "20:00"),
    fixed_label="全局固定时间",
    random_key="random_periods",
    random_default=("08:00-10:00", "19:00-21:00"),
    random_label="全局随机时段",
    cron_key="share_cron",
    cron_default="0 8,20 * * *",
    cron_label="全局高级定时表达式",
    smart_max_key="smart_schedule_max_count",
    smart_max_default=2,
    smart_quiet_key="smart_schedule_quiet_hours",
    smart_quiet_default=("23:30-07:30",),
    smart_quiet_label="全局智能定时勿扰时间",
    smart_prompt_key="smart_schedule_prompt",
)

BRIEFING_SCHEDULE = ScheduleDefinition(
    mode_key="briefing_schedule_mode",
    mode_default="llm_smart",
    mode_label="早报触发模式",
    fixed_key="briefing_fixed_times",
    fixed_default=("08:00",),
    fixed_label="早报固定时间",
    random_key="briefing_random_periods",
    random_default=("08:00-09:00",),
    random_label="早报随机时段",
    cron_key="cron_briefing",
    cron_default="0 8 * * *",
    cron_label="早报高级定时表达式",
    smart_max_key="briefing_smart_schedule_max_count",
    smart_max_default=1,
    smart_quiet_key="briefing_smart_schedule_quiet_hours",
    smart_quiet_default=("23:30-07:30",),
    smart_quiet_label="早报智能定时勿扰时间",
    smart_prompt_key="briefing_smart_schedule_prompt",
)

QZONE_SCHEDULE = ScheduleDefinition(
    mode_key="qzone_trigger_mode",
    mode_default="llm_smart",
    mode_label="空间触发模式",
    fixed_key="qzone_fixed_times",
    fixed_default=("20:00",),
    fixed_label="空间固定时间",
    random_key="qzone_random_periods",
    random_default=("19:00-21:00",),
    random_label="空间随机时段",
    cron_key="qzone_cron",
    cron_default="0 20 * * *",
    cron_label="空间高级定时表达式",
    smart_max_key="qzone_smart_schedule_max_count",
    smart_max_default=1,
    smart_quiet_key="qzone_smart_schedule_quiet_hours",
    smart_quiet_default=("23:30-07:30",),
    smart_quiet_label="空间智能定时勿扰时间",
    smart_prompt_key="qzone_smart_schedule_prompt",
)


__all__ = [
    "BRIEFING_SCHEDULE",
    "GLOBAL_SCHEDULE",
    "QZONE_SCHEDULE",
    "SCHEDULE_MODE_OPTIONS",
    "ScheduleDefinition",
]

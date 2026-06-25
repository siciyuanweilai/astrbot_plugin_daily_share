from datetime import datetime

from ...config import TimePeriod


class TaskHelperPeriodMixin:
    """分享时段辅助。"""

    def get_curr_period(self) -> TimePeriod:
        h = datetime.now().hour
        if 0 <= h < 6:
            return TimePeriod.DAWN
        if 6 <= h < 9:
            return TimePeriod.MORNING
        if 9 <= h < 12:
            return TimePeriod.FORENOON
        if 12 <= h < 14:
            return TimePeriod.NOON
        if 14 <= h < 16:
            return TimePeriod.AFTERNOON
        if 16 <= h < 19:
            return TimePeriod.EVENING
        if 19 <= h < 22:
            return TimePeriod.NIGHT
        return TimePeriod.LATE_NIGHT

    def get_period_range_str(self, period: TimePeriod) -> str:
        """获取时段对应的时间范围。"""
        return {
            TimePeriod.DAWN: "00:00-06:00",
            TimePeriod.MORNING: "06:00-09:00",
            TimePeriod.FORENOON: "09:00-12:00",
            TimePeriod.NOON: "12:00-14:00",
            TimePeriod.AFTERNOON: "14:00-16:00",
            TimePeriod.EVENING: "16:00-19:00",
            TimePeriod.NIGHT: "19:00-22:00",
            TimePeriod.LATE_NIGHT: "22:00-24:00",
        }.get(period, "")

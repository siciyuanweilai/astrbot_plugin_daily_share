import asyncio
import base64
import json
import mimetypes
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from astrbot.api import logger

from ..config import (
    TimePeriod,
    ShareType,
    NEWS_SOURCE_MAP,
    CRON_TEMPLATES,
    SHARE_TYPE_SEQUENCES,
    DEFAULT_KNOWLEDGE_CATS,
    DEFAULT_REC_CATS,
)
from ..constants import CMD_CN_MAP, SOURCE_CN_MAP, TYPE_CN_MAP

try:
    from quart import jsonify as _quart_jsonify
    from quart import request as _quart_request
    from quart import Response as _quart_response
except Exception:
    _quart_jsonify = None
    _quart_request = None
    _quart_response = None

_PAGE_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif"}
_PAGE_VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v", ".avi", ".mkv"}
_PAGE_INLINE_PREVIEW_MAX_BYTES = 8 * 1024 * 1024
_PAGE_THUMBNAIL_MAX_SIDE = 960
_PAGE_VIEW_IMAGE_MAX_SIDE = 2048
_PAGE_MEDIA_CACHE_SECONDS = 7 * 24 * 60 * 60
_PAGE_PREFERENCES_FILE = "dashboard_preferences.json"
_PAGE_PREFERENCES_DEFAULTS = {
    "sakura_enabled": True,
}
_PAGE_SHARE_TYPE_OPTIONS = {"自动", "问候", "新闻", "心情", "知识", "推荐"}
_PAGE_TRIGGER_MODE_OPTIONS = {"fixed_time", "random_period", "llm_smart", "cron"}
_PAGE_BRIEFING_SCHEDULE_MODE_OPTIONS = {"fixed_time", "random_period", "llm_smart", "cron"}
_PAGE_NEWS_RANDOM_MODE_OPTIONS = {"fixed", "random", "config", "time_based"}
_PAGE_CONTEXT_STRATEGY_OPTIONS = {"cautious", "active", "minimal"}
_PAGE_RECENT_ACTION_LIMIT = 1
_PAGE_RECENT_SHARE_LIMIT = 1
_PAGE_SHARE_SOURCE_LABELS = {
    "manual": "手动",
    "scheduled": "定时",
    "smart_schedule": "智能定时",
    "command": "自然语言",
}
_PAGE_BASIC_SEQUENCE_DEFAULTS = {
    f"{period.value}_sequence": list(SHARE_TYPE_SEQUENCES.get(period, []))
    for period in TimePeriod
}
_PAGE_QZONE_SEQUENCE_DEFAULTS = {
    "qzone_dawn_sequence": ["心情"],
    "qzone_morning_sequence": ["问候", "心情"],
    "qzone_forenoon_sequence": ["心情"],
    "qzone_noon_sequence": ["心情"],
    "qzone_afternoon_sequence": ["心情"],
    "qzone_evening_sequence": ["心情"],
    "qzone_night_sequence": ["心情"],
    "qzone_late_night_sequence": ["心情", "问候"],
}
_PAGE_RANDOM_PERIOD_RE = re.compile(
    r"^(?:[01]?\d|2[0-3]):[0-5]\d-(?:[01]?\d|2[0-3]):[0-5]\d$"
)
_PAGE_CLOCK_TIME_RE = re.compile(r"^(?:[01]?\d|2[0-3]):[0-5]\d$")
_PAGE_CONF_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "_conf_schema.json"

PAGE_PREFERENCES_FILE = _PAGE_PREFERENCES_FILE

__all__ = [name for name in globals() if not name.startswith("__")]

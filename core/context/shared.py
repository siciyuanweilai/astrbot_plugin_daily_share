import asyncio
import datetime
import json
import re
import time
from typing import Any, Dict, List, Optional

from astrbot.api import logger

from ..config import ShareType, TimePeriod


DAILY_SHARE_INTERNAL_TRIGGER = "愿此见闻悄然为我启封"
DAILY_SHARE_MEMORY_PROMPT = "每日分享记录"
DAILY_SHARE_SOURCE = "daily_share"

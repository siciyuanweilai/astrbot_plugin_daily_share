import asyncio as asyncio
import datetime as datetime
import json as json
import time as time
from typing import Any as Any
from typing import Dict as Dict  # noqa: UP035
from typing import List as List  # noqa: UP035
from typing import Optional as Optional

from astrbot.api import logger as logger

from ..config import ShareType as ShareType
from ..config import TimePeriod as TimePeriod

DAILY_SHARE_MEMORY_PROMPT = "每日分享记录"
DAILY_SHARE_SOURCE = "daily_share"

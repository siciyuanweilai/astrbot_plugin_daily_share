GLOBAL_STATE_KEY = "global"
QZONE_STATE_KEY = "qzone"
BRIEFING_STATE_KEY = "briefing"
TARGET_STATE_PREFIX = "target_"

GLOBAL_TARGET_ID = "global"
QZONE_TARGET_ID = "qzone_broadcast"
BRIEFING_TARGET_ID = "briefing_broadcast"
BRIEFING_TARGET_ALIASES = ("briefing", BRIEFING_TARGET_ID)

HISTORY_SHARE_BRIEFING = "briefing"
HISTORY_SHARE_QZONE = "qzone"
HISTORY_SHARE_NEWS = "news"

SOURCE_COMMAND = "command"
SOURCE_MANUAL = "manual"
SOURCE_SCHEDULED = "scheduled"
SOURCE_SMART = "smart_schedule"

MEDIA_IMAGE = "image"
MEDIA_VIDEO = "video"
MEDIA_TEXT = "text"


def target_state_key(target_id) -> str:
    return f"{TARGET_STATE_PREFIX}{target_id}"

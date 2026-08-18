from datetime import datetime

from astrbot.api import logger

from ..config import (
    SHARE_TYPE_SEQUENCES,
    XIAOHONGSHU_SHARE_TYPE_SEQUENCES,
    ShareType,
    TimePeriod,
)
from ..constants import normalize_share_type_sequence, normalize_share_type_token
from ..database.keys import (
    GLOBAL_STATE_KEY,
    QZONE_STATE_KEY,
    XIAOHONGSHU_TARGET_ID,
    target_state_key,
)
from .taskbase import TaskServiceBase


class TaskTypeSelectorService(TaskServiceBase):
    """分享类型轮换与时段默认序列选择。"""

    async def decide_type_with_state(
        self,
        current_period: TimePeriod,
        is_qzone: bool = False,
        target_id: str | None = None,
        specific_type: str = "自动",
    ) -> ShareType:
        """带目标标识状态的分享类型决定，支持自定义列表轮换。"""
        if is_qzone:
            state_key = QZONE_STATE_KEY
        else:
            state_key = target_state_key(target_id) if target_id else GLOBAL_STATE_KEY

        state = await self.db.get_share_state(state_key, {})

        if specific_type:
            custom_seq = normalize_share_type_sequence(specific_type, allow_auto=True)

            if custom_seq and custom_seq != ["auto"]:
                idx_key = "custom_sequence_index"
                idx = state.get(idx_key, 0)
                if idx >= len(custom_seq):
                    idx = 0

                selected_str = custom_seq[idx]
                next_idx = (idx + 1) % len(custom_seq)

                await self.db.update_share_state(
                    state_key,
                    {
                        idx_key: next_idx,
                        "last_timestamp": datetime.now().isoformat(),
                    },
                )

                if selected_str != "auto":
                    try:
                        return ShareType(selected_str)
                    except ValueError:
                        logger.warning(
                            f"[日常分享] 自定义序列包含无效分享类型 {selected_str!r}，使用时段默认序列。"
                        )

        default_sequences = SHARE_TYPE_SEQUENCES
        if is_qzone:
            conf_node = self.qzone_conf
            prefix = "qzone_"
        elif target_id == XIAOHONGSHU_TARGET_ID:
            conf_node = self.xiaohongshu_conf
            prefix = "xiaohongshu_"
            default_sequences = XIAOHONGSHU_SHARE_TYPE_SEQUENCES
        else:
            conf_node = self.basic_conf
            prefix = ""
        config_key = f"{prefix}{current_period.value}_sequence"
        seq = conf_node.get(config_key, [])

        if not seq:
            seq = default_sequences.get(current_period, ["问候"])

        idx_key = f"index_{current_period.value}"
        idx = state.get(idx_key, 0)
        if idx >= len(seq):
            idx = 0

        selected = normalize_share_type_token(seq[idx])
        next_idx = (idx + 1) % len(seq)

        await self.db.update_share_state(
            state_key,
            {
                "last_period": current_period.value,
                idx_key: next_idx,
                "sequence_index": next_idx,
                "last_timestamp": datetime.now().isoformat(),
                "last_type": selected,
            },
        )

        if not selected:
            logger.warning(
                f"[日常分享] 无效分享类型配置 {seq[idx]!r}，请改为中文类型：问候、新闻、心情、知识、推荐。"
            )
            return ShareType.GREETING
        return ShareType(selected)

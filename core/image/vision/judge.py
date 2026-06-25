from __future__ import annotations

from astrbot.api import logger

from ...config import ShareType


class ImageVisualJudgeMixin:
    """判断配图是否需要出现主角人物。"""

    async def _check_involves_self(self, content: str, share_type: ShareType, target_umo: str = None) -> bool:
        """检测内容是否涉及“自己”。"""
        if self.img_conf.get("image_always_include_self", False):
            return True
        if self.img_conf.get("image_never_include_self", False):
            return False

        try:
            type_hint = ""
            if share_type in [ShareType.GREETING, ShareType.MOOD]:
                type_hint = "(提示：问候或心情分享通常需要人物出镜)"

            system_prompt = """你是一个AI绘画构图顾问。
任务：根据用户的【分享文案】，判断画面中【是否需要出现人物角色】。
【判断标准】
- YES (画人):
  1. 包含第一人称动作/状态 ("我穿着..." "我正在..." "我感觉...")
  2. 社交问候/互动 ("早安" "晚安" "看着我")
  3. 表达个人情绪/自拍感 ("今天好开心" "累瘫了")

- NO (画景/物):
  1. 纯客观描述 ("今天天气很好" "这朵花很美")
  2. 推荐具体物品 ("推荐这本书" "这个电影很好看")
  3. 分享新闻/知识 ("据说..." "你知道吗...")
隐藏推理口吻：
- 如果服务端记录隐藏推理，只保留一句以“我”开头的角色内心判断。
- 不要写“我们分析”“我们根据”“用户内容”“判断标准”这类旁观、审题或样本解析口吻。
请回答 YES 或 NO，不要解释。"""
            user_prompt = f"类型：{share_type.value} {type_hint}\n内容：{content}\n\n是否含人物？"

            res = await self._call_llm(user_prompt, system_prompt, timeout=10, target_umo=target_umo)
            if res and "YES" in res.strip().upper():
                return True
        except Exception as e:
            logger.debug(f"[图像服务] 人物判断失败，按不含人物处理: {e}")

        return False

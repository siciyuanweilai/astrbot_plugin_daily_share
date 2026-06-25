from __future__ import annotations

from astrbot.api import logger


class TaskNewsCacheFormatMixin:
    async def _shorten_news_url(self, url: str) -> str:
        original_url = self._clean_snapshot_text(url, 500)
        if not original_url:
            return ""

        shortener = getattr(self.news_service, "shorten_url", None)
        if not callable(shortener):
            return original_url

        try:
            short_url = await shortener(original_url)
            return self._clean_snapshot_text(short_url, 500) or original_url
        except Exception as e:
            logger.debug(f"[每日分享] 生成新闻短链接失败，保留原链接: {e}")
            return original_url

    async def _format_news_link_item(self, snapshot: dict, item: dict, index: int, action: str = "link") -> str:
        source_name = snapshot.get("source_name") or "新闻热搜"
        source_key = snapshot.get("source_key") or ""
        title = item.get("title") or "未命名新闻"
        url = item.get("url") or ""
        if not url:
            return f"【{source_name}】第 {index} 条暂时没有可用原文链接。\n{title}"

        link = await self._shorten_news_url(url)
        if action == "source":
            lines = [f"【{source_name}】第 {index} 条", f"标题：{title}", f"来源：{source_name}"]
            if source_key:
                lines.append(f"来源标识：{source_key}")
            lines.append(f"短链接：{link}")
            return "\n".join(lines)

        lines = [f"【{source_name}】第 {index} 条", f"标题：{title}", f"短链接：{link}"]
        desc = self._clean_snapshot_text(item.get("description"), 160)
        if desc and desc != title:
            lines.append(f"摘要：{desc}")
        elif action == "summary":
            lines.append("摘要：当前缓存里暂时没有更详细的摘要，可以打开短链接查看原文。")
        return "\n".join(lines)

    def _format_news_link_preview(self, snapshot: dict, items: list, limit: int = 10) -> str:
        preview = "\n".join(
            f"{idx}. {item.get('title', '未命名新闻')}"
            for idx, item in enumerate(items[:limit], start=1)
        )
        return (
            f"工具内部提示：当前可查新闻列表为【{snapshot.get('source_name', '新闻热搜')}】，共 {len(items)} 条。"
            "如果用户想查链接、来源或详情，你需要把理解出的序号用阿拉伯数字填入 index 后再次调用本工具；"
            "不要向用户提及缓存命中或工具状态。\n"
            f"{preview}"
        )

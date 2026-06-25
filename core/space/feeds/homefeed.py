from __future__ import annotations

from ..models import QzonePost
from ..parse import parse_home_feed_list


class QzoneFeedHomeMixin:
    """空间主页动态。"""

    async def query_home_posts(self, *, pos: int = 0, num: int = 5) -> list[QzonePost]:
        ctx = await self.context()
        offset = max(0, int(pos or 0))
        limit = max(1, min(int(num or 5), 20))
        fetch_limit = max(1, min(offset + limit, 20))
        raw = await self._request_text(
            "GET",
            self.HOME_FEED_URL,
            params={
                "g_iframeUser": 1,
                "i_uin": ctx.uin,
                "i_login_uin": ctx.uin,
                "mode": 4,
                "previewV8": 1,
                "style": 35,
                "version": 8,
                "needDelOpr": "true",
                "transparence": "true",
                "hideExtend": "false",
                "showcount": fetch_limit,
                "MORE_FEEDS_CGI": "http://ic2.s8.qzone.qq.com/cgi-bin/feeds/feeds_html_act_all",
                "refer": 2,
                "paramstring": "os-windows|100",
            },
            headers=self._headers(ctx, Referer=f"{self.BASE_URL}/{ctx.uin}/main"),
        )
        posts = parse_home_feed_list(raw)[offset : offset + limit]
        self._remember_posts(posts)
        return posts

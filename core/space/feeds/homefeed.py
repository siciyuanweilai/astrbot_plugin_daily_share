from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import QzonePost
from ..parse import parse_home_feed_list

if TYPE_CHECKING:
    from ..qzone import QzoneService


class QzoneFeedHomeService:
    """空间主页动态。"""

    def __init__(self, owner: QzoneService) -> None:
        self.owner = owner

    async def query_home_posts(self, *, pos: int = 0, num: int = 5) -> list[QzonePost]:
        ctx = await self.owner.context()
        offset = max(0, int(pos or 0))
        limit = max(1, min(int(num or 5), 20))
        fetch_limit = max(1, min(offset + limit, 20))
        raw = await self.owner._request_text(
            "GET",
            self.owner.HOME_FEED_URL,
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
            headers=self.owner._headers(
                ctx, Referer=f"{self.owner.BASE_URL}/{ctx.uin}/main"
            ),
        )
        posts = parse_home_feed_list(raw)[offset : offset + limit]
        self.owner._remember_posts(posts)
        return posts

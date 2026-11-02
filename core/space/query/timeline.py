from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs

from ..models import QzoneContext

if TYPE_CHECKING:
    from ..qzone import QzoneService


class QzoneFeedQueryService:
    def __init__(self, owner: QzoneService) -> None:
        self.owner = owner

    def _recent_posts_params(
        self, ctx: QzoneContext, *, count: int, cursor: str = ""
    ) -> dict[str, Any]:
        params = {
            "uin": ctx.uin,
            "scope": 0,
            "view": 1,
            "filter": "all",
            "flag": 1,
            "applist": "all",
            "pagenum": 1,
            "aisortEndTime": 0,
            "aisortOffset": 0,
            "aisortBeginTime": 0,
            "begintime": 0,
            "format": "json",
            "g_tk": ctx.gtk2,
            "useutf8": 1,
            "outputhtmlfeed": 1,
        }
        if count > 0:
            params["count"] = count
        if cursor:
            cursor_params = parse_qs(str(cursor), keep_blank_values=True)
            page_values = cursor_params.get("pagenum") or []
            basetime_values = cursor_params.get("basetime") or []
            if page_values:
                params["pagenum"] = page_values[0]
            if basetime_values:
                params["begintime"] = basetime_values[0]
            params["externparam"] = cursor
        return params

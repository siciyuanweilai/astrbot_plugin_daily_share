from __future__ import annotations


class DashboardQzoneUtilMixin:
    @staticmethod
    def _page_qzone_post_payload(post, *, self_uin: int = 0, include_comments: bool = False) -> dict:
        return post.to_payload(self_uin=self_uin, include_comments=include_comments)

    @staticmethod
    def _page_qzone_account_payload(ctx) -> dict:
        return {"uin": ctx.uin, "nickname": ctx.nickname or str(ctx.uin)}

    @staticmethod
    def _page_qzone_page_args(params: dict, *, default_num: int = 10, max_num: int = 20) -> tuple[int, int]:
        try:
            pos = max(0, int(params.get("pos") or 0))
        except Exception:
            pos = 0
        try:
            num = min(max(int(params.get("num") or default_num), 1), max_num)
        except Exception:
            num = default_num
        return pos, num

    def _page_qzone_post_items(self, posts, *, self_uin: int, include_comments: bool = True) -> list[dict]:
        return [
            self._page_qzone_post_payload(
                post,
                self_uin=self_uin,
                include_comments=include_comments,
            )
            for post in posts
        ]

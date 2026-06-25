from __future__ import annotations


class DashboardRouteTargetMixin:
    async def page_targets_update(self):
        async def handler():
            body = await self._page_json_body()
            receiver_conf = self.config.setdefault("receiver", {})
            extra_conf = self.config.setdefault("extra_shares", {})

            receiver_conf["groups"] = self._normalize_page_target_list(body.get("groups", []))
            receiver_conf["users"] = self._normalize_page_target_list(body.get("users", []))
            extra_conf["briefing_groups"] = self._normalize_page_target_list(
                body.get("briefing_groups", []),
                briefing=True,
            )
            extra_conf["briefing_users"] = self._normalize_page_target_list(
                body.get("briefing_users", []),
                briefing=True,
            )

            self.receiver_conf = receiver_conf
            self.extra_shares_conf = extra_conf
            await self._save_config_and_refresh_runtime()

            status = await self._build_page_status()
            return {"ok": True, "data": status["data"], "message": "目标配置已保存"}

        return await self._page_json(handler)

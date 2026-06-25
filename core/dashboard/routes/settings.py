from __future__ import annotations


class DashboardRouteConfigMixin:
    async def page_config(self):
        async def handler():
            body = await self._page_json_body()
            saved = bool(body)
            if saved:
                previous_enabled = bool(self.config.get("enable_auto_share", False))
                self._apply_page_config_payload(body)
                next_enabled = bool(self.config.get("enable_auto_share", False))
                await self._save_config_and_refresh_runtime(
                    clear_pending_when_disabled=previous_enabled and not next_enabled
                )

            data = self._page_config_payload()
            if saved:
                status = await self._build_page_status()
                data["status"] = status["data"]
            return {
                "ok": True,
                "data": data,
                "message": "设置已保存" if saved else "",
            }

        return await self._page_json(handler)

    async def page_preferences(self):
        async def handler():
            preferences = await self._load_page_preferences()
            body = await self._page_json_body()
            should_save = False
            if "sakura_enabled" in body:
                preferences["sakura_enabled"] = bool(body.get("sakura_enabled"))
                should_save = True
            if should_save:
                preferences = await self._save_page_preferences(preferences)
            return {"ok": True, "data": {"preferences": preferences}}

        return await self._page_json(handler)

    async def page_toggle(self):
        async def handler():
            body = await self._page_json_body()
            enable = bool(body.get("enable"))
            self.config["enable_auto_share"] = enable
            await self._save_config_and_refresh_runtime(
                clear_pending_when_disabled=not enable
            )
            status = await self._build_page_status()
            return {
                "ok": True,
                "data": status["data"],
                "message": "自动分享已启用" if enable else "自动分享已停用",
            }

        return await self._page_json(handler)

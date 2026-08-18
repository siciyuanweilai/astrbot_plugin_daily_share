from __future__ import annotations

from ..panelcomponent import PanelComponent
from ..revision import require_current_revision, settings_config_revision


class DashboardRouteConfigService(PanelComponent):
    async def page_config(self):
        async def handler():
            body = await self.server._page_json_body()
            saved = bool(body)
            if saved:
                requested_revision = body.get("settings_revision")

                def validate_revision() -> None:
                    require_current_revision(
                        requested_revision,
                        settings_config_revision(self.config),
                        conflict_message=(
                            "设置已在其他页面或运行过程中更新，请基于最新设置重试"
                        ),
                    )

                def apply_config() -> None:
                    self.apply._apply_page_config_payload(body)

                await self.refresh.save_config_and_refresh_runtime(
                    precondition=validate_revision, mutation=apply_config
                )

            data = self.payload._page_config_payload()
            if saved:
                status = await self.status_routes._build_page_status()
                data["status"] = status["data"]
            return {
                "ok": True,
                "data": data,
                "message": "设置已保存" if saved else "",
            }

        return await self.server._page_json(handler)

    async def page_preferences(self):
        async def handler():
            preferences = await self.server._load_page_preferences()
            body = await self.server._page_json_body()
            should_save = False
            if "sakura_enabled" in body:
                preferences["sakura_enabled"] = bool(body.get("sakura_enabled"))
                should_save = True
            if should_save:
                preferences = await self.server._save_page_preferences(preferences)
            return {"ok": True, "data": {"preferences": preferences}}

        return await self.server._page_json(handler)

    async def page_toggle(self):
        async def handler():
            body = await self.server._page_json_body()
            enable = bool(body.get("enable"))
            await self.refresh.save_config_and_refresh_runtime(
                clear_pending_when_disabled=not enable,
                mutation=lambda: self.config.__setitem__("enable_auto_share", enable),
            )
            status = await self.status_routes._build_page_status()
            return {
                "ok": True,
                "data": status["data"],
                "message": "自动分享已启用" if enable else "自动分享已停用",
            }

        return await self.server._page_json(handler)

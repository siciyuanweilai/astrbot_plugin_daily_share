from __future__ import annotations

from ..panelcomponent import PanelComponent
from ..roster import apply_shared_target_bindings


class DashboardRouteTargetService(PanelComponent):
    async def page_targets_update(self):
        async def handler():
            body = apply_shared_target_bindings(await self.server._page_json_body())

            def apply_targets() -> None:
                receiver_conf = self.config.setdefault("receiver", {})
                extra_conf = self.config.setdefault("extra_shares", {})
                receiver_conf["groups"] = self.targets._normalize_page_target_list(
                    body.get("groups", []), expected_group=True
                )
                receiver_conf["users"] = self.targets._normalize_page_target_list(
                    body.get("users", []), expected_group=False
                )
                extra_conf["briefing_groups"] = (
                    self.targets._normalize_page_target_list(
                        body.get("briefing_groups", []),
                        briefing=True,
                        expected_group=True,
                    )
                )
                extra_conf["briefing_users"] = self.targets._normalize_page_target_list(
                    body.get("briefing_users", []),
                    briefing=True,
                    expected_group=False,
                )

            await self.refresh.save_config_and_refresh_runtime(mutation=apply_targets)

            status = await self.status_routes._build_page_status()
            return {"ok": True, "data": status["data"], "message": "目标配置已保存"}

        return await self.server._page_json(handler)

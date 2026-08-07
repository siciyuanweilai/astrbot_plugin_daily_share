from __future__ import annotations

from astrbot.api import logger

from ..panelcomponent import PanelComponent
from ..revision import (
    require_current_revision,
    target_config_revision,
    target_config_snapshot,
)
from ..roster import apply_shared_target_bindings


class DashboardRouteTargetService(PanelComponent):
    async def page_targets_update(self):
        async def handler():
            body = apply_shared_target_bindings(await self.server._page_json_body())
            requested_revision = body.get("target_revision")

            def validate_revision() -> None:
                require_current_revision(
                    requested_revision,
                    target_config_revision(self.config),
                    conflict_message=(
                        "目标配置已在其他页面或运行过程中更新，请刷新仪表盘后重试"
                    ),
                )

            def apply_targets() -> tuple[dict[str, int], dict[str, int]]:
                before = {
                    key: len(value)
                    for key, value in target_config_snapshot(self.config).items()
                }
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
                after = {
                    key: len(value)
                    for key, value in target_config_snapshot(self.config).items()
                }
                return before, after

            before, after = await self.refresh.save_config_and_refresh_runtime(
                precondition=validate_revision, mutation=apply_targets
            )
            logger.info(
                "[日常分享] 仪表盘目标配置已保存: %s -> %s",
                before,
                after,
            )

            status = await self.status_routes._build_page_status()
            return {"ok": True, "data": status["data"], "message": "目标配置已保存"}

        return await self.server._page_json(handler)

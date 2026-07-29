from __future__ import annotations

from ..panelcomponent import PanelComponent

from datetime import datetime

from astrbot.api import logger

from ...database.keys import SOURCE_MANUAL

_PAGE_SHARE_TARGET_SCOPES = {
    "broadcast_groups": "groups",
    "broadcast_users": "users",
}


def _page_broadcast_target_scope(target: str) -> str:
    return _PAGE_SHARE_TARGET_SCOPES.get(target, "all")


def _page_missing_target_message(target: str) -> str:
    if target == "broadcast_groups":
        return "未找到可用群聊接收对象，请在目标配置中添加群号。"
    if target == "broadcast_users":
        return "未找到可用私聊接收对象，请在目标配置中添加 QQ 号或会话 ID。"
    return "未找到可用接收对象，请先在目标配置中添加群聊或私聊目标。"


class DashboardRouteActionService(PanelComponent):
    def _ensure_page_share_targets(
        self, target: str, specific_target: str = ""
    ) -> None:
        if target in {"qzone", "briefing"} or specific_target:
            return
        target_scope = _page_broadcast_target_scope(target)
        if self.task_manager.share.resolve_execute_share_targets(
            None,
            target_scope,
            exclude_custom_cron=False,
        ):
            return
        raise RuntimeError(_page_missing_target_message(target))

    async def _run_page_action(
        self,
        run_id: str,
        target: str,
        share_type: str,
        news_source: str,
        specific_target: str = "",
    ) -> None:
        run = self._page_action_runs.get(run_id)
        if not run:
            return
        try:
            force_type = self.validation._page_share_type(share_type)
            source_key = self.validation._page_news_source(news_source)
            success_message = "分享成功"
            async with self._lock:
                if target == "qzone":
                    ok = await self.task_manager.qzone_share.execute_qzone_share(
                        force_type=force_type,
                        news_source=source_key,
                        source_type=SOURCE_MANUAL,
                    )
                    if not ok:
                        raise RuntimeError("QQ 空间分享失败，请查看日志")
                    success_message = "QQ 空间分享成功"
                elif target == "briefing":
                    ok = await self.task_manager.briefing.execute_briefing_share(
                        source_type=SOURCE_MANUAL
                    )
                    if not ok:
                        raise RuntimeError("早报分享失败，请查看日志")
                    success_message = "早报分享成功"
                else:
                    ok = await self.task_manager.share.execute_share(
                        force_type=force_type,
                        news_source=source_key,
                        specific_target=specific_target or None,
                        target_scope=_page_broadcast_target_scope(target),
                        source_type=SOURCE_MANUAL,
                        exclude_custom_cron=False,
                    )
                    if not ok:
                        raise RuntimeError("分享失败，请查看日志")
                    success_message = {
                        "broadcast_groups": "群聊分享成功",
                        "broadcast_users": "私聊分享成功",
                    }.get(target, "分享成功")
            run["status"] = "done"
            run["message"] = success_message
        except Exception as exc:
            logger.exception("[日常分享] 仪表盘手动分享失败: %s", exc)
            run["status"] = "error"
            run["message"] = str(exc) or "分享失败"
        finally:
            run["finished_at"] = datetime.now().isoformat(timespec="seconds")
            self.activity._page_prune_actions()

    async def page_run(self):
        async def handler():
            body = await self.server._page_json_body()
            target = str(body.get("target") or "broadcast").strip()
            if target not in {
                "broadcast",
                "broadcast_groups",
                "broadcast_users",
                "qzone",
                "briefing",
            }:
                raise RuntimeError(f"不支持的分享目标: {target}")
            if self.is_share_busy(global_scope=True):
                raise BlockingIOError("已有任务正在分享，请稍后再试")

            share_type = str(body.get("share_type") or "自动").strip()
            news_source = str(body.get("news_source") or "").strip()
            self.validation._page_share_type(share_type)
            self.validation._page_news_source(news_source)
            specific_target, specific_kind = self.targets._page_specific_share_target(
                target,
                body.get("specific_target"),
                body.get("specific_adapter_id"),
            )
            self.action_routes._ensure_page_share_targets(target, specific_target)
            target_label = (
                await self.labels._resolve_page_target_label(
                    specific_target, specific_kind
                )
                if specific_target
                else ""
            )

            self._page_action_seq += 1
            run_id = f"dashboard-{self._page_action_seq}"
            run = {
                "id": run_id,
                "target": target,
                "target_id": specific_target,
                "target_label": target_label,
                "kind": specific_kind,
                "share_type": share_type or "自动",
                "news_source": news_source,
                "source_type": SOURCE_MANUAL,
                "source_label": "手动",
                "status": "running",
                "message": "分享中",
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "finished_at": "",
            }
            self._page_action_runs[run_id] = run
            self.track_task(
                self.action_routes._run_page_action(
                    run_id, target, share_type, news_source, specific_target
                )
            )
            return {"ok": True, "data": {"run": run}, "message": "任务已开始"}

        return await self.server._page_json(handler)

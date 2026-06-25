from __future__ import annotations

from datetime import datetime

from astrbot.api import logger

from ...database.keys import SOURCE_MANUAL


class DashboardRouteActionMixin:
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
            force_type = self._page_share_type(share_type)
            source_key = self._page_news_source(news_source)
            success_message = "分享成功"
            async with self._lock:
                if target == "qzone":
                    ok = await self.task_manager.execute_qzone_share(
                        force_type=force_type,
                        news_source=source_key,
                        source_type=SOURCE_MANUAL,
                    )
                    if not ok:
                        raise RuntimeError("QQ 空间分享失败，请查看日志")
                    success_message = "QQ 空间分享成功"
                elif target == "briefing":
                    await self.task_manager.execute_briefing_share(source_type=SOURCE_MANUAL)
                    success_message = "早报分享成功"
                else:
                    target_scope = {
                        "broadcast_groups": "groups",
                        "broadcast_users": "users",
                    }.get(target, "all")
                    await self.task_manager.execute_share(
                        force_type=force_type,
                        news_source=source_key,
                        specific_target=specific_target or None,
                        target_scope=target_scope,
                        source_type=SOURCE_MANUAL,
                    )
                    success_message = {
                        "broadcast_groups": "群聊分享成功",
                        "broadcast_users": "私聊分享成功",
                    }.get(target, "分享成功")
            run["status"] = "done"
            run["message"] = success_message
        except Exception as exc:
            logger.exception("[每日分享] 仪表盘手动分享失败: %s", exc)
            run["status"] = "error"
            run["message"] = str(exc) or "分享失败"
        finally:
            run["finished_at"] = datetime.now().isoformat(timespec="seconds")
            self._page_prune_actions()

    async def page_run(self):
        async def handler():
            body = await self._page_json_body()
            target = str(body.get("target") or "broadcast").strip()
            if target not in {"broadcast", "broadcast_groups", "broadcast_users", "qzone", "briefing"}:
                raise RuntimeError(f"不支持的分享目标: {target}")
            if self._is_share_busy(global_scope=True):
                raise RuntimeError("已有任务正在分享，请稍后再试")

            share_type = str(body.get("share_type") or "自动").strip()
            news_source = str(body.get("news_source") or "").strip()
            self._page_share_type(share_type)
            self._page_news_source(news_source)
            specific_target, specific_kind = self._page_specific_share_target(
                target,
                body.get("specific_target"),
            )
            target_label = (
                await self._resolve_page_target_label(specific_target, specific_kind)
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
            self._track_task(
                self._run_page_action(run_id, target, share_type, news_source, specific_target)
            )
            return {"ok": True, "data": {"run": run}, "message": "任务已开始"}

        return await self._page_json(handler)

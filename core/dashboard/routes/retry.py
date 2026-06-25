from __future__ import annotations

from datetime import datetime

from astrbot.api import logger

from ...database.keys import BRIEFING_TARGET_ALIASES, GLOBAL_TARGET_ID, QZONE_TARGET_ID, SOURCE_MANUAL


class DashboardRouteRetryMixin:
    async def _run_page_retry_action(self, run_id: str, history_item: dict) -> None:
        run = self._page_action_runs.get(run_id)
        if not run:
            return
        try:
            target_id = str(history_item.get("target_id") or "").strip()
            raw_type = str(history_item.get("type") or "auto").strip()
            force_type = self._page_share_type(raw_type)
            async with self._lock:
                if target_id == QZONE_TARGET_ID:
                    await self.task_manager.execute_qzone_share(
                        force_type=force_type,
                        source_type=SOURCE_MANUAL,
                    )
                elif target_id in BRIEFING_TARGET_ALIASES:
                    await self.task_manager.execute_briefing_share(source_type=SOURCE_MANUAL)
                elif target_id == GLOBAL_TARGET_ID:
                    await self.task_manager.execute_share(
                        force_type=force_type,
                        source_type=SOURCE_MANUAL,
                    )
                else:
                    await self.task_manager.execute_share(
                        force_type=force_type,
                        specific_target=target_id,
                        source_type=SOURCE_MANUAL,
                    )
            run["status"] = "done"
            run["message"] = "重试完成"
        except Exception as exc:
            logger.exception("[每日分享] 仪表盘重试失败: %s", exc)
            run["status"] = "error"
            run["message"] = str(exc) or "重试失败"
        finally:
            run["finished_at"] = datetime.now().isoformat(timespec="seconds")
            self._page_prune_actions()

    async def page_retry(self):
        async def handler():
            body = await self._page_json_body()
            history_id = body.get("history_id")
            if history_id is None:
                raise RuntimeError("缺少 history_id")
            item = await self.db.get_history_by_id(int(history_id))
            if not item:
                raise RuntimeError("未找到失败记录")
            if item.get("success"):
                raise RuntimeError("该记录不是失败记录，无需重试")
            if self._is_share_busy(global_scope=True):
                raise RuntimeError("已有任务正在分享，请稍后再试")

            self._page_action_seq += 1
            run_id = f"retry-{self._page_action_seq}"
            run = {
                "id": run_id,
                "target": "retry",
                "target_id": item.get("target_id", ""),
                "target_label": await self._resolve_page_target_label(
                    item.get("target_id", ""),
                    item.get("kind", ""),
                ),
                "kind": item.get("kind", ""),
                "share_type": item.get("type") or "auto",
                "news_source": "",
                "source_type": SOURCE_MANUAL,
                "source_label": "手动",
                "history_id": item.get("id"),
                "status": "running",
                "message": "重试中",
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "finished_at": "",
            }
            self._page_action_runs[run_id] = run
            self._track_task(self._run_page_retry_action(run_id, item))
            return {"ok": True, "data": {"run": run}, "message": "重试任务已开始"}

        return await self._page_json(handler)

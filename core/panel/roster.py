from .panelcomponent import PanelComponent

from ..database.keys import target_state_key
from ..platform import parse_platform_session


_TARGET_BUCKET_GROUP_KIND = {
    "groups": True,
    "users": False,
    "briefing_groups": True,
    "briefing_users": False,
}


def apply_shared_target_bindings(payload: dict) -> dict:
    """让分享与早报中的同一目标复用本次明确选择的平台。"""
    source = payload if isinstance(payload, dict) else {}
    bindings: dict[tuple[bool, str], set[str]] = {}

    for bucket, expected_group in _TARGET_BUCKET_GROUP_KIND.items():
        for item in (
            source.get(bucket, []) if isinstance(source.get(bucket), list) else []
        ):
            if not isinstance(item, dict):
                continue
            raw = str(item.get("session_id") or item.get("id") or "").strip()
            session = parse_platform_session(raw) or parse_platform_session(
                str(item.get("id") or "")
            )
            session_id = session.session_id if session else raw
            adapter_id = str(
                item.get("adapter_id")
                or item.get("platform_id")
                or (session.platform_id if session else "")
            ).strip()
            if session_id and adapter_id:
                bindings.setdefault((expected_group, session_id), set()).add(adapter_id)

    result = dict(source)
    for bucket, expected_group in _TARGET_BUCKET_GROUP_KIND.items():
        items = source.get(bucket, [])
        if not isinstance(items, list):
            continue
        resolved = []
        for item in items:
            if isinstance(item, dict):
                normalized = dict(item)
                raw = str(
                    normalized.get("session_id") or normalized.get("id") or ""
                ).strip()
                session = parse_platform_session(raw) or parse_platform_session(
                    str(normalized.get("id") or "")
                )
                session_id = session.session_id if session else raw
                adapter_id = str(
                    normalized.get("adapter_id") or normalized.get("platform_id") or ""
                ).strip()
                choices = bindings.get((expected_group, session_id), set())
                if not adapter_id and len(choices) == 1:
                    normalized["adapter_id"] = next(iter(choices))
                resolved.append(normalized)
                continue

            raw = str(item or "").strip()
            session = parse_platform_session(raw)
            if session:
                resolved.append(item)
                continue
            choices = bindings.get((expected_group, raw), set())
            if raw and len(choices) == 1:
                resolved.append(
                    {
                        "id": "",
                        "session_id": raw,
                        "adapter_id": next(iter(choices)),
                    }
                )
            else:
                resolved.append(item)
        result[bucket] = resolved
    return result


class DashboardTargetConfigService(PanelComponent):
    """仪表盘目标配置、统计和序列化。"""

    async def _page_target_item(self, target_id: str, conf, kind: str) -> dict:
        cron = None
        sequence = None
        if isinstance(conf, dict):
            cron = conf.get("cron")
            sequence = conf.get("seq")
        elif conf:
            sequence = str(conf)
        session = parse_platform_session(target_id)
        adapter_id = session.platform_id if session else ""
        if session:
            try:
                adapter_id = self.task_manager.targets.ensure_target_platform_routable(
                    target_id,
                    expected_group=session.is_group,
                ).route_id
            except ValueError:
                pass
        return {
            "id": str(target_id),
            "session_id": session.session_id if session else str(target_id),
            "adapter_id": adapter_id,
            "target_label": await self.labels._resolve_page_target_label(
                target_id, kind
            ),
            "kind": kind,
            "cron": cron or "",
            "sequence": sequence or "自动",
        }

    async def _page_targets(self) -> dict:
        r_groups = self.task_manager.targets.parse_targets_config(
            self.receiver_conf.get("groups", []), expected_group=True
        )
        r_users = self.task_manager.targets.parse_targets_config(
            self.receiver_conf.get("users", []), expected_group=False
        )
        briefing_groups = [
            await self.targets._page_target_item(item, None, "briefing_group")
            for item in self.extra_shares_conf.get("briefing_groups", [])
            if str(item or "").strip()
        ]
        briefing_users = [
            await self.targets._page_target_item(item, None, "briefing_user")
            for item in self.extra_shares_conf.get("briefing_users", [])
            if str(item or "").strip()
        ]
        groups = [
            await self.targets._page_target_item(target_id, conf, "group")
            for target_id, conf in r_groups.items()
        ]
        users = [
            await self.targets._page_target_item(target_id, conf, "user")
            for target_id, conf in r_users.items()
        ]
        return {
            "groups": groups,
            "users": users,
            "briefing_groups": briefing_groups,
            "briefing_users": briefing_users,
            "summary": {
                "share_targets": len(groups) + len(users),
                "briefing_targets": len(briefing_groups) + len(briefing_users),
            },
        }

    def _empty_target_stats(self) -> dict:
        return {
            "total": 0,
            "success": 0,
            "failed": 0,
            "success_rate": 0,
            "recent_count": 0,
            "frequency_per_day": 0,
            "last_at": "",
            "last_success_at": "",
            "types": {},
        }

    def _index_target_stats(self, stats: list) -> dict:
        indexed = {}
        for item in stats:
            target_id = str(item.get("target_id") or "").strip()
            if not target_id:
                continue
            keys = [target_id]
            _, real_id = self.ctx_service.parse_umo(target_id)
            if real_id:
                keys.append(real_id)
            for key in keys:
                indexed[key] = item
        return indexed

    async def _enrich_page_targets(
        self,
        targets: dict,
        target_stats: list,
        briefing_target_stats: list | None = None,
    ) -> None:
        stats_by_key = self.targets._index_target_stats(target_stats)
        briefing_stats_by_key = self.targets._index_target_stats(
            briefing_target_stats or []
        )
        for bucket in ("groups", "users", "briefing_groups", "briefing_users"):
            for item in targets.get(bucket, []):
                target_id = str(item.get("id") or "")
                if bucket.startswith("briefing"):
                    item["stats"] = briefing_stats_by_key.get(
                        target_id, self.targets._empty_target_stats()
                    )
                    item["state"] = {}
                    continue
                item["stats"] = stats_by_key.get(
                    target_id, self.targets._empty_target_stats()
                )
                state = await self.db.get_share_state(target_state_key(target_id), {})
                item["state"] = state if isinstance(state, dict) else {}

    def _clean_target_id_for_page(
        self,
        target_id: str,
        *,
        expected_group: bool,
        adapter_id: str = "",
        original_umo: str = "",
    ) -> str:
        target_id = str(target_id or "").strip()
        if not target_id:
            raise RuntimeError("QQ 号或群号不能为空")
        try:
            return self.task_manager.targets.resolve_target_input(
                target_id,
                expected_group=expected_group,
                adapter_id=adapter_id,
                original_umo=original_umo,
            )
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc

    def _page_specific_share_target(
        self, target: str, target_id: str, adapter_id: str = ""
    ) -> tuple:
        raw = str(target_id or "").strip()
        if not raw or target not in {"broadcast_groups", "broadcast_users"}:
            return "", ""
        label = "群号" if target == "broadcast_groups" else "QQ 号或会话 ID"
        if any(sep in raw for sep in (",", "，", ";", "；", "\n", "\r")):
            raise RuntimeError(f"一次只能指定一个{label}")
        is_group = target == "broadcast_groups"
        return (
            self.targets._clean_target_id_for_page(
                raw,
                expected_group=is_group,
                adapter_id=adapter_id,
            ),
            "group" if is_group else "user",
        )

    def _serialize_page_share_target(self, item, *, expected_group: bool) -> str:
        if isinstance(item, str):
            raw = item.strip().replace("：", ":")
            if not raw:
                return ""
            return self.targets._clean_target_id_for_page(
                raw,
                expected_group=expected_group,
            )

        if not isinstance(item, dict):
            raise RuntimeError("目标配置格式无效")

        target_id = self.targets._clean_target_id_for_page(
            str(item.get("session_id") or item.get("id") or ""),
            expected_group=expected_group,
            adapter_id=item.get("adapter_id") or item.get("platform_id") or "",
            original_umo=item.get("id") or item.get("umo") or "",
        )
        cron = str(item.get("cron") or "").strip()
        sequence = str(item.get("sequence") or item.get("seq") or "自动").strip()
        sequence = sequence.replace("，", ",") or "自动"

        if cron and not self.task_manager.targets.looks_like_cron(cron):
            raise RuntimeError(f"无效定时表达式: {cron}")
        cron = self.task_manager.targets.normalize_cron_value(cron)
        if sequence and not self.task_manager.targets.looks_like_share_sequence(
            sequence
        ):
            raise RuntimeError(f"无效类型序列: {sequence}")
        sequence = self.task_manager.targets.normalize_share_sequence(sequence)

        if cron:
            return f"{target_id}:{cron}:{sequence}"
        if sequence and sequence != "自动":
            return f"{target_id}:{sequence}"
        return target_id

    def _serialize_page_briefing_target(self, item, *, expected_group: bool) -> str:
        if isinstance(item, str):
            return self.targets._clean_target_id_for_page(
                item,
                expected_group=expected_group,
            )
        if not isinstance(item, dict):
            raise RuntimeError("目标配置格式无效")
        return self.targets._clean_target_id_for_page(
            str(item.get("session_id") or item.get("id") or ""),
            expected_group=expected_group,
            adapter_id=item.get("adapter_id") or item.get("platform_id") or "",
            original_umo=item.get("id") or item.get("umo") or "",
        )

    def _normalize_page_target_list(
        self,
        items,
        *,
        briefing: bool = False,
        expected_group: bool,
    ) -> list:
        if not isinstance(items, list):
            raise RuntimeError("目标列表必须是数组")
        result = []
        seen = set()
        for item in items:
            entry = (
                self.targets._serialize_page_briefing_target(
                    item, expected_group=expected_group
                )
                if briefing
                else self.targets._serialize_page_share_target(
                    item, expected_group=expected_group
                )
            )
            entry = str(entry or "").strip()
            if not entry:
                continue
            key = entry.replace("：", ":")
            if key not in seen:
                result.append(entry)
                seen.add(key)
        return result

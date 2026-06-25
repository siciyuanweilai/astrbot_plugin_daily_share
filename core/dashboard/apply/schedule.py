from __future__ import annotations


class DashboardApplyScheduleMixin:
    def _page_apply_schedule_fields(
        self,
        target: dict,
        source: dict,
        *,
        mode_key: str,
        mode_default: str,
        mode_label: str,
        mode_options: set,
        fixed_key: str,
        fixed_default: list,
        fixed_label: str,
        random_key: str,
        random_default: list,
        random_label: str,
        cron_key: str,
        cron_default: str,
        cron_label: str,
        smart_max_key: str,
        smart_max_default: int,
        smart_quiet_key: str,
        smart_quiet_default: list,
        smart_quiet_label: str,
        smart_prompt_key: str,
    ) -> None:
        if mode_key in source:
            target[mode_key] = self._page_choice_value(
                source.get(mode_key), mode_options, mode_default, mode_label
            )
        if fixed_key in source:
            target[fixed_key] = self._page_fixed_times_value(
                source.get(fixed_key), fixed_default, fixed_label
            )
        if random_key in source:
            target[random_key] = self._page_random_periods_value(
                source.get(random_key), random_default, random_label
            )
        if cron_key in source:
            target[cron_key] = self._page_cron_value(
                source.get(cron_key), cron_default, cron_label
            )
        if smart_max_key in source:
            target[smart_max_key] = self._page_int_value(
                source.get(smart_max_key), smart_max_default, min_value=1, max_value=6
            )
        if smart_quiet_key in source:
            target[smart_quiet_key] = self._page_quiet_hours_value(
                source.get(smart_quiet_key), smart_quiet_label
            )
        if smart_prompt_key in source:
            target[smart_prompt_key] = self._page_clean_text(
                source.get(smart_prompt_key), max_len=800
            )

        mode = str(target.get(mode_key) or mode_default).strip()
        if mode == "fixed_time" and not target.get(fixed_key):
            raise RuntimeError(f"{fixed_label}不能为空")
        if mode == "random_period" and not target.get(random_key):
            raise RuntimeError(f"{random_label}不能为空")
        if mode == "llm_smart" and smart_quiet_key not in target:
            target[smart_quiet_key] = list(smart_quiet_default)

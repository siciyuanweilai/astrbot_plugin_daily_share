from __future__ import annotations

from ...schedule import ScheduleDefinition
from ..panelcomponent import PanelComponent


class DashboardApplyScheduleService(PanelComponent):
    def _page_apply_schedule_fields(
        self,
        target: dict,
        source: dict,
        definition: ScheduleDefinition,
    ) -> None:
        self.schedule_apply._page_apply_schedule_values(
            target,
            source,
            definition,
        )

        mode = str(target.get(definition.mode_key) or definition.mode_default).strip()
        if mode == "fixed_time" and not target.get(definition.fixed_key):
            raise RuntimeError(f"{definition.fixed_label}不能为空")
        if mode == "random_period" and not target.get(definition.random_key):
            raise RuntimeError(f"{definition.random_label}不能为空")
        if mode == "llm_smart" and definition.smart_quiet_key not in target:
            target[definition.smart_quiet_key] = list(definition.smart_quiet_default)

    def _page_apply_schedule_values(
        self,
        target: dict,
        source: dict,
        definition: ScheduleDefinition,
    ) -> None:
        mode_key = definition.mode_key
        fixed_key = definition.fixed_key
        random_key = definition.random_key
        cron_key = definition.cron_key
        smart_max_key = definition.smart_max_key
        smart_quiet_key = definition.smart_quiet_key
        smart_prompt_key = definition.smart_prompt_key
        if mode_key in source:
            target[mode_key] = self.validation._page_choice_value(
                source.get(mode_key),
                definition.mode_options,
                definition.mode_default,
                definition.mode_label,
            )
        if fixed_key in source:
            target[fixed_key] = self.validation._page_fixed_times_value(
                source.get(fixed_key),
                list(definition.fixed_default),
                definition.fixed_label,
            )
        if random_key in source:
            target[random_key] = self.validation._page_random_periods_value(
                source.get(random_key),
                list(definition.random_default),
                definition.random_label,
            )
        if cron_key in source:
            target[cron_key] = self.validation._page_cron_value(
                source.get(cron_key),
                definition.cron_default,
                definition.cron_label,
            )
        if smart_max_key in source:
            target[smart_max_key] = self.validation._page_int_value(
                source.get(smart_max_key),
                definition.smart_max_default,
                min_value=1,
                max_value=6,
            )
        if smart_quiet_key in source:
            target[smart_quiet_key] = self.validation._page_quiet_hours_value(
                source.get(smart_quiet_key), definition.smart_quiet_label
            )
        if smart_prompt_key in source:
            target[smart_prompt_key] = self.validation._page_clean_text(
                source.get(smart_prompt_key), max_len=800
            )

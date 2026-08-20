import { text } from "./format.js";

import {
  applyBoundSchemaValues,
  applySchemaExtraValues,
  applySchemaSpecialCombos,
  collectSchemaExtraPayload,
  settingsPayloadGroups,
  writeBoundSchemaFields,
} from "./schema.js";

const CONFIG_AUTO_SAVE_FAST_DELAY_MS = 360;
const CONFIG_AUTO_SAVE_TEXT_DELAY_MS = 900;
const CONFIG_AUTO_SAVE_RETRY_DELAY_MS = 600;

export function createSettingsConfig({
  state,
  elements: el,
  bridge,
  apiGet,
  apiPost,
  setNotice,
  loadStatus,
  closeSweetSelects,
  registerSweetCombo,
  syncSweetCombo,
  syncSweetSelect,
  syncSweetSelects,
  applySettingsSchemaEnhancements,
  normalizeSettingsSliders,
  syncSettingSlider,
} = {}) {
  function arrayToLines(value) {
    return Array.isArray(value) ? value.join("\n") : "";
  }

  function newsSourceDisplayLabel(value) {
    return text(value).trim().replace(/热搜$/, "");
  }

  function newsSourceArrayToLines(value, options = []) {
    if (!Array.isArray(value)) return "";
    const labels = new Map(
      options.map((source) => [
        text(source?.value).trim(),
        newsSourceDisplayLabel(source?.label),
      ]),
    );
    return value
      .map((item) => {
        const raw = text(item).trim();
        return labels.get(raw) || raw;
      })
      .filter(Boolean)
      .join("\n");
  }

  function linesToArray(value) {
    return text(value)
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function setInputValue(input, value) {
    if (!input) return;
    input.value = value ?? "";
    syncSettingSlider(input);
  }

  function setInputChecked(input, value) {
    if (!input) return;
    input.checked = Boolean(value);
  }

  function configSection(name) {
    return state.configData?.sections?.[name] || {};
  }

  function setConfigDirty(value) {
    state.configDirty = Boolean(value);
  }

  function isConfigRevisionConflict(error) {
    const message = text(error?.message).trim();
    return message.includes("设置已在其他页面");
  }

  function configAutoSaveDelay(event) {
    const target = event?.target;
    if (event?.type === "change") return CONFIG_AUTO_SAVE_FAST_DELAY_MS;
    if (target instanceof HTMLSelectElement) return CONFIG_AUTO_SAVE_FAST_DELAY_MS;
    if (!(target instanceof HTMLInputElement)) return CONFIG_AUTO_SAVE_TEXT_DELAY_MS;
    if (target.type === "range" || target.type === "checkbox" || target.type === "radio") {
      return CONFIG_AUTO_SAVE_FAST_DELAY_MS;
    }
    return CONFIG_AUTO_SAVE_TEXT_DELAY_MS;
  }

  function scheduleConfigAutoSave(eventOrDelay) {
    window.clearTimeout(state.configAutoSaveTimer);
    const delay = typeof eventOrDelay === "number" ? eventOrDelay : configAutoSaveDelay(eventOrDelay);
    const changeSeq = state.configChangeSeq;
    state.configAutoSaveTimer = window.setTimeout(() => {
      state.configAutoSaveTimer = 0;
      void commitConfigSave({ changeSeq });
    }, delay);
  }

  function handleConfigChanged(event) {
    if (state.configApplying || isTargetEditorEvent(event)) return;
    handleScheduleChanged(event);
    state.configChangeSeq += 1;
    setConfigDirty(true);
    scheduleConfigAutoSave(event);
  }

  function scheduleControls(kind) {
    const groups = {
      basic: {
        mode: el.cfgBasicTriggerMode,
        fixed: el.cfgBasicFixedTimes,
        random: el.cfgBasicRandomPeriods,
        cron: el.cfgBasicShareCron,
        delay: el.cfgBasicCronDelay,
        smart: [
          el.cfgBasicSmartMaxCount,
          el.cfgBasicSmartQuietHours,
          el.cfgBasicSmartPrompt,
        ],
        defaultMode: "llm_smart",
      },
      briefing: {
        mode: el.cfgBriefingScheduleMode,
        fixed: el.cfgBriefingFixedTimes,
        random: el.cfgBriefingRandomPeriods,
        cron: el.cfgBriefingCron,
        delay: el.cfgBriefingDelay,
        smart: [
          el.cfgBriefingSmartMaxCount,
          el.cfgBriefingSmartQuietHours,
          el.cfgBriefingSmartPrompt,
        ],
        defaultMode: "llm_smart",
      },
      qzone: {
        mode: el.cfgQzoneTriggerMode,
        fixed: el.cfgQzoneFixedTimes,
        random: el.cfgQzoneRandomPeriods,
        cron: el.cfgQzoneCron,
        delay: el.cfgQzoneDelay,
        smart: [
          el.cfgQzoneSmartMaxCount,
          el.cfgQzoneSmartQuietHours,
          el.cfgQzoneSmartPrompt,
        ],
        defaultMode: "llm_smart",
      },
    };
    return groups[kind] || null;
  }

  function xiaohongshuScheduleField(kind) {
    return el.configForm?.querySelector(
      `[data-schedule="xiaohongshu-${kind}"]`,
    );
  }

  function syncXiaohongshuScheduleVisibility() {
    const modeField = el.configForm?.querySelector(
      '[data-schema-section="xiaohongshu_conf"][data-schema-field="trigger_mode"]',
    );
    const modeInput = modeField?.querySelector("input, select, textarea");
    if (!modeInput) return;

    const mode = {
      固定时间: "fixed_time",
      随机时段: "random_period",
      高级定时: "cron",
    }[text(modeInput.value).trim()] || text(modeInput.value).trim() || "fixed_time";
    const visibleKind = {
      fixed_time: "fixed",
      random_period: "random",
      cron: "cron",
    }[mode] || "fixed";

    for (const kind of ["fixed", "random", "cron"]) {
      const field = xiaohongshuScheduleField(kind);
      if (field) field.hidden = kind !== visibleKind;
    }
    const delayField = xiaohongshuScheduleField("delay");
    if (delayField) delayField.hidden = mode !== "fixed_time" && mode !== "cron";
    syncSweetSelect(modeInput);
  }

  function syncScheduleVisibility(kind) {
    const controls = scheduleControls(kind);
    if (!controls) return;
    const mode = controls.mode?.value || controls.defaultMode;
    const visibleKey = {
      fixed_time: "fixed",
      random_period: "random",
      llm_smart: "smart",
      cron: "cron",
    }[mode] || "smart";
    for (const key of ["fixed", "random", "smart", "cron"]) {
      for (const node of el.configForm?.querySelectorAll(`[data-schedule="${kind}-${key}"]`) || []) {
        node.hidden = key !== visibleKey;
      }
    }
    const delayVisible = mode === "fixed_time" || mode === "cron";
    for (const node of el.configForm?.querySelectorAll(`[data-schedule="${kind}-delay"]`) || []) {
      node.hidden = !delayVisible;
    }
    syncSweetSelect(controls.mode);
  }

  function handleScheduleChanged(event) {
    syncXiaohongshuScheduleVisibility();
    const target = event?.target;
    for (const kind of ["basic", "briefing", "qzone"]) {
      const controls = scheduleControls(kind);
      const fields = Object.values(controls).flat();
      if (!controls || !fields.includes(target)) continue;
      syncScheduleVisibility(kind);
      return;
    }
  }

  function populateDatalist(list, options = [], selected = "") {
    if (!list) return;
    const seen = new Set();
    const nodes = [];
    for (const option of options) {
      const value = text(option?.value).trim();
      if (!value || seen.has(value)) continue;
      seen.add(value);
      const node = document.createElement("option");
      node.value = value;
      node.label = text(option?.label).trim() || value;
      nodes.push(node);
    }
    const selectedValue = text(selected).trim();
    if (selectedValue && !seen.has(selectedValue)) {
      const node = document.createElement("option");
      node.value = selectedValue;
      node.label = selectedValue;
      nodes.push(node);
    }
    list.replaceChildren(...nodes);
    if (list === el.cfgLlmProviderOptions) syncSweetCombo(el.cfgLlmProviderId);
  }

  function populateNewsSourceSelect(options = [], selected = "zhihu") {
    if (!el.cfgNewsFixedSource) return;
    const nextOptions = options.length
      ? options.map((source) => new Option(newsSourceDisplayLabel(source.label || source.value), source.value))
      : [new Option("知乎", "zhihu")];
    el.cfgNewsFixedSource.replaceChildren(...nextOptions);
    el.cfgNewsFixedSource.value = selected || nextOptions[0]?.value || "";
    syncSweetSelect(el.cfgNewsFixedSource);
  }

  function applyConfigData(data = {}) {
    state.configApplying = true;
    state.configData = data;
    const target = configSection("target");
    const basic = configSection("basic");
    const qzone = configSection("qzone");
    const news = configSection("news");

    setInputValue(el.cfgContactAliases, arrayToLines(target.contact_aliases));

    applyBoundSchemaValues(state.configData, el, syncSettingSlider);
    syncScheduleVisibility("basic");
    syncScheduleVisibility("briefing");
    syncScheduleVisibility("qzone");
    setInputChecked(
      el.cfgQzoneAutoInteraction,
      qzone.qzone_enable_auto_interaction
        ?? (qzone.qzone_enable_auto_like || qzone.qzone_enable_auto_comment || qzone.qzone_enable_auto_reply),
    );
    populateNewsSourceSelect(data.options?.news_sources || [], news.news_api_source || "zhihu");
    setInputValue(el.cfgNewsRandomSources, newsSourceArrayToLines(news.news_random_sources, data.options?.news_sources || []));

    populateDatalist(el.cfgLlmProviderOptions, data.options?.providers || [], basic.llm_provider_id);
    populateDatalist(
      el.cfgAdapterOptions,
      data.options?.adapters || [],
      qzone.qzone_adapter_id || data.schema_values?.sections?.qzone_conf?.qzone_adapter_id,
    );

    applySettingsSchemaEnhancements(data);
    applySchemaSpecialCombos(el.configForm, registerSweetCombo, {
      provider: el.cfgLlmProviderOptions,
      adapter: el.cfgAdapterOptions,
    });
    applySchemaExtraValues(state.configData, el.configForm, syncSettingSlider);
    syncXiaohongshuScheduleVisibility();
    state.configApplying = false;
    setConfigDirty(false);
    syncSweetSelects();
  }

  function collectConfigPayload() {
    normalizeSettingsSliders();
    const payload = {
      settings_revision: state.configData?.settings_revision || "",
      enabled: Boolean(el.cfgEnabled?.checked),
      sections: {},
      schema_extra: { root: {}, sections: {} },
    };
    for (const [section, ids] of Object.entries(settingsPayloadGroups)) {
      writeBoundSchemaFields(payload, section, ids, { configData: state.configData, elements: el });
    }
    const extra = collectSchemaExtraPayload(state.configData, el.configForm);
    Object.assign(payload.schema_extra.root, extra.root);
    Object.assign(payload.schema_extra.sections, extra.sections);
    return payload;
  }

  function setSettingsTab(tab, { scroll = true, sync = true } = {}) {
    state.settingsTab = tab || "target";
    for (const section of el.settingsSections) {
      const active = section.dataset.settingsSection === state.settingsTab;
      section.classList.toggle("active", active);
      section.hidden = !active;
      section.setAttribute("aria-hidden", active ? "false" : "true");
    }
    for (const item of el.settingsNavItems || []) {
      const active = item.dataset.settingsTab === state.settingsTab;
      item.classList.toggle("active", active);
      if (active) {
        item.setAttribute("aria-current", "true");
      } else {
        item.removeAttribute("aria-current");
      }
    }
    if (sync) {
      closeSweetSelects();
      syncSweetSelects();
    }
    if (!scroll) return;
    const section = el.settingsSections.find((item) => item.dataset.settingsSection === state.settingsTab);
    if (section) {
      const top = Math.max(0, section.getBoundingClientRect().top + window.scrollY - 16);
      window.scrollTo({ top, behavior: "smooth" });
    }
  }

  async function loadConfig({ quiet = false } = {}) {
    if (!bridge) return;
    try {
      const data = await apiGet("page/config");
      applyConfigData(data);
      if (!quiet) setNotice("");
      return true;
    } catch (error) {
      setNotice(error.message || "设置加载失败", "error");
      return false;
    }
  }

  async function commitConfigSave({ changeSeq = state.configChangeSeq } = {}) {
    if (!state.configDirty) return;
    if (state.configSaving) {
      state.configSaveQueued = true;
      return;
    }

    window.clearTimeout(state.configAutoSaveTimer);
    state.configAutoSaveTimer = 0;
    state.configSaving = true;
    state.configSaveQueued = false;
    setConfigDirty(true);

    let shouldQueueNextSave = false;
    try {
      const data = await apiPost("page/config", collectConfigPayload());
      shouldQueueNextSave = state.configSaveQueued || state.configChangeSeq !== changeSeq;
      if (shouldQueueNextSave) {
        state.configData = data;
        setConfigDirty(true);
      } else {
        state.configData = data;
        setConfigDirty(false);
      }
      await loadStatus({ quiet: true });
    } catch (error) {
      shouldQueueNextSave = false;
      setConfigDirty(true);
      if (isConfigRevisionConflict(error)) {
        const loaded = await loadConfig({ quiet: true });
        if (loaded) {
          setNotice("设置已在其他页面更新，已自动加载最新设置。", "info");
        }
      } else {
        setNotice(error.message || "设置保存失败", "error");
      }
    } finally {
      state.configSaving = false;
      if (shouldQueueNextSave || state.configSaveQueued) {
        state.configSaveQueued = false;
        setConfigDirty(true);
        scheduleConfigAutoSave(CONFIG_AUTO_SAVE_RETRY_DELAY_MS);
      }
      setConfigDirty(state.configDirty);
    }
  }

  function isTargetEditorElement(node) {
    return Boolean(node?.closest?.(".settings-target-editor"));
  }

  function isTargetEditorEvent(event) {
    return isTargetEditorElement(event?.target);
  }

  return {
    handleConfigChanged,
    loadConfig,
    setSettingsTab,
  };
}

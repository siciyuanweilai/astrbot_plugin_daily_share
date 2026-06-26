import { text } from "./format.js?v=20260614-smart-schedule";

import {
  applyBoundSchemaValues,
  applySchemaExtraValues,
  applySchemaSpecialCombos,
  collectSchemaExtraPayload,
  settingsPayloadGroups,
  writeBoundSchemaFields,
} from "./schema.js?v=20260626-qzone-adapter";

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
    if (el.saveConfigButton) {
      el.saveConfigButton.disabled = !state.configDirty || state.configSaving || !state.configData;
    }
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
      void commitConfigSave({ auto: true, changeSeq });
    }, delay);
  }

  function handleConfigChanged(event) {
    if (state.configApplying || isTargetEditorEvent(event)) return;
    handleScheduleChanged(event);
    handleAutoScheduleChanged(event);
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
    const target = event?.target;
    for (const kind of ["basic", "briefing", "qzone"]) {
      const controls = scheduleControls(kind);
      const fields = Object.values(controls).flat();
      if (!controls || !fields.includes(target)) continue;
      syncScheduleVisibility(kind);
      return;
    }
  }

  function autoScheduleControls(kind) {
    return {
      interval: el.cfgQzoneAutoInteractionInterval,
      cron: el.cfgQzoneAutoInteractionCron,
      defaultInterval: 45,
      defaultCron: "0 */2 * * *",
    };
  }

  function handleAutoScheduleChanged(event) {
    const target = event?.target;
    const controls = autoScheduleControls("interaction");
    if (target !== controls.interval && target !== controls.cron) return;
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
    if (list === el.cfgPersonaOptions) syncSweetCombo(el.cfgPersonaId);
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
    const qzone = configSection("qzone");
    const news = configSection("news");
    const llm = configSection("llm");

    setInputValue(el.cfgTargetGroups, arrayToLines(target.groups));
    setInputValue(el.cfgTargetUsers, arrayToLines(target.users));
    setInputValue(el.cfgBriefingGroups, arrayToLines(target.briefing_groups));
    setInputValue(el.cfgBriefingUsers, arrayToLines(target.briefing_users));
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

    populateDatalist(el.cfgLlmProviderOptions, data.options?.providers || [], llm.llm_provider_id);
    populateDatalist(el.cfgPersonaOptions, data.options?.personas || [], llm.persona_id);
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
    state.configApplying = false;
    setConfigDirty(false);
    syncSweetSelects();
  }

  function collectConfigPayload() {
    normalizeSettingsSliders();
    const payload = {
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
      section.classList.toggle("active", section.dataset.settingsSection === state.settingsTab);
    }
    if (sync) {
      closeSweetSelects();
      syncSweetSelects();
    }
    if (!scroll) return;
    const section = el.settingsSections.find((item) => item.dataset.settingsSection === state.settingsTab);
    if (section) {
      state.settingsScrollLockUntil = Date.now() + 720;
      const top = Math.max(0, section.getBoundingClientRect().top + window.scrollY - 16);
      window.scrollTo({ top, behavior: "smooth" });
    }
  }

  function settingsVisiblePixels(section, viewportTop, viewportBottom) {
    const rect = section.getBoundingClientRect();
    return Math.max(0, Math.min(rect.bottom, viewportBottom) - Math.max(rect.top, viewportTop));
  }

  function resolveSettingsTabFromViewport() {
    if (state.activeView !== "settings" || !el.settingsSections.length) return;
    if (Date.now() < state.settingsScrollLockUntil) return;
    const viewportTop = Math.min(180, Math.max(96, window.innerHeight * 0.14));
    const viewportBottom = window.innerHeight - 24;
    let active = state.settingsTab || el.settingsSections[0].dataset.settingsSection || "target";
    let activeVisible = 0;
    let best = active;
    let bestVisible = 0;

    for (const section of el.settingsSections) {
      const tab = section.dataset.settingsSection || "";
      const visible = settingsVisiblePixels(section, viewportTop, viewportBottom);
      if (tab === active) activeVisible = visible;
      if (visible > bestVisible) {
        best = tab || best;
        bestVisible = visible;
      }
    }

    if (best && best !== state.settingsTab && (activeVisible < 64 || bestVisible - activeVisible > 96)) {
      setSettingsTab(best, { scroll: false, sync: false });
    }
  }

  function updateSettingsTabFromScroll() {
    if (state.settingsScrollFrame) return;
    state.settingsScrollFrame = window.requestAnimationFrame(() => {
      state.settingsScrollFrame = 0;
      resolveSettingsTabFromViewport();
    });
  }

  async function loadConfig({ quiet = false } = {}) {
    if (!bridge) return;
    try {
      const data = await apiGet("page/config");
      applyConfigData(data);
      if (!quiet) setNotice("");
    } catch (error) {
      setNotice(error.message || "设置加载失败", "error");
    }
  }

  async function commitConfigSave({ auto = false, changeSeq = state.configChangeSeq } = {}) {
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
    if (el.reloadConfigButton) el.reloadConfigButton.disabled = true;

    let shouldQueueNextSave = false;
    try {
      const data = await apiPost("page/config", collectConfigPayload());
      shouldQueueNextSave = state.configSaveQueued || state.configChangeSeq !== changeSeq;
      if (shouldQueueNextSave) {
        state.configData = data;
        setConfigDirty(true);
      } else if (auto) {
        state.configData = data;
        setConfigDirty(false);
      } else {
        applyConfigData(data);
      }
      await loadStatus({ quiet: true });
      if (!auto) setNotice("设置已保存。", "success");
    } catch (error) {
      shouldQueueNextSave = false;
      setConfigDirty(true);
      setNotice(error.message || "设置保存失败", "error");
    } finally {
      state.configSaving = false;
      if (shouldQueueNextSave || state.configSaveQueued) {
        state.configSaveQueued = false;
        setConfigDirty(true);
        scheduleConfigAutoSave(CONFIG_AUTO_SAVE_RETRY_DELAY_MS);
      }
      if (el.reloadConfigButton) el.reloadConfigButton.disabled = false;
      setConfigDirty(state.configDirty);
    }
  }

  async function saveConfig(event) {
    event?.preventDefault();
    if (event && !event.submitter && isTargetEditorElement(document.activeElement)) return;
    await commitConfigSave({ auto: false, changeSeq: state.configChangeSeq });
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
    saveConfig,
    setSettingsTab,
    updateSettingsTabFromScroll,
  };
}

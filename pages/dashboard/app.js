import { createDashboardApi, withTimeout } from "./api/bridge.js";
import { createDashboardEffects } from "./ui/trails.js";
import { createCalendarUi } from "./ui/calendar.js";
import { getDashboardElements } from "./ui/elements.js";
import { createDashboardEventController } from "./ui/wiring.js";
import { createMediaUi } from "./ui/library.js";
import { createQzoneUi } from "./ui/portal.js";
import { createStatusView } from "./ui/status.js";
import { createSettingsEnhancements } from "./ui/enhance.js";
import { createSettingsConfig } from "./ui/prefs.js";
import { createSweetControls } from "./ui/selects.js";
import { createDashboardState } from "./ui/session.js";
import { createTargetsUi } from "./ui/targets.js";
import { createSakuraControls } from "./ui/sakura.js";
import { createViewController } from "./ui/view.js";
import { text } from "./ui/format.js";

const bridge = window.AstrBotPluginPage;
const BRIDGE_READY_TIMEOUT_MS = 5000;
const BRIDGE_REQUEST_TIMEOUT_MS = 20000;
const { apiGet, apiPost } = createDashboardApi(bridge, BRIDGE_REQUEST_TIMEOUT_MS);
const NOTICE_AUTO_HIDE_MS = 4200;
const STATUS_POLL_RUNNING_DELAY_MS = 1200;
const STATUS_POLL_IDLE_DELAY_MS = 20000;
const SAKURA_STORAGE_KEY = "daily_share_dashboard_sakura";
const TARGET_CAROUSEL_INTERVAL_MS = 5200;

const state = createDashboardState();
const el = getDashboardElements();

const {
  closeSweetSelects,
  initSweetCombos,
  initSweetSelects,
  registerSweetCombo,
  syncSweetCombo,
  syncSweetSelect,
  syncSweetSelects,
} = createSweetControls({
  selects: el.selects,
  combos: [{ input: el.cfgLlmProviderId, list: el.cfgLlmProviderOptions }],
});

const {
  clearSakuraFall,
  hasSakuraFall,
  initDreamCursor,
  initSakuraFall,
  isMotionReduced: isSakuraMotionReduced,
} = createDashboardEffects({
  sakuraLayer: el.sakuraLayer,
  cursorTrailLayer: el.cursorTrailLayer,
});

const {
  applySakuraPreferences,
  initSakuraControls,
} = createSakuraControls({
  state,
  elements: el,
  bridge,
  apiPost,
  setNotice,
  storageKey: SAKURA_STORAGE_KEY,
  clearSakuraFall,
  hasSakuraFall,
  initSakuraFall,
  isMotionReduced: isSakuraMotionReduced,
});

const {
  applySettingsSchemaEnhancements,
  normalizeSettingsSliders,
  syncSettingSlider,
} = createSettingsEnhancements({
  configForm: el.configForm,
  settingsSections: el.settingsSections,
  elements: el,
});

const {
  initCalendarPanelLayout,
  renderCalendar,
  scheduleCalendarCarousel,
  scheduleCalendarPanelLayout,
  stopCalendarCarouselTimer,
} = createCalendarUi({
  state,
  elements: el,
  carouselIntervalMs: TARGET_CAROUSEL_INTERVAL_MS,
});

let loadQzoneFeedFromMedia = null;
let loadQzoneRelationFromMedia = null;

const {
  applyMediaPage,
  bindMediaEvents,
  clearImageMemoryCache,
  isDefaultMediaFilter,
  openMediaLightbox,
  reloadMediaPage,
  renderMedia,
  renderMediaFilters,
  resetMediaPage,
  syncDefaultMediaFromStatus,
} = createMediaUi({
  state,
  elements: el,
  apiGet,
  apiPost,
  setNotice,
  syncSweetSelect,
  loadQzoneFeed: (...args) => loadQzoneFeedFromMedia?.(...args),
  loadQzoneRelation: (...args) => loadQzoneRelationFromMedia?.(...args),
  reloadStatus: loadStatus,
});

const {
  bindTargetEvents,
  renderTargetCarousel,
  renderTargets,
  scheduleTargetCarousel,
  stopTargetCarouselTimer,
} = createTargetsUi({
  state,
  elements: el,
  carouselIntervalMs: TARGET_CAROUSEL_INTERVAL_MS,
  apiPost,
  syncSweetSelect,
  setTargetsDirty,
  setNotice,
  applyMediaPage,
  isDefaultMediaFilter,
  renderAll,
  scheduleCalendarPanelLayout,
});

const {
  bindQzoneEvents,
  closeQzoneEvents,
  loadQzoneFeed,
  loadQzoneRelation,
  renderQzone,
} = createQzoneUi({
  state,
  elements: el,
  apiGet,
  apiPost,
  setNotice,
  openMediaLightbox,
  reloadStatus: loadStatus,
});

loadQzoneFeedFromMedia = loadQzoneFeed;
loadQzoneRelationFromMedia = loadQzoneRelation;

function hideNotice() {
  window.clearTimeout(state.noticeTimer);
  state.noticeTimer = 0;
  el.notice.hidden = true;
  el.notice.textContent = "";
  el.notice.className = "notice";
}

function setNotice(message, tone = "info", autoHideMs = NOTICE_AUTO_HIDE_MS) {
  window.clearTimeout(state.noticeTimer);
  state.noticeTimer = 0;
  const body = text(message).trim();
  if (!body) {
    hideNotice();
    return;
  }

  const duration = Math.max(1200, Number(autoHideMs) || NOTICE_AUTO_HIDE_MS);
  el.notice.hidden = false;
  el.notice.textContent = body;
  el.notice.className = "notice";
  el.notice.style.setProperty("--notice-duration", `${duration}ms`);
  if (tone) el.notice.classList.add(tone);
  void el.notice.offsetWidth;
  el.notice.classList.add("is-visible");
  state.noticeTimer = window.setTimeout(hideNotice, duration);
}

const {
  handleConfigChanged,
  loadConfig,
  setSettingsTab,
} = createSettingsConfig({
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
});

const {
  fillNewsSources,
  isSpecificRunTarget,
  renderConfig,
  renderMetrics,
  renderRecentActions,
} = createStatusView({
  state,
  elements: el,
  syncSweetSelect,
});

function renderStatusProgress() {
  renderRecentActions();
  renderConfig();
}

const {
  closeDashboardEvents,
  connectDashboardEvents,
} = createDashboardEventController({
  state,
  elements: el,
  loadQzoneFeed,
  reloadStatus: loadStatus,
  renderStatusProgress,
});

const {
  initPageSwitchControls,
  restoreActiveView,
} = createViewController({
  state,
  elements: el,
  closeSweetSelects,
  stopTargetCarouselTimer,
  stopCalendarCarouselTimer,
  renderTargetCarousel,
  scheduleCalendarCarousel,
  scheduleCalendarPanelLayout,
  loadConfig,
  setSettingsTab,
});

function setTargetsDirty(value) {
  state.targetsDirty = Boolean(value);
}

function renderAll() {
  fillNewsSources();
  renderMetrics();
  renderRecentActions();
  renderTargetCarousel();
  renderConfig();
  renderTargets();
  renderCalendar();
  renderQzone();
  renderMediaFilters();
  renderMedia();
  updateRunFormState();
  syncSweetSelects();
  scheduleCalendarPanelLayout();
}

function hasRunningAction() {
  return (state.status?.actions || []).some((item) => item.status === "running");
}

function hasRunningProgress() {
  return text(state.status?.progress?.status).trim().toLowerCase() === "running";
}

function shouldPollStatus() {
  return hasRunningAction() || hasRunningProgress() || state.watchedRuns.size > 0;
}

function canPollStatus() {
  return state.bridgeReady && document.visibilityState !== "hidden";
}

function watchRun(run, fallbackTarget = "broadcast") {
  const runId = text(run?.id).trim();
  if (!runId) return;
  state.watchedRuns.set(runId, {
    target: text(run?.target || fallbackTarget).trim(),
    startedAt: text(run?.started_at).trim(),
  });
}

function notifyFinishedRuns(actions = []) {
  if (!state.watchedRuns.size) return false;
  let notified = false;
  const byId = new Map(actions.map((item) => [text(item?.id).trim(), item]));
  for (const [runId, watched] of [...state.watchedRuns.entries()]) {
    const action = byId.get(runId);
    if (!action || action.status === "running") continue;
    state.watchedRuns.delete(runId);
    notified = true;
    if (action.status === "error") {
      setNotice(action.message || "分享失败", "error");
    } else {
      setNotice(
        action.message || (watched.target === "retry" ? "重试完成。" : "分享成功。"),
        "success",
      );
    }
  }
  return notified;
}

function schedulePoll() {
  window.clearTimeout(state.pollTimer);
  state.pollTimer = 0;
  if (!canPollStatus()) return;
  const delay = shouldPollStatus()
    ? STATUS_POLL_RUNNING_DELAY_MS
    : STATUS_POLL_IDLE_DELAY_MS;
  state.pollTimer = window.setTimeout(
    () => loadStatus({ quiet: true }),
    delay,
  );
}

function handleStatusVisibilityChange() {
  window.clearTimeout(state.pollTimer);
  state.pollTimer = 0;
  if (canPollStatus()) {
    loadStatus({ quiet: true });
  }
}

async function loadStatus({ quiet = false } = {}) {
  if (!bridge) {
    setNotice("没有检测到页面通信接口，请从插件管理页面进入。", "error");
    return;
  }
  try {
    const nextStatus = await apiGet("page/status", { _ts: Date.now() });
    if (state.targetsDirty && state.status?.targets) {
      nextStatus.targets = state.status.targets;
      nextStatus.target_revision = state.status.target_revision;
    }
    state.status = nextStatus;
    if (!state.sakuraSaving) applySakuraPreferences(nextStatus.preferences);
    const showedRunResult = notifyFinishedRuns(nextStatus.actions || []);
    if (showedRunResult) {
      resetMediaPage();
    }
    const defaultMedia = isDefaultMediaFilter();
    const loadFilteredMedia = !defaultMedia && state.mediaKindFilter !== "qzone" && !state.mediaLoaded;
    if (defaultMedia) {
      syncDefaultMediaFromStatus(state.status);
    } else if (loadFilteredMedia) {
      state.media = [];
      state.mediaLoaded = true;
    }
    renderAll();
    if (loadFilteredMedia) {
      await reloadMediaPage({ quiet: true });
    }
    if (!quiet && !showedRunResult) setNotice("");
    schedulePoll();
  } catch (error) {
    if (!quiet) {
      setNotice(error.message || "状态加载失败", "error");
    }
    schedulePoll();
  }
}

async function runShare(event) {
  event.preventDefault();
  el.runButton.disabled = true;
  const target = el.runTarget.value;
  try {
    const data = await apiPost("page/run", {
      target,
      share_type: el.shareType.value,
      news_source: el.newsSource.value,
      specific_target: isSpecificRunTarget(target) ? text(el.runSpecificTarget?.value).trim() : "",
      specific_adapter_id: isSpecificRunTarget(target)
        ? text(el.runSpecificAdapter?.value).trim()
        : "",
    });
    watchRun(data.run, target);
    setNotice("任务已开始。", "success");
    await loadStatus({ quiet: true });
  } catch (error) {
    setNotice(error.message || "分享失败", "error");
  } finally {
    el.runButton.disabled = Boolean(state.status?.busy);
  }
}

function updateRunFormState() {
  const target = el.runTarget.value;
  const briefing = target === "briefing";
  const specificTarget = isSpecificRunTarget(target);
  const showSpecificTarget = target === "broadcast" || specificTarget;
  const specificTargetIsGroup = target !== "broadcast_users";
  el.shareType.disabled = briefing;
  el.newsSource.disabled = briefing || el.shareType.value !== "新闻";
  if (el.runSpecificTargetField) {
    el.runSpecificTargetField.hidden = !showSpecificTarget;
  }
  if (el.runSpecificAdapterField) {
    el.runSpecificAdapterField.hidden = !specificTarget;
  }
  if (el.runSpecificTargetLabel) {
    el.runSpecificTargetLabel.textContent = specificTargetIsGroup
      ? "指定群号"
      : "指定 QQ 号 / 会话 ID";
  }
  if (el.runSpecificTarget) {
    el.runSpecificTarget.placeholder = specificTargetIsGroup
      ? "输入群号，可留空"
      : "输入 QQ 号或会话 ID，可留空";
    el.runSpecificTarget.inputMode = "text";
    el.runSpecificTarget.disabled = !specificTarget;
    if (specificTarget) {
      if (el.runSpecificTarget.dataset.target && el.runSpecificTarget.dataset.target !== target) {
        el.runSpecificTarget.value = "";
      }
      el.runSpecificTarget.dataset.target = target;
    } else {
      el.runSpecificTarget.value = "";
      el.runSpecificTarget.dataset.target = "";
    }
  }
  if (el.runSpecificAdapter) {
    const selected = el.runSpecificAdapter.value;
    const platforms = Array.isArray(state.status?.target_platforms)
      ? state.status.target_platforms.filter((platform) => {
          if (platform.supports_proactive === false) return false;
          if (platform.conflicted === true) return false;
          return !(specificTargetIsGroup && platform.supports_group === false);
        })
      : [];
    const conflicts = Array.isArray(state.status?.target_platforms)
      ? state.status.target_platforms.filter((platform) => platform.conflicted === true)
      : [];
    const automaticLabel = conflicts.length
      ? "存在机器人实例 ID 冲突"
      : platforms.length === 1
      ? `自动（${platforms[0].label || platforms[0].value}）`
      : platforms.length > 1
        ? "请选择机器人"
        : "暂无可用机器人";
    const options = [new Option(automaticLabel, "")];
    for (const platform of platforms) {
      options.push(new Option(platform.label || platform.value, platform.value));
    }
    for (const platform of conflicts) {
      const option = new Option(platform.label || platform.value, "");
      option.disabled = true;
      options.push(option);
    }
    el.runSpecificAdapter.replaceChildren(...options);
    el.runSpecificAdapter.value = platforms.some((item) => item.value === selected)
      ? selected
      : "";
    el.runSpecificAdapter.disabled = !specificTarget;
    syncSweetSelect(el.runSpecificAdapter);
  }
  syncSweetSelect(el.runTarget);
  syncSweetSelect(el.shareType);
  syncSweetSelect(el.newsSource);
}

function handleSettingSwitchClick(event) {
  const label = event.target?.closest?.("label.setting-switch");
  if (!label || !el.configForm?.contains(label)) return;
  if (event.target instanceof HTMLInputElement && event.target.type === "checkbox") return;
  event.preventDefault();
}

function bindEvents() {
  el.configForm?.addEventListener("submit", (event) => event.preventDefault());
  el.configForm?.addEventListener("input", handleConfigChanged);
  el.configForm?.addEventListener("change", handleConfigChanged);
  el.configForm?.addEventListener("click", handleSettingSwitchClick);
  el.settingsNav?.addEventListener("click", (event) => {
    const item = event.target?.closest?.("[data-settings-tab]");
    if (!item || !el.settingsNav.contains(item)) return;
    event.preventDefault();
    setSettingsTab(item.dataset.settingsTab, { scroll: false });
  });
  el.runForm.addEventListener("submit", runShare);
  bindMediaEvents();
  bindQzoneEvents();
  window.addEventListener("beforeunload", () => {
    window.clearTimeout(state.pollTimer);
    window.clearTimeout(state.targetAutoSaveTimer);
    clearImageMemoryCache();
    closeDashboardEvents();
    closeQzoneEvents();
    stopTargetCarouselTimer();
    stopCalendarCarouselTimer();
  });
  document.addEventListener("visibilitychange", handleStatusVisibilityChange);
  bindTargetEvents();
  el.calendarPanel?.addEventListener("pointerenter", stopCalendarCarouselTimer);
  el.calendarPanel?.addEventListener("pointerleave", scheduleCalendarCarousel);
  el.calendarPanel?.addEventListener("focusin", stopCalendarCarouselTimer);
  el.calendarPanel?.addEventListener("focusout", scheduleCalendarCarousel);
  el.runTarget.addEventListener("change", updateRunFormState);
  el.shareType.addEventListener("change", updateRunFormState);
}

async function init() {
  initPageSwitchControls();
  restoreActiveView();
  initSakuraControls();
  bindEvents();
  initDreamCursor();
  initSweetSelects();
  initSweetCombos();
  initCalendarPanelLayout();

  if (!bridge) {
    setNotice("没有检测到页面通信接口，请从插件管理页面进入。", "error");
    return;
  }
  try {
    await withTimeout(
      bridge.ready(),
      BRIDGE_READY_TIMEOUT_MS,
      "初始化超时"
    );
  } catch (error) {
    setNotice(error.message || "桥接初始化失败", "error");
    return;
  }
  state.bridgeReady = true;
  connectDashboardEvents();
  await loadStatus();
  if (state.activeView === "settings" && !state.configData) {
    await loadConfig({ quiet: true });
  }
}

init();

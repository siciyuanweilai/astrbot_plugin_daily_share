import {
  DASHBOARD_EVENT_RECONNECT_MS,
  DASHBOARD_EVENT_RELOAD_DELAY_MS,
} from "./limits.js?v=20260615-dashboard-events";

export function createDashboardEventController({
  state,
  elements: el,
  loadQzoneFeed,
  reloadStatus,
  renderStatusProgress,
} = {}) {
  let eventReloadIncludesQzone = false;

  function scheduleEventReload({ qzone = false } = {}) {
    eventReloadIncludesQzone = eventReloadIncludesQzone || Boolean(qzone);
    window.clearTimeout(state.dashboardEventReloadTimer);
    state.dashboardEventReloadTimer = window.setTimeout(() => {
      state.dashboardEventReloadTimer = 0;
      const shouldReloadQzone = eventReloadIncludesQzone;
      eventReloadIncludesQzone = false;
      if (shouldReloadQzone && !el.qzonePanel?.hidden) loadQzoneFeed?.({ quiet: true });
      reloadStatus?.({ quiet: true });
    }, DASHBOARD_EVENT_RELOAD_DELAY_MS);
  }

  function handleEventMessage(event) {
    try {
      const payload = JSON.parse(event.data || "{}");
      if (payload.type === "share_progress") {
        if (state.status) state.status.progress = payload.data || {};
        renderStatusProgress?.();
        scheduleEventReload();
      } else if (payload.type === "qzone") {
        scheduleEventReload({ qzone: true });
      }
    } catch {
      // 忽略异常事件，避免影响仪表盘主流程。
    }
  }

  function connectDashboardEvents() {
    if (!window.EventSource || state.dashboardEventSource) return;
    try {
      const source = new EventSource("/astrbot_plugin_daily_share/page/events");
      state.dashboardEventSource = source;
      source.onmessage = handleEventMessage;
      source.onerror = () => {
        source.close();
        state.dashboardEventSource = null;
        window.clearTimeout(state.dashboardEventReconnectTimer);
        state.dashboardEventReconnectTimer = window.setTimeout(
          connectDashboardEvents,
          DASHBOARD_EVENT_RECONNECT_MS,
        );
      };
    } catch {
      state.dashboardEventSource = null;
    }
  }

  function closeDashboardEvents() {
    window.clearTimeout(state.dashboardEventReconnectTimer);
    window.clearTimeout(state.dashboardEventReloadTimer);
    state.dashboardEventReconnectTimer = 0;
    state.dashboardEventReloadTimer = 0;
    eventReloadIncludesQzone = false;
    state.dashboardEventSource?.close();
    state.dashboardEventSource = null;
  }

  return {
    closeDashboardEvents,
    connectDashboardEvents,
  };
}

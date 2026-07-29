export function createViewController({
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
  updateSettingsTabFromScroll,
} = {}) {
  function setActiveView(view, { scroll = true, behavior = "smooth" } = {}) {
    const nextView = view === "settings" ? "settings" : "dashboard";
    state.activeView = nextView;
    el.dashboardView.hidden = nextView !== "dashboard";
    el.settingsView.hidden = nextView !== "settings";
    document.body.classList.toggle("is-settings-view", nextView === "settings");
    if (nextView !== "dashboard") {
      stopTargetCarouselTimer();
      stopCalendarCarouselTimer();
    }
    closeSweetSelects();
    if (scroll) window.scrollTo({ top: 0, behavior });
  }

  function restoreActiveView() {
    setActiveView("dashboard", { scroll: false, behavior: "auto" });
  }

  async function openSettingsPage() {
    setActiveView("settings");
    setSettingsTab("target", { scroll: false });
    if (!state.configData) {
      await loadConfig({ quiet: true });
    }
    window.setTimeout(updateSettingsTabFromScroll, 220);
  }

  function openDashboardPage() {
    setActiveView("dashboard");
    renderTargetCarousel();
    scheduleCalendarCarousel();
    scheduleCalendarPanelLayout();
  }

  function initPageSwitchControls() {
    if (state.pageSwitchBound) return;
    state.pageSwitchBound = true;
    document.addEventListener("click", (event) => {
      const button = event.target?.closest?.("#settingsPageButton, #settingsBackButton");
      if (!(button instanceof HTMLButtonElement) || button.disabled) return;
      event.preventDefault();
      if (button.id === "settingsPageButton") {
        openSettingsPage();
      } else {
        openDashboardPage();
      }
    }, true);
  }

  return {
    initPageSwitchControls,
    restoreActiveView,
    setActiveView,
  };
}

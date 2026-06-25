const MEDIA_AUTO_LOAD_MARGIN_PX = 520;
const MEDIA_FILTERBAR_FIXED_TOP_PX = 8;
const MEDIA_FILTERBAR_FIXED_TOP_MOBILE_PX = 6;

export function createMediaScrollController({
  state,
  elements: el,
  loadMoreMedia,
} = {}) {
  let mediaScrollTarget = null;
  let mediaScrollFrame = 0;

  function canAutoLoadMoreMedia() {
    return state.activeView === "dashboard" &&
      state.bridgeReady &&
      state.mediaKindFilter !== "qzone" &&
      state.mediaLoaded &&
      state.mediaHasMore &&
      !state.mediaLoading &&
      !el.dashboardView?.hidden &&
      !el.mediaPanel?.hidden &&
      !el.mediaList?.hidden;
  }

  function isDocumentScrollTarget(target) {
    return !target ||
      target === window ||
      target === document ||
      target === document.documentElement ||
      target === document.body;
  }

  function isScrollableMediaAncestor(target) {
    if (!(target instanceof Element) || !el.mediaPanel || !target.contains(el.mediaPanel)) {
      return false;
    }
    const style = window.getComputedStyle(target);
    return /(auto|scroll|overlay)/.test(style.overflowY) &&
      target.scrollHeight > target.clientHeight + 1;
  }

  function findMediaScrollTarget() {
    if (isScrollableMediaAncestor(mediaScrollTarget)) return mediaScrollTarget;
    for (let node = el.mediaPanel?.parentElement; node && node !== document.body; node = node.parentElement) {
      if (isScrollableMediaAncestor(node)) return node;
    }
    return window;
  }

  function rememberMediaScrollTarget(event) {
    const target = event?.target;
    if (isDocumentScrollTarget(target)) {
      mediaScrollTarget = window;
      return;
    }
    if (isScrollableMediaAncestor(target)) mediaScrollTarget = target;
  }

  function mediaScrollViewport(target = findMediaScrollTarget()) {
    if (isDocumentScrollTarget(target)) {
      return {
        top: 0,
        bottom: window.innerHeight,
      };
    }
    const rect = target.getBoundingClientRect();
    return {
      top: Math.max(0, rect.top),
      bottom: Math.min(window.innerHeight, rect.bottom),
    };
  }

  function mediaScrollMetrics(target = findMediaScrollTarget()) {
    if (isDocumentScrollTarget(target)) {
      const root = document.scrollingElement || document.documentElement;
      return {
        scrollTop: window.scrollY || root.scrollTop || 0,
        viewportSize: window.innerHeight,
        scrollSize: Math.max(root.scrollHeight, document.body?.scrollHeight || 0),
      };
    }
    return {
      scrollTop: target.scrollTop,
      viewportSize: target.clientHeight,
      scrollSize: target.scrollHeight,
    };
  }

  function handleMediaPageScroll(event) {
    rememberMediaScrollTarget(event);
    syncMediaFilterbarPin();
    if (!canAutoLoadMoreMedia()) return;
    const metrics = mediaScrollMetrics();
    if (metrics.scrollTop + metrics.viewportSize >= metrics.scrollSize - MEDIA_AUTO_LOAD_MARGIN_PX) {
      loadMoreMedia?.();
    }
  }

  function queueMediaPageScroll(event) {
    rememberMediaScrollTarget(event);
    if (mediaScrollFrame) return;
    mediaScrollFrame = window.requestAnimationFrame(() => {
      mediaScrollFrame = 0;
      handleMediaPageScroll();
    });
  }

  function mediaFilterbarTopOffset() {
    const viewport = mediaScrollViewport();
    const gap = window.matchMedia?.("(max-width: 760px)").matches
      ? MEDIA_FILTERBAR_FIXED_TOP_MOBILE_PX
      : MEDIA_FILTERBAR_FIXED_TOP_PX;
    return viewport.top + gap;
  }

  function ensureMediaFilterbarPlaceholder() {
    if (!el.mediaFilterbar) return null;
    let placeholder = el.mediaFilterbar.nextElementSibling;
    if (placeholder?.classList?.contains("media-filterbar-placeholder")) {
      return placeholder;
    }
    placeholder = document.createElement("div");
    placeholder.className = "media-filterbar-placeholder";
    placeholder.hidden = true;
    el.mediaFilterbar.insertAdjacentElement("afterend", placeholder);
    return placeholder;
  }

  function releaseMediaFilterbarPin(placeholder = ensureMediaFilterbarPlaceholder()) {
    if (!el.mediaFilterbar) return;
    document.documentElement.classList.remove("media-filterbar-pinned");
    el.mediaFilterbar.classList.remove("is-pinned");
    el.mediaFilterbar.style.removeProperty("--media-filterbar-top");
    el.mediaFilterbar.style.removeProperty("--media-filterbar-left");
    el.mediaFilterbar.style.removeProperty("--media-filterbar-width");
    if (placeholder) {
      placeholder.hidden = true;
      placeholder.style.height = "0px";
    }
  }

  function syncMediaHangingLayer(active) {
    const root = document.documentElement;
    if (!active || !el.mediaPanel) {
      root.classList.remove("media-panel-under-hanger");
      return;
    }
    const hanger = document.querySelector(".dashboard-view:not([hidden]) .hanging-controls:not(.settings-hanging-controls)");
    const panelRect = el.mediaPanel.getBoundingClientRect();
    const hangerRect = hanger?.getBoundingClientRect();
    const hangerTop = hangerRect?.top ?? 0;
    const hangerBottom = hangerRect?.bottom ?? 260;
    root.classList.toggle(
      "media-panel-under-hanger",
      panelRect.top < hangerBottom && panelRect.bottom > hangerTop,
    );
  }

  function syncMediaFilterbarPin() {
    if (!el.mediaFilterbar || !el.mediaPanel) {
      syncMediaHangingLayer(false);
      return;
    }
    const placeholder = ensureMediaFilterbarPlaceholder();
    const active = state.activeView === "dashboard" &&
      !el.dashboardView?.hidden &&
      !el.mediaPanel?.hidden;
    syncMediaHangingLayer(active);
    if (!active) {
      releaseMediaFilterbarPin(placeholder);
      return;
    }

    const viewport = mediaScrollViewport();
    const panelRect = el.mediaPanel.getBoundingClientRect();
    const top = mediaFilterbarTopOffset();
    const pinned = el.mediaFilterbar.classList.contains("is-pinned");
    const anchorRect = pinned && placeholder
      ? placeholder.getBoundingClientRect()
      : el.mediaFilterbar.getBoundingClientRect();
    const barHeight = el.mediaFilterbar.offsetHeight || anchorRect.height || 0;
    const style = window.getComputedStyle(el.mediaFilterbar);
    const marginBottom = Number.parseFloat(style.marginBottom) || 0;
    const shouldPin = anchorRect.top <= top &&
      panelRect.bottom > top + barHeight + 8 &&
      panelRect.top < viewport.bottom;
    if (!shouldPin) {
      releaseMediaFilterbarPin(placeholder);
      return;
    }

    if (placeholder) {
      placeholder.hidden = false;
      placeholder.style.height = `${barHeight + marginBottom}px`;
    }
    el.mediaFilterbar.classList.add("is-pinned");
    document.documentElement.classList.add("media-filterbar-pinned");
    el.mediaFilterbar.style.setProperty("--media-filterbar-top", `${top}px`);
    el.mediaFilterbar.style.setProperty("--media-filterbar-left", `${panelRect.left}px`);
    el.mediaFilterbar.style.setProperty("--media-filterbar-width", `${panelRect.width}px`);
  }

  return {
    queueMediaPageScroll,
    syncMediaFilterbarPin,
  };
}

import { text } from "./format.js?v=20260614-smart-schedule";

const sliderGestureThresholdPx = 8;
const sliderGestureAxisRatio = 1.25;
const sliderLockReleaseMs = 260;
const sliderGestures = new WeakMap();

function settingSliderEventPoint(event) {
  const touch = event.touches?.[0] || event.changedTouches?.[0];
  const x = Number(event.clientX ?? touch?.clientX);
  const y = Number(event.clientY ?? touch?.clientY);
  return Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
}

function shouldGuardSettingSliderGesture(event) {
  const pointerType = text(event?.pointerType).toLowerCase();
  if (pointerType === "mouse") return false;
  if (pointerType === "touch" || pointerType === "pen") return true;
  return Boolean(window.matchMedia?.("(pointer: coarse)")?.matches || window.innerWidth <= 720);
}

function restoreSettingSliderGesture(range, gesture) {
  if (!gesture) return;
  range.value = gesture.rangeValue;
  gesture.input.value = gesture.inputValue;
}

function releaseSettingSliderGesture(range, gesture) {
  window.clearTimeout(gesture?.releaseTimer);
  if (!gesture) return;
  gesture.releaseTimer = window.setTimeout(() => {
    if (sliderGestures.get(range) === gesture) sliderGestures.delete(range);
  }, sliderLockReleaseMs);
}

function settingSliderBinding(input) {
  return input?.closest?.(".setting-field")?.querySelector(":scope > .setting-slider-control input[type='range']") || null;
}

function sliderNumber(value, fallback = 0) {
  const raw = text(value).trim();
  if (raw === "") return fallback;
  const number = Number(raw);
  return Number.isFinite(number) ? number : fallback;
}

function fieldCaptionNode(field) {
  return [...field.children].find((child) => child.tagName === "SPAN") || null;
}

export function createSettingSliderEnhancements({ configForm } = {}) {
  function syncSettingSlider(input) {
    if (!(input instanceof HTMLInputElement)) return;
    const range = settingSliderBinding(input);
    if (!range) return;
    const min = sliderNumber(range.min, 0);
    const max = sliderNumber(range.max, min);
    const value = sliderNumber(input.value, sliderNumber(range.value, min));
    range.value = String(Math.min(max, Math.max(min, value)));
  }

  function normalizeSettingSliderInput(input) {
    if (!(input instanceof HTMLInputElement)) return;
    const range = settingSliderBinding(input);
    if (!range) return;
    const min = sliderNumber(range.min, 0);
    const max = sliderNumber(range.max, min);
    const value = sliderNumber(input.value, sliderNumber(input.defaultValue || range.min, min));
    const clamped = Math.min(max, Math.max(min, value));
    input.value = String(clamped);
    range.value = String(clamped);
  }

  function syncSettingsSliders() {
    for (const input of configForm?.querySelectorAll(".setting-field.has-slider input[type='number']") || []) {
      syncSettingSlider(input);
    }
  }

  function normalizeSettingsSliders() {
    for (const input of configForm?.querySelectorAll(".setting-field.has-slider input[type='number']") || []) {
      normalizeSettingSliderInput(input);
    }
  }

  function beginSettingSliderGesture(range, input, event) {
    if (!shouldGuardSettingSliderGesture(event)) return;
    const point = settingSliderEventPoint(event);
    if (!point) return;
    const previous = sliderGestures.get(range);
    if (previous) window.clearTimeout(previous.releaseTimer);
    sliderGestures.set(range, {
      input,
      startX: point.x,
      startY: point.y,
      inputValue: input.value,
      rangeValue: range.value,
      mode: "pending",
      releaseTimer: 0,
    });
  }

  function commitSettingSliderRange(input, range, eventName = "input") {
    const previous = input.value;
    input.value = range.value;
    syncSettingSlider(input);
    if (input.value !== previous) {
      input.dispatchEvent(new Event(eventName, { bubbles: true }));
    }
  }

  function updateSettingSliderGesture(range, input, event) {
    const gesture = sliderGestures.get(range);
    if (!gesture || gesture.mode !== "pending") return;
    const point = settingSliderEventPoint(event);
    if (!point) return;
    const dx = Math.abs(point.x - gesture.startX);
    const dy = Math.abs(point.y - gesture.startY);
    if (dy > sliderGestureThresholdPx && dy > dx * sliderGestureAxisRatio) {
      gesture.mode = "locked";
      restoreSettingSliderGesture(range, gesture);
    } else if (dx > sliderGestureThresholdPx && dx > dy * sliderGestureAxisRatio) {
      gesture.mode = "adjusting";
      commitSettingSliderRange(input, range);
    }
  }

  function endSettingSliderGesture(range) {
    const gesture = sliderGestures.get(range);
    if (!gesture) return;
    if (gesture.mode === "adjusting") {
      sliderGestures.delete(range);
      return;
    }
    gesture.mode = "locked";
    restoreSettingSliderGesture(range, gesture);
    releaseSettingSliderGesture(range, gesture);
  }

  function settingSliderInputBlocked(range) {
    const gesture = sliderGestures.get(range);
    if (!gesture || gesture.mode === "adjusting") return false;
    restoreSettingSliderGesture(range, gesture);
    return true;
  }

  function enhanceSettingSlider(input, slider = {}) {
    if (!(input instanceof HTMLInputElement) || input.type !== "number") return;
    const field = input.closest(".setting-field");
    if (!field || field.querySelector(":scope > .setting-slider-control")) {
      syncSettingSlider(input);
      return;
    }

    const min = slider.min ?? input.min ?? 0;
    const max = slider.max ?? input.max ?? 100;
    const step = slider.step ?? input.step ?? 1;
    input.min = String(min);
    input.max = String(max);
    input.step = String(step);
    input.inputMode = String(step).includes(".") || String(step) === "any" ? "decimal" : "numeric";
    input.classList.add("setting-number-input");
    field.classList.add("has-slider");

    const control = document.createElement("div");
    control.className = "setting-slider-control";

    const range = document.createElement("input");
    range.type = "range";
    range.min = String(min);
    range.max = String(max);
    range.step = String(step);
    range.setAttribute("aria-label", `${fieldCaptionNode(field)?.textContent || "数值"}滑块`);

    input.insertAdjacentElement("beforebegin", control);
    control.append(range, input);

    range.addEventListener("pointerdown", (event) => beginSettingSliderGesture(range, input, event), { passive: true });
    range.addEventListener("pointermove", (event) => updateSettingSliderGesture(range, input, event), { passive: true });
    range.addEventListener("pointerup", () => endSettingSliderGesture(range), { passive: true });
    range.addEventListener("pointercancel", () => endSettingSliderGesture(range), { passive: true });
    if (!window.PointerEvent) {
      range.addEventListener("touchstart", (event) => beginSettingSliderGesture(range, input, event), { passive: true });
      range.addEventListener("touchmove", (event) => updateSettingSliderGesture(range, input, event), { passive: true });
      range.addEventListener("touchend", () => endSettingSliderGesture(range), { passive: true });
      range.addEventListener("touchcancel", () => endSettingSliderGesture(range), { passive: true });
    }
    range.addEventListener("input", (event) => {
      event.stopPropagation();
      if (settingSliderInputBlocked(range)) return;
      commitSettingSliderRange(input, range);
    });
    range.addEventListener("change", (event) => {
      event.stopPropagation();
      if (settingSliderInputBlocked(range)) return;
      commitSettingSliderRange(input, range, "change");
    });
    input.addEventListener("input", () => syncSettingSlider(input));
    input.addEventListener("change", () => normalizeSettingSliderInput(input));
    syncSettingSlider(input);
  }

  return {
    enhanceSettingSlider,
    normalizeSettingsSliders,
    syncSettingSlider,
    syncSettingsSliders,
  };
}

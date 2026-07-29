import { text } from "./format.js";

export function createSweetComboControls({
  combos = [],
  applySweetMenuPlacement,
  clearSweetMenuPlacement,
  closeSweetControlSet,
  closeSweetSelects,
} = {}) {
  const sweetComboControllers = new Map();

  function comboControlLabel(input) {
    const explicit = text(input.getAttribute("aria-label")).trim();
    if (explicit) return explicit;
    const label = input.closest("label");
    const caption = label
      ? [...label.children].find((child) => child.tagName === "SPAN")?.textContent
      : "";
    return text(caption).trim() || "候选项";
  }

  function comboClearLabel(input) {
    const explicit = text(input?.dataset?.emptyLabel).trim();
    if (explicit) return explicit;
    return "跟随默认";
  }

  function comboListOptions(controller) {
    const list = controller?.list;
    const input = controller?.input;
    const options = [];
    const seen = new Set();

    function addOption(value, label) {
      const optionValue = text(value).trim();
      if (seen.has(optionValue)) return;
      seen.add(optionValue);
      options.push({
        value: optionValue,
        label: text(label).trim() || optionValue,
      });
    }

    if (input?.dataset?.comboOptional !== "false") {
      addOption("", comboClearLabel(input));
    }

    for (const option of [...(list?.options || [])]) {
      const value = text(option.value).trim();
      const label = text(option.label || option.textContent || option.value).trim();
      if (value || label) addOption(value, label);
    }

    return options;
  }

  function comboFilteredOptions(controller) {
    const query = text(controller.input.value).trim().toLowerCase();
    const options = comboListOptions(controller);
    const exactValueSelected = options.some((option) => option.value && option.value.toLowerCase() === query);
    if (!query || exactValueSelected) return options;
    return options.filter((option) => (
      option.value.toLowerCase().includes(query)
      || option.label.toLowerCase().includes(query)
    ));
  }

  function comboDisplayLabel(option) {
    return text(option.label || option.value).trim() || "跟随默认";
  }

  function comboOptionSubtitle(option) {
    const label = comboDisplayLabel(option);
    const value = text(option.value).trim();
    if (!value || value === label || label.includes(value)) return "";
    return value;
  }

  function buildSweetComboOption(input, option, index) {
    const controller = sweetComboControllers.get(input);
    const item = document.createElement("button");
    const title = document.createElement("strong");
    const label = comboDisplayLabel(option);
    const subtitle = comboOptionSubtitle(option);
    item.type = "button";
    item.id = `${controller.id}-option-${index}`;
    item.className = "sweet-combo-option";
    item.dataset.index = String(index);
    item.dataset.value = option.value;
    item.role = "option";
    item.tabIndex = -1;
    item.setAttribute("aria-selected", option.value === input.value ? "true" : "false");
    item.title = subtitle ? `${label}\n${subtitle}` : label;
    item.classList.toggle("is-selected", option.value === input.value);
    item.classList.toggle("is-clear", !option.value);
    title.textContent = label;
    item.append(title);
    if (subtitle) {
      const detail = document.createElement("span");
      detail.textContent = subtitle;
      item.append(detail);
    }
    item.addEventListener("click", () => commitSweetCombo(input, index));
    return item;
  }

  function setSweetComboActive(input, index) {
    const controller = sweetComboControllers.get(input);
    if (!controller) return;
    const items = [...controller.menu.querySelectorAll(".sweet-combo-option")];
    const nextIndex = items.length ? Math.min(Math.max(index, 0), items.length - 1) : -1;
    controller.activeIndex = nextIndex;
    for (const item of items) {
      const active = Number(item.dataset.index) === nextIndex;
      item.classList.toggle("is-active", active);
      if (active) {
        input.setAttribute("aria-activedescendant", item.id);
        if (!controller.menu.hidden) item.scrollIntoView({ block: "nearest" });
      }
    }
  }

  function renderSweetCombo(input) {
    const controller = sweetComboControllers.get(input);
    if (!controller) return;
    const options = comboFilteredOptions(controller);
    controller.options = options;
    if (!options.length) {
      const empty = document.createElement("div");
      empty.className = "sweet-combo-empty";
      empty.textContent = "没有匹配的候选项";
      controller.menu.replaceChildren(empty);
      setSweetComboActive(input, -1);
      return;
    }
    controller.menu.replaceChildren(...options.map((option, index) => buildSweetComboOption(input, option, index)));
    const selectedIndex = options.findIndex((option) => option.value === input.value);
    setSweetComboActive(input, selectedIndex >= 0 ? selectedIndex : 0);
  }

  function closeSweetCombo(input) {
    const controller = sweetComboControllers.get(input);
    if (!controller || !controller.wrapper.classList.contains("is-open")) return;
    controller.wrapper.classList.remove("is-open");
    clearSweetMenuPlacement(controller);
    controller.panel?.classList.remove("has-open-select");
    controller.overlayHost?.classList.remove("has-open-select");
    controller.menu.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  }

  function closeSweetCombos(except = null) {
    closeSweetControlSet(sweetComboControllers, closeSweetCombo, except);
  }

  function updateSweetComboPlacement(input) {
    const controller = sweetComboControllers.get(input);
    if (controller) applySweetMenuPlacement(controller, input);
  }

  function updateOpenSweetComboPlacements() {
    for (const input of sweetComboControllers.keys()) updateSweetComboPlacement(input);
  }

  function openSweetCombo(input) {
    const controller = sweetComboControllers.get(input);
    if (!controller || input.disabled) return;
    closeSweetSelects();
    closeSweetCombos(input);
    renderSweetCombo(input);
    controller.wrapper.classList.add("is-open");
    controller.panel?.classList.add("has-open-select");
    controller.overlayHost?.classList.add("has-open-select");
    controller.menu.hidden = false;
    input.setAttribute("aria-expanded", "true");
    updateSweetComboPlacement(input);
  }

  function moveSweetComboActive(input, step) {
    const controller = sweetComboControllers.get(input);
    const items = controller ? controller.menu.querySelectorAll(".sweet-combo-option") : [];
    if (!controller || !items.length) return;
    const current = controller.activeIndex >= 0 ? controller.activeIndex : 0;
    const next = (current + step + items.length) % items.length;
    setSweetComboActive(input, next);
  }

  function commitSweetCombo(input, index) {
    const controller = sweetComboControllers.get(input);
    const option = controller?.options?.[index];
    if (!controller || !option) return;
    const previous = input.value;
    input.value = option.value;
    renderSweetCombo(input);
    closeSweetCombo(input);
    input.focus({ preventScroll: true });
    if (input.value !== previous) {
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  function handleSweetComboKeydown(input, event) {
    const controller = sweetComboControllers.get(input);
    if (!controller) return;
    const open = controller.wrapper.classList.contains("is-open");
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) openSweetCombo(input);
      moveSweetComboActive(input, event.key === "ArrowDown" ? 1 : -1);
      return;
    }
    if (event.key === "Enter" && open && controller.activeIndex >= 0) {
      event.preventDefault();
      commitSweetCombo(input, controller.activeIndex);
      return;
    }
    if (event.key === "Escape" && open) {
      event.preventDefault();
      closeSweetCombo(input);
    }
  }

  function syncSweetCombo(input) {
    const controller = sweetComboControllers.get(input);
    if (!controller) return;
    if (controller.wrapper.classList.contains("is-open")) {
      renderSweetCombo(input);
      updateSweetComboPlacement(input);
    }
  }

  function pruneDisconnectedSweetCombos() {
    for (const [input, controller] of sweetComboControllers.entries()) {
      if (!controller.wrapper.isConnected) sweetComboControllers.delete(input);
    }
  }

  function initSweetCombo(input, list) {
    if (!input || !list) return null;
    pruneDisconnectedSweetCombos();
    const current = sweetComboControllers.get(input);
    if (current) {
      current.list = list;
      syncSweetCombo(input);
      return current;
    }
    const id = `sweet-combo-${input.id || sweetComboControllers.size}`;
    const wrapper = document.createElement("div");
    const menu = document.createElement("div");
    const panel = input.closest(".panel, .settings-section");
    const overlayHost = input.closest(".control-grid, .panel-head, .settings-section");
    wrapper.className = "sweet-combo";
    wrapper.dataset.comboFor = input.id || "";
    const comboKind = text(input.dataset.comboKind || (input.id === "cfgLlmProviderId" ? "provider" : "")).trim();
    if (comboKind) wrapper.dataset.comboKind = comboKind;
    menu.id = `${id}-listbox`;
    menu.className = "sweet-combo-menu";
    menu.role = "listbox";
    menu.hidden = true;

    input.removeAttribute("list");
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-controls", menu.id);
    input.setAttribute("aria-label", comboControlLabel(input));
    input.insertAdjacentElement("beforebegin", wrapper);
    wrapper.append(input, menu);

    sweetComboControllers.set(input, {
      id,
      input,
      list,
      wrapper,
      menu,
      panel,
      overlayHost,
      options: [],
      activeIndex: -1,
      pointerDownOpen: false,
      pointerDown: false,
    });

    input.addEventListener("pointerdown", () => {
      const controller = sweetComboControllers.get(input);
      if (!controller) return;
      controller.pointerDown = true;
      controller.pointerDownOpen = controller.wrapper.classList.contains("is-open");
    });
    input.addEventListener("focus", () => {
      const controller = sweetComboControllers.get(input);
      if (!controller?.pointerDown) openSweetCombo(input);
    });
    input.addEventListener("click", () => {
      const controller = sweetComboControllers.get(input);
      if (!controller) return;
      if (controller.pointerDownOpen) {
        closeSweetCombo(input);
      } else {
        openSweetCombo(input);
      }
      controller.pointerDown = false;
      controller.pointerDownOpen = false;
    });
    input.addEventListener("input", () => syncSweetCombo(input));
    input.addEventListener("keydown", (event) => handleSweetComboKeydown(input, event));
    return sweetComboControllers.get(input);
  }

  function registerSweetCombo(input, list) {
    return initSweetCombo(input, list);
  }

  function initSweetCombos() {
    for (const combo of combos) registerSweetCombo(combo?.input, combo?.list);
    document.addEventListener("click", (event) => {
      pruneDisconnectedSweetCombos();
      for (const controller of sweetComboControllers.values()) {
        if (controller.wrapper.contains(event.target)) return;
      }
      closeSweetCombos();
    });
    window.addEventListener("resize", updateOpenSweetComboPlacements);
    window.addEventListener("scroll", updateOpenSweetComboPlacements, { passive: true, capture: true });
  }

  return {
    closeSweetCombos,
    initSweetCombos,
    registerSweetCombo,
    syncSweetCombo,
  };
}

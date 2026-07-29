import { text } from "./format.js";
import { createSweetComboControls } from "./combos.js";

const menuGap = 6;
const viewportPadding = 12;
const menuMaxHeight = 268;
const menuMinHeight = 96;
const providerMenuMaxWidth = 360;

export function createSweetControls({ selects = [], combos = [] } = {}) {
  const sweetSelectControllers = new Map();

  function sweetMenuPlacement(anchor, menu) {
    const rect = anchor.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom - viewportPadding;
    const spaceAbove = rect.top - viewportPadding;
    const menuHeight = Math.min(menu.scrollHeight || menuMaxHeight, menuMaxHeight);
    const dropUp = spaceBelow < menuHeight && spaceAbove > spaceBelow;
    const available = Math.max(
      menuMinHeight,
      Math.min(menuMaxHeight, (dropUp ? spaceAbove : spaceBelow) - menuGap),
    );
    return { dropUp, available };
  }

  function applySweetMenuPlacement(controller, anchor) {
    if (!controller || controller.menu.hidden) return;
    const { dropUp, available } = sweetMenuPlacement(anchor, controller.menu);
    controller.wrapper.classList.toggle("is-drop-up", dropUp);
    controller.wrapper.classList.toggle("is-drop-down", !dropUp);
    controller.wrapper.style.setProperty("--sweet-select-menu-max-height", `${available}px`);
    if (controller.wrapper.dataset.comboKind === "provider") {
      const rect = anchor.getBoundingClientRect();
      const boundary = controller.overlayHost?.getBoundingClientRect?.();
      const boundaryLeft = boundary?.left ?? viewportPadding;
      const boundaryRight = boundary?.right ?? window.innerWidth - viewportPadding;
      const width = Math.min(
        providerMenuMaxWidth,
        Math.max(rect.width, boundaryRight - boundaryLeft),
        Math.max(0, window.innerWidth - viewportPadding * 2),
      );
      const minLeft = boundaryLeft - rect.left;
      const maxLeft = boundaryRight - rect.left - width;
      const left = Math.max(minLeft, Math.min(0, maxLeft));
      controller.menu.style.left = `${left}px`;
      controller.menu.style.right = "auto";
      controller.menu.style.width = `${width}px`;
    }
  }

  function clearSweetMenuPlacement(controller) {
    controller.wrapper.classList.remove("is-drop-up", "is-drop-down");
    controller.wrapper.style.removeProperty("--sweet-select-menu-max-height");
    controller.menu.style.removeProperty("left");
    controller.menu.style.removeProperty("right");
    controller.menu.style.removeProperty("width");
  }

  function closeSweetControlSet(controllers, closeControl, except = null) {
    for (const control of controllers.keys()) {
      if (control !== except) closeControl(control);
    }
  }

  function selectControlLabel(select) {
    const explicit = text(select.getAttribute("aria-label")).trim();
    if (explicit) return explicit;
    const label = select.closest("label");
    const caption = label
      ? [...label.children].find((child) => child.tagName === "SPAN")?.textContent
      : "";
    return text(caption).trim() || "下拉选择";
  }

  function selectOptionText(option) {
    return text(option?.textContent || option?.label || option?.value).trim() || "请选择";
  }

  function currentSelectOption(select) {
    return select.options[select.selectedIndex] || select.options[0] || null;
  }

  function selectableOptionIndexes(select) {
    return [...select.options]
      .map((option, index) => (option.disabled ? -1 : index))
      .filter((index) => index >= 0);
  }

  function sweetSelectOptionSignature(select) {
    return [...select.options]
      .map((option) => [
        option.value,
        selectOptionText(option),
        option.disabled ? "1" : "0",
      ].join("\u001f"))
      .join("\u001e");
  }

  function buildSweetSelectOptions(select, controller, selected) {
    return [...select.options].map((option, index) => {
      const item = document.createElement("button");
      item.type = "button";
      item.id = `${controller.id}-option-${index}`;
      item.className = "sweet-select-option";
      item.dataset.index = String(index);
      item.role = "option";
      item.tabIndex = -1;
      item.addEventListener("click", () => commitSweetSelect(select, index));
      return syncSweetSelectOption(item, option, option === selected);
    });
  }

  function syncSweetSelectOption(item, option, isSelected) {
    item.disabled = option.disabled;
    item.textContent = selectOptionText(option);
    item.setAttribute("aria-selected", isSelected ? "true" : "false");
    item.classList.toggle("is-selected", isSelected);
    return item;
  }

  function setSweetSelectActive(select, index) {
    const controller = sweetSelectControllers.get(select);
    if (!controller) return;
    const selectable = selectableOptionIndexes(select);
    const fallback = selectable.includes(select.selectedIndex) ? select.selectedIndex : selectable[0] ?? -1;
    controller.activeIndex = selectable.includes(index) ? index : fallback;
    for (const option of controller.menu.querySelectorAll(".sweet-select-option")) {
      const active = Number(option.dataset.index) === controller.activeIndex;
      option.classList.toggle("is-active", active);
      if (active) {
        controller.trigger.setAttribute("aria-activedescendant", option.id);
        if (!controller.menu.hidden) option.scrollIntoView({ block: "nearest" });
      }
    }
  }

  function syncSweetSelect(select) {
    const controller = sweetSelectControllers.get(select);
    if (!controller) return;
    const selected = currentSelectOption(select);
    const selectedText = selectOptionText(selected);
    const disabled = select.disabled || !select.options.length;
    const optionSignature = sweetSelectOptionSignature(select);

    if (optionSignature !== controller.optionSignature) {
      controller.menu.replaceChildren(...buildSweetSelectOptions(select, controller, selected));
      controller.optionSignature = optionSignature;
    } else {
      for (const item of controller.menu.querySelectorAll(".sweet-select-option")) {
        const option = select.options[Number(item.dataset.index)];
        if (option) syncSweetSelectOption(item, option, option === selected);
      }
    }

    controller.value.textContent = selectedText;
    controller.wrapper.classList.toggle("is-disabled", disabled);
    controller.trigger.disabled = disabled;
    controller.trigger.setAttribute("aria-disabled", disabled ? "true" : "false");
    controller.trigger.setAttribute("aria-label", `${selectControlLabel(select)}：${selectedText}`);
    setSweetSelectActive(select, selected ? select.selectedIndex : -1);
  }

  function closeSweetSelect(select) {
    const controller = sweetSelectControllers.get(select);
    if (!controller || !controller.wrapper.classList.contains("is-open")) return;
    controller.wrapper.classList.remove("is-open");
    clearSweetMenuPlacement(controller);
    controller.panel?.classList.remove("has-open-select");
    controller.overlayHost?.classList.remove("has-open-select");
    controller.menu.hidden = true;
    controller.trigger.setAttribute("aria-expanded", "false");
    controller.trigger.removeAttribute("aria-activedescendant");
  }

  function closeSweetSelects(except = null) {
    closeSweetControlSet(sweetSelectControllers, closeSweetSelect, except);
  }

  function updateSweetSelectPlacement(select) {
    const controller = sweetSelectControllers.get(select);
    if (controller) applySweetMenuPlacement(controller, controller.trigger);
  }

  function updateOpenSweetSelectPlacements() {
    for (const select of sweetSelectControllers.keys()) {
      updateSweetSelectPlacement(select);
    }
  }

  function openSweetSelect(select) {
    const controller = sweetSelectControllers.get(select);
    if (!controller || controller.trigger.disabled) return;
    syncSweetSelect(select);
    closeSweetCombos();
    closeSweetSelects(select);
    controller.wrapper.classList.add("is-open");
    controller.panel?.classList.add("has-open-select");
    controller.overlayHost?.classList.add("has-open-select");
    controller.menu.hidden = false;
    updateSweetSelectPlacement(select);
    controller.trigger.setAttribute("aria-expanded", "true");
    setSweetSelectActive(select, select.selectedIndex);
  }

  function moveSweetSelectActive(select, step) {
    const selectable = selectableOptionIndexes(select);
    if (!selectable.length) return;
    const controller = sweetSelectControllers.get(select);
    const current = controller?.activeIndex ?? select.selectedIndex;
    const currentPosition = Math.max(0, selectable.indexOf(current));
    const nextPosition = (currentPosition + step + selectable.length) % selectable.length;
    setSweetSelectActive(select, selectable[nextPosition]);
  }

  function commitSweetSelect(select, index) {
    const option = select.options[index];
    const controller = sweetSelectControllers.get(select);
    if (!option || option.disabled || !controller) return;
    const previous = select.value;
    select.selectedIndex = index;
    syncSweetSelect(select);
    closeSweetSelect(select);
    controller.trigger.focus({ preventScroll: true });
    if (select.value !== previous) {
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  function handleSweetSelectKeydown(select, event) {
    const controller = sweetSelectControllers.get(select);
    if (!controller) return;
    const open = controller.wrapper.classList.contains("is-open");
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) openSweetSelect(select);
      moveSweetSelectActive(select, event.key === "ArrowDown" ? 1 : -1);
      return;
    }
    if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      if (!open) openSweetSelect(select);
      const selectable = selectableOptionIndexes(select);
      setSweetSelectActive(select, event.key === "Home" ? selectable[0] : selectable.at(-1));
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (open) {
        commitSweetSelect(select, controller.activeIndex);
      } else {
        openSweetSelect(select);
      }
      return;
    }
    if (event.key === "Escape" && open) {
      event.preventDefault();
      closeSweetSelect(select);
    }
  }

  function initSweetSelect(select) {
    if (!select || sweetSelectControllers.has(select)) return;
    const id = `sweet-select-${select.id || sweetSelectControllers.size}`;
    const wrapper = document.createElement("div");
    const trigger = document.createElement("button");
    const value = document.createElement("span");
    const arrow = document.createElement("span");
    const menu = document.createElement("div");
    const panel = select.closest(".panel");
    const overlayHost = select.closest(".control-grid, .panel-head");

    wrapper.className = "sweet-select";
    if (select.classList.contains("compact-select")) wrapper.classList.add("is-compact");
    if (select.classList.contains("media-type-filter")) wrapper.classList.add("is-media-type");
    wrapper.dataset.selectFor = select.id || "";

    trigger.type = "button";
    trigger.className = "sweet-select-trigger";
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");
    trigger.setAttribute("aria-controls", `${id}-listbox`);

    value.className = "sweet-select-value";
    arrow.className = "sweet-select-arrow";
    arrow.setAttribute("aria-hidden", "true");
    menu.id = `${id}-listbox`;
    menu.className = "sweet-select-menu";
    menu.role = "listbox";
    menu.hidden = true;

    trigger.append(value, arrow);
    wrapper.append(trigger, menu);
    select.classList.add("native-select");
    select.tabIndex = -1;
    select.setAttribute("aria-hidden", "true");
    select.insertAdjacentElement("afterend", wrapper);

    const controller = {
      id,
      wrapper,
      trigger,
      value,
      menu,
      panel,
      overlayHost,
      activeIndex: select.selectedIndex,
      optionSignature: "",
      observer: null,
    };
    sweetSelectControllers.set(select, controller);

    trigger.addEventListener("click", () => {
      if (wrapper.classList.contains("is-open")) {
        closeSweetSelect(select);
      } else {
        openSweetSelect(select);
      }
    });
    trigger.addEventListener("keydown", (event) => handleSweetSelectKeydown(select, event));
    select.addEventListener("change", () => syncSweetSelect(select));
    controller.observer = new MutationObserver(() => syncSweetSelect(select));
    controller.observer.observe(select, {
      attributes: true,
      attributeFilter: ["disabled"],
      childList: true,
      subtree: true,
    });
    syncSweetSelect(select);
  }

  function initSweetSelects() {
    for (const select of selects) initSweetSelect(select);
    document.addEventListener("click", (event) => {
      for (const controller of sweetSelectControllers.values()) {
        if (controller.wrapper.contains(event.target)) return;
      }
      closeSweetSelects();
    });
    window.addEventListener("resize", updateOpenSweetSelectPlacements);
    window.addEventListener("scroll", updateOpenSweetSelectPlacements, { passive: true, capture: true });
  }

  function syncSweetSelects() {
    for (const select of sweetSelectControllers.keys()) syncSweetSelect(select);
  }

  const {
    closeSweetCombos,
    initSweetCombos,
    registerSweetCombo,
    syncSweetCombo,
  } = createSweetComboControls({
    combos,
    applySweetMenuPlacement,
    clearSweetMenuPlacement,
    closeSweetControlSet,
    closeSweetSelects,
  });

  return {
    closeSweetSelects,
    initSweetCombos,
    initSweetSelects,
    registerSweetCombo,
    syncSweetCombo,
    syncSweetSelect,
    syncSweetSelects,
  };
}

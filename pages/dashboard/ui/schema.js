import { text } from "./format.js";

import {
  settingsExtraSchemaSelector,
  settingsFieldSchema,
  settingsMappedSchemaFields,
  settingsPayloadGroups,
  settingsSectionSchema,
} from "./schemamap.js";

export {
  settingsExtraSchemaSelector,
  settingsMappedSchemaFields,
  settingsPayloadGroups,
  settingsSectionSchema,
};

export function settingsSchemaBindings() {
  return { ...settingsFieldSchema };
}

export function schemaMetaForMapping(schema, mapping = {}) {
  if (mapping.root) return schema.root?.[mapping.root] || {};
  return schema.sections?.[mapping.section]?.fields?.[mapping.field] || {};
}

export function cleanSchemaLabel(value) {
  return text(value)
    .replace(/^[^\w\u4e00-\u9fff【】]+/u, "")
    .trim();
}

export function schemaBindingMeta(configData, mapping = {}) {
  return schemaMetaForMapping(configData?.schema_meta || {}, mapping);
}

export function schemaBindingValue(configData, mapping = {}) {
  const values = configData?.schema_values || {};
  if (mapping.root) return values.root?.[mapping.root];
  return values.sections?.[mapping.section]?.[mapping.field];
}

export function schemaValueToInputText(value) {
  if (Array.isArray(value)) return value.join("\n");
  return value ?? "";
}

export function schemaValueOrDefault(value, meta = {}) {
  return value ?? meta.default;
}

function intValue(value, fallback, min, max) {
  const parsed = Number.parseInt(text(value).trim(), 10);
  const number = Number.isFinite(parsed) ? parsed : fallback;
  return Math.min(max, Math.max(min, number));
}

function linesToArray(value) {
  return text(value)
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function setSchemaInputValue(input, value, meta = {}, syncSettingSlider = null) {
  if (!input) return;
  const nextValue = schemaValueOrDefault(value, meta);
  if (input.type === "checkbox") {
    input.checked = Boolean(nextValue);
    return;
  }
  const inputText = schemaValueToInputText(nextValue);
  input.defaultValue = inputText;
  input.value = inputText;
  syncSettingSlider?.(input);
}

export function schemaInputValue(input, meta = {}) {
  const type = text(meta.type || "string").toLowerCase();
  if (input?.type === "checkbox" || type === "bool") return Boolean(input?.checked);
  const slider = meta.slider || {};
  if (type === "int") {
    return intValue(
      input?.value,
      Number(meta.default ?? 0),
      Number(slider.min ?? -2147483648),
      Number(slider.max ?? 2147483647),
    );
  }
  if (type === "float" || type === "number") {
    const raw = text(input?.value).trim();
    const parsed = raw === "" ? Number(meta.default ?? 0) : Number(raw);
    const fallback = Number(meta.default ?? 0);
    const number = Number.isFinite(parsed) ? parsed : fallback;
    return Math.min(
      Number(slider.max ?? Number.MAX_SAFE_INTEGER),
      Math.max(Number(slider.min ?? -Number.MAX_SAFE_INTEGER), number),
    );
  }
  if (type === "list") return linesToArray(input?.value);
  return text(input?.value).trim();
}

export function applyBoundSchemaValues(configData, elements, syncSettingSlider) {
  for (const [id, mapping] of Object.entries(settingsSchemaBindings())) {
    const input = elements[id] || document.getElementById(id);
    if (!input) continue;
    setSchemaInputValue(
      input,
      schemaBindingValue(configData, mapping),
      schemaBindingMeta(configData, mapping),
      syncSettingSlider,
    );
  }
}

function writeBoundSchemaPayload(payload, id, targetSection, { configData, elements }) {
  const mapping = settingsSchemaBindings()[id];
  const input = elements[id] || document.getElementById(id);
  if (!mapping || !input) return;
  const value = schemaInputValue(input, schemaBindingMeta(configData, mapping));
  if (mapping.root) {
    if (mapping.root === "enable_auto_share") {
      payload.enabled = value;
    } else {
      payload.schema_extra.root[mapping.root] = value;
    }
    return;
  }
  if (!payload.sections[targetSection]) payload.sections[targetSection] = {};
  payload.sections[targetSection][mapping.field] = value;
}

export function writeBoundSchemaFields(payload, targetSection, ids, options) {
  for (const id of ids) {
    writeBoundSchemaPayload(payload, id, targetSection, options);
  }
}

function sectionNodeBySchema(settingsSections, schemaSection) {
  const candidates = Object.entries(settingsSectionSchema)
    .filter(([, mapping]) => mapping.section === schemaSection)
    .map(([key]) => key);
  const preferred = candidates.find((key) => !/Sequence$/i.test(key)) || candidates[0];
  return settingsSections.find((section) => section.dataset.settingsSection === preferred) || null;
}

function extraFieldLabel(meta = {}, key = "") {
  return cleanSchemaLabel(meta.description || meta.title || key) || key;
}

function makeExtraSelect(meta = {}) {
  const select = document.createElement("select");
  for (const option of meta.options || []) {
    const value = text(option).trim();
    select.append(new Option(value, value));
  }
  return select;
}

function makeExtraInput(meta = {}) {
  const type = text(meta.type || "string").toLowerCase();
  if (type === "bool") {
    const input = document.createElement("input");
    input.type = "checkbox";
    return input;
  }
  if (type === "list") {
    const input = document.createElement("textarea");
    input.rows = meta.items?.options ? 4 : 3;
    return input;
  }
  const input = document.createElement("input");
  input.type = type === "int" || type === "float" || type === "number" ? "number" : "text";
  if (meta._special === "select_provider") {
    input.setAttribute("list", "cfgLlmProviderOptions");
    input.placeholder = "跟随默认";
    input.dataset.emptyLabel = "跟随默认";
    input.dataset.comboKind = "provider";
    input.dataset.schemaProviderCombo = "1";
    input.autocomplete = "off";
  }
  if (meta._special === "select_adapter") {
    input.setAttribute("list", "cfgAdapterOptions");
    input.placeholder = "默认第一个实例";
    input.dataset.emptyLabel = "默认第一个实例";
    input.dataset.comboKind = "adapter";
    input.dataset.schemaAdapterCombo = "1";
    input.autocomplete = "off";
  }
  if (!input.dataset.comboKind && meta.options?.length) return makeExtraSelect(meta);
  return input;
}

function makeExtraField({ scope, section, key, meta }) {
  const input = makeExtraInput(meta);
  const label = document.createElement("label");
  label.className = input.type === "checkbox" ? "setting-switch setting-extra-field" : "setting-field setting-extra-field";
  label.dataset.schemaExtra = "1";
  label.dataset.schemaScope = scope;
  if (section) label.dataset.schemaSection = section;
  label.dataset.schemaField = key;

  const caption = document.createElement("span");
  caption.textContent = extraFieldLabel(meta, key);
  if (input.type === "checkbox") {
    label.append(input, caption);
  } else {
    label.append(caption, input);
  }
  return label;
}

function ensureExtraGroup(section) {
  let group = section.querySelector(":scope > .settings-extra-fields");
  if (group) return group;
  group = document.createElement("div");
  group.className = "settings-extra-fields";
  group.dataset.schemaExtraGroup = "1";
  section.append(group);
  return group;
}

export function ensureSchemaExtraFields(data, settingsSections) {
  const schema = data.schema_meta || {};
  const mapped = settingsMappedSchemaFields();
  for (const group of document.querySelectorAll("[data-schema-extra-group]")) {
    group.remove();
  }

  const addField = (sectionNode, args) => {
    ensureExtraGroup(sectionNode).append(makeExtraField(args));
  };

  for (const [key, meta] of Object.entries(schema.root || {})) {
    if (mapped.root.has(key)) continue;
    const target = settingsSections.find((section) => section.dataset.settingsSection === "basic");
    if (target) addField(target, { scope: "root", key, meta });
  }

  for (const [sectionKey, sectionMeta] of Object.entries(schema.sections || {})) {
    const target = sectionNodeBySchema(settingsSections, sectionKey);
    if (!target) continue;
    const mappedFields = mapped.sections.get(sectionKey) || new Set();
    for (const [fieldKey, meta] of Object.entries(sectionMeta.fields || {})) {
      if (mappedFields.has(fieldKey)) continue;
      addField(target, { scope: "section", section: sectionKey, key: fieldKey, meta });
    }
  }

  for (const group of document.querySelectorAll("[data-schema-extra-group]")) {
    if (!group.querySelector(".setting-extra-field")) group.remove();
  }
}

export function schemaExtraMeta(schema, wrapper) {
  const scope = wrapper?.dataset?.schemaScope || "";
  const key = wrapper?.dataset?.schemaField || "";
  if (scope === "root") return schema.root?.[key] || {};
  const section = wrapper?.dataset?.schemaSection || "";
  return schema.sections?.[section]?.fields?.[key] || {};
}

export function schemaExtraValue(configData, wrapper) {
  const values = configData?.schema_values || {};
  const scope = wrapper?.dataset?.schemaScope || "";
  const key = wrapper?.dataset?.schemaField || "";
  if (scope === "root") return values.root?.[key];
  const section = wrapper?.dataset?.schemaSection || "";
  return values.sections?.[section]?.[key];
}

export function schemaExtraInput(wrapper) {
  return wrapper?.querySelector("textarea, select, input:not([type='range'])") || null;
}

export function applySchemaSpecialCombos(configForm, registerSweetCombo, lists = {}) {
  const specs = [
    ["[data-schema-provider-combo]", lists.provider],
    ["[data-schema-adapter-combo]", lists.adapter],
  ];
  for (const [selector, list] of specs) {
    if (!list) continue;
    for (const input of configForm?.querySelectorAll(selector) || []) {
      registerSweetCombo?.(input, list);
    }
  }
}

export function applySchemaExtraValues(configData, configForm, syncSettingSlider) {
  const schema = configData?.schema_meta || {};
  for (const wrapper of configForm?.querySelectorAll(settingsExtraSchemaSelector) || []) {
    setSchemaInputValue(
      schemaExtraInput(wrapper),
      schemaExtraValue(configData, wrapper),
      schemaExtraMeta(schema, wrapper),
      syncSettingSlider,
    );
  }
}

export function collectSchemaExtraPayload(configData, configForm) {
  const extra = { root: {}, sections: {} };
  const schema = configData?.schema_meta || {};
  for (const wrapper of configForm?.querySelectorAll(settingsExtraSchemaSelector) || []) {
    const input = schemaExtraInput(wrapper);
    const key = wrapper.dataset.schemaField || "";
    if (!input || !key) continue;
    const value = schemaInputValue(input, schemaExtraMeta(schema, wrapper));
    if (wrapper.dataset.schemaScope === "root") {
      extra.root[key] = value;
      continue;
    }
    const section = wrapper.dataset.schemaSection || "";
    if (!section) continue;
    if (!extra.sections[section]) extra.sections[section] = {};
    extra.sections[section][key] = value;
  }
  return extra;
}

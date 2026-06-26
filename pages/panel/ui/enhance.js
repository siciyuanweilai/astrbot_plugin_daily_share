import { text } from "./format.js?v=20260614-smart-schedule";
import {
  cleanSchemaLabel,
  ensureSchemaExtraFields,
  schemaExtraMeta,
  schemaMetaForMapping,
  settingsExtraSchemaSelector,
  settingsSectionSchema,
  settingsSchemaBindings,
} from "./schema.js?v=20260626-qzone-adapter";
import { createSettingSliderEnhancements } from "./sliders.js?v=20260626-clean-settings";

function fieldCaptionNode(field) {
  return [...field.children].find((child) => child.tagName === "SPAN") || null;
}

function ensureFieldHint(field) {
  let hint = field.querySelector(":scope > .setting-hint");
  if (!hint) {
    hint = document.createElement("p");
    hint.className = "setting-hint";
    field.append(hint);
  }
  return hint;
}

function ensureSectionNote(section) {
  let note = section.querySelector(":scope > .settings-section-note");
  if (!note) {
    note = document.createElement("p");
    note.className = "settings-section-note";
    const title = section.querySelector(":scope > .settings-section-title");
    title?.insertAdjacentElement("afterend", note);
  }
  return note;
}

export function createSettingsEnhancements({
  configForm,
  settingsSections = [],
  elements = {},
} = {}) {
  const {
    enhanceSettingSlider,
    normalizeSettingsSliders,
    syncSettingSlider,
    syncSettingsSliders,
  } = createSettingSliderEnhancements({ configForm });

  function enhanceSettingField(input, meta = {}) {
    const field = input?.closest?.(".setting-field, .setting-switch");
    if (!field) return;
    const caption = fieldCaptionNode(field);
    const label = cleanSchemaLabel(meta.description || meta.title);
    if (caption && label) caption.textContent = label;

    const hintText = text(meta.hint).trim();
    if (hintText) {
      field.classList.add("has-schema-hint");
      const hint = ensureFieldHint(field);
      hint.textContent = hintText;
      if (input.id) {
        hint.id = `${input.id}Hint`;
        input.setAttribute("aria-describedby", hint.id);
      }
    }

    if (meta.slider) {
      enhanceSettingSlider(input, meta.slider);
    }
  }

  function applyTargetSchemaGuide(schema = {}) {
    const fields = schema.sections?.receiver?.fields || {};
    const pairs = [
      [fields.groups, elements.targetGroupsGuideTitle, elements.targetGroupsGuideHint],
      [fields.users, elements.targetUsersGuideTitle, elements.targetUsersGuideHint],
    ];
    for (const [meta, titleNode, hintNode] of pairs) {
      if (!meta) continue;
      const title = cleanSchemaLabel(meta.title || meta.description);
      const hint = text(meta.hint).trim();
      if (titleNode && title) titleNode.textContent = title;
      if (hintNode) hintNode.textContent = hint;
    }
  }

  function applySettingsSchemaEnhancements(data = {}) {
    const schema = data.schema_meta || {};
    if (!schema.sections && !schema.root) return;
    ensureSchemaExtraFields(data, settingsSections);

    for (const section of settingsSections) {
      const key = section.dataset.settingsSection || "";
      const sectionMapping = settingsSectionSchema[key] || {};
      const meta = schema.sections?.[sectionMapping.section] || {};
      const title = cleanSchemaLabel(sectionMapping.title || meta.description || meta.title);
      const noteText = text(sectionMapping.hint || meta.hint || meta.description).trim();
      const titleNode = section.querySelector(":scope > .settings-section-title");
      if (titleNode && title) titleNode.textContent = title;
      if (noteText) ensureSectionNote(section).textContent = noteText;
    }

    for (const [id, mapping] of Object.entries(settingsSchemaBindings())) {
      const input = elements[id] || document.getElementById(id);
      if (!input) continue;
      const meta = schemaMetaForMapping(schema, mapping);
      if (Object.keys(meta).length) enhanceSettingField(input, meta);
    }
    for (const wrapper of configForm?.querySelectorAll(settingsExtraSchemaSelector) || []) {
      const input = wrapper.querySelector("input, textarea, select");
      const meta = schemaExtraMeta(schema, wrapper);
      if (input && Object.keys(meta).length) enhanceSettingField(input, meta);
    }
    applyTargetSchemaGuide(schema);
    syncSettingsSliders();
  }

  return {
    applySettingsSchemaEnhancements,
    normalizeSettingsSliders,
    syncSettingSlider,
  };
}

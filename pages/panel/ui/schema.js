import { text } from "./format.js?v=20260614-smart-schedule";

export const settingsExtraSchemaSelector = "[data-schema-extra]";

export const settingsSectionSchema = {
  target: { section: "receiver", title: "分享目标设置" },
  basic: { section: "basic_conf" },
  sequence: {
    section: "basic_conf",
    title: "全局时段序列",
    hint: "当本次分享类型为自动时，会按当前时段的序列循环选择分享类型；智能定时若指定具体类型，会优先使用计划类型。",
  },
  briefing: { section: "extra_shares" },
  content: { section: "content_library" },
  context: { section: "context_conf" },
  news: { section: "news_conf" },
  media: { section: "image_conf" },
  tts: { section: "tts_conf" },
  weixin: {
    section: "image_conf",
    title: "个人微信图片",
    hint: "这些选项只影响个人微信图片发送前的压缩、超时和临时文件清理。",
  },
  qzone: { section: "qzone_conf" },
  qzoneSequence: {
    section: "qzone_conf",
    title: "QQ空间时段序列",
    hint: "当本次说说类型为自动时，会按当前时段的序列循环选择说说类型；智能定时若指定具体类型，会优先使用计划类型。",
  },
  llm: { section: "llm_conf" },
};

const settingsFieldSchema = {
  cfgEnabled: { root: "enable_auto_share" },
  cfgTargetGroups: { section: "receiver", field: "groups" },
  cfgTargetUsers: { section: "receiver", field: "users" },
  cfgContactAliases: { root: "contact_aliases" },
  cfgBasicTriggerMode: { section: "basic_conf", field: "trigger_mode" },
  cfgBasicFixedTimes: { section: "basic_conf", field: "fixed_times" },
  cfgBasicShareCron: { section: "basic_conf", field: "share_cron" },
  cfgBasicRandomPeriods: { section: "basic_conf", field: "random_periods" },
  cfgBasicSmartMaxCount: { section: "basic_conf", field: "smart_schedule_max_count" },
  cfgBasicSmartQuietHours: { section: "basic_conf", field: "smart_schedule_quiet_hours" },
  cfgBasicSmartPrompt: { section: "basic_conf", field: "smart_schedule_prompt" },
  cfgBasicCronDelay: { section: "basic_conf", field: "cron_random_delay" },
  cfgBasicShareType: { section: "basic_conf", field: "share_type" },
  cfgBasicRetentionDays: { section: "basic_conf", field: "data_retention_days" },
  cfgBasicDynamicDays: { section: "basic_conf", field: "dashboard_dynamic_days" },
  cfgDawnSequence: { section: "basic_conf", field: "dawn_sequence" },
  cfgMorningSequence: { section: "basic_conf", field: "morning_sequence" },
  cfgForenoonSequence: { section: "basic_conf", field: "forenoon_sequence" },
  cfgNoonSequence: { section: "basic_conf", field: "noon_sequence" },
  cfgAfternoonSequence: { section: "basic_conf", field: "afternoon_sequence" },
  cfgEveningSequence: { section: "basic_conf", field: "evening_sequence" },
  cfgNightSequence: { section: "basic_conf", field: "night_sequence" },
  cfgLateNightSequence: { section: "basic_conf", field: "late_night_sequence" },
  cfgReferenceHistoryCount: { section: "context_conf", field: "reference_history_count" },
  cfgLifeContext: { section: "context_conf", field: "enable_life_context" },
  cfgLifeContextGroup: { section: "context_conf", field: "life_context_in_group" },
  cfgGroupSchedule: { section: "context_conf", field: "group_share_schedule" },
  cfgChatHistory: { section: "context_conf", field: "enable_chat_history" },
  cfgDeepHistory: { section: "context_conf", field: "enable_deep_history" },
  cfgDeepHistoryHours: { section: "context_conf", field: "deep_history_hours" },
  cfgDeepHistoryMaxCount: { section: "context_conf", field: "deep_history_max_count" },
  cfgPrivateHistoryCount: { section: "context_conf", field: "private_history_count" },
  cfgGroupIntensityCount: { section: "context_conf", field: "group_intensity_check_count" },
  cfgGroupShareStrategy: { section: "context_conf", field: "group_share_strategy" },
  cfgRecordMemory: { section: "context_conf", field: "record_share_to_memory" },
  cfgBriefingGroups: { section: "extra_shares", field: "briefing_groups" },
  cfgBriefingUsers: { section: "extra_shares", field: "briefing_users" },
  cfgBriefing60s: { section: "extra_shares", field: "enable_60s_news" },
  cfgBriefingAi: { section: "extra_shares", field: "enable_ai_news" },
  cfgBriefingQzoneSync: { section: "extra_shares", field: "sync_briefing_to_qzone" },
  cfgBriefingScheduleMode: { section: "extra_shares", field: "briefing_schedule_mode" },
  cfgBriefingFixedTimes: { section: "extra_shares", field: "briefing_fixed_times" },
  cfgBriefingRandomPeriods: { section: "extra_shares", field: "briefing_random_periods" },
  cfgBriefingCron: { section: "extra_shares", field: "cron_briefing" },
  cfgBriefingSmartMaxCount: { section: "extra_shares", field: "briefing_smart_schedule_max_count" },
  cfgBriefingSmartQuietHours: { section: "extra_shares", field: "briefing_smart_schedule_quiet_hours" },
  cfgBriefingSmartPrompt: { section: "extra_shares", field: "briefing_smart_schedule_prompt" },
  cfgBriefingDelay: { section: "extra_shares", field: "briefing_cron_random_delay" },
  cfgQzoneEnabled: { section: "qzone_conf", field: "enable_qzone" },
  cfgQzoneTimeout: { section: "qzone_conf", field: "qzone_api_timeout_seconds" },
  cfgQzoneTriggerMode: { section: "qzone_conf", field: "qzone_trigger_mode" },
  cfgQzoneFixedTimes: { section: "qzone_conf", field: "qzone_fixed_times" },
  cfgQzoneCron: { section: "qzone_conf", field: "qzone_cron" },
  cfgQzoneRandomPeriods: { section: "qzone_conf", field: "qzone_random_periods" },
  cfgQzoneSmartMaxCount: { section: "qzone_conf", field: "qzone_smart_schedule_max_count" },
  cfgQzoneSmartQuietHours: { section: "qzone_conf", field: "qzone_smart_schedule_quiet_hours" },
  cfgQzoneSmartPrompt: { section: "qzone_conf", field: "qzone_smart_schedule_prompt" },
  cfgQzoneShareType: { section: "qzone_conf", field: "qzone_share_type" },
  cfgQzoneImage: { section: "qzone_conf", field: "qzone_enable_image" },
  cfgQzoneHotImage: { section: "qzone_conf", field: "qzone_attach_hot_news_image" },
  cfgQzoneImageTypes: { section: "qzone_conf", field: "qzone_image_enabled_types" },
  cfgQzoneVideo: { section: "qzone_conf", field: "qzone_enable_video" },
  cfgQzoneVideoTypes: { section: "qzone_conf", field: "qzone_video_enabled_types" },
  cfgQzoneAutoInteraction: { section: "qzone_conf", field: "qzone_enable_auto_interaction" },
  cfgQzoneAutoInteractionInterval: { section: "qzone_conf", field: "qzone_auto_interaction_interval_minutes" },
  cfgQzoneAutoInteractionCron: { section: "qzone_conf", field: "qzone_auto_interaction_cron" },
  cfgQzoneAutoLike: { section: "qzone_conf", field: "qzone_enable_auto_like" },
  cfgQzoneAutoLikeLimit: { section: "qzone_conf", field: "qzone_auto_like_limit" },
  cfgQzoneAutoComment: { section: "qzone_conf", field: "qzone_enable_auto_comment" },
  cfgQzoneAutoCommentLimit: { section: "qzone_conf", field: "qzone_auto_comment_limit" },
  cfgQzoneAutoCommentPrompt: { section: "qzone_conf", field: "qzone_auto_comment_prompt" },
  cfgQzoneAutoReply: { section: "qzone_conf", field: "qzone_enable_auto_reply" },
  cfgQzoneAutoReplyLimit: { section: "qzone_conf", field: "qzone_auto_reply_limit" },
  cfgQzoneAutoReplyPrompt: { section: "qzone_conf", field: "qzone_auto_reply_prompt" },
  cfgQzoneDawnSequence: { section: "qzone_conf", field: "qzone_dawn_sequence" },
  cfgQzoneMorningSequence: { section: "qzone_conf", field: "qzone_morning_sequence" },
  cfgQzoneForenoonSequence: { section: "qzone_conf", field: "qzone_forenoon_sequence" },
  cfgQzoneNoonSequence: { section: "qzone_conf", field: "qzone_noon_sequence" },
  cfgQzoneAfternoonSequence: { section: "qzone_conf", field: "qzone_afternoon_sequence" },
  cfgQzoneEveningSequence: { section: "qzone_conf", field: "qzone_evening_sequence" },
  cfgQzoneNightSequence: { section: "qzone_conf", field: "qzone_night_sequence" },
  cfgQzoneLateNightSequence: { section: "qzone_conf", field: "qzone_late_night_sequence" },
  cfgKnowledgePrefix: { section: "content_library", field: "show_knowledge_type_prefix" },
  cfgRecPrefix: { section: "content_library", field: "show_rec_type_prefix" },
  cfgKnowledgeCats: { section: "content_library", field: "knowledge_cats" },
  cfgRecCats: { section: "content_library", field: "rec_cats" },
  cfgAiImage: { section: "image_conf", field: "enable_ai_image" },
  cfgHotImage: { section: "image_conf", field: "attach_hot_news_image" },
  cfgNewsImageCleanupMax: { section: "image_conf", field: "news_image_cleanup_max_count" },
  cfgPriorityText: { section: "image_conf", field: "priority_text_over_schedule" },
  cfgAiVideo: { section: "image_conf", field: "enable_ai_video" },
  cfgSeparateMedia: { section: "image_conf", field: "separate_text_and_image" },
  cfgSeparateDelay: { section: "image_conf", field: "separate_send_delay" },
  cfgRecordImageDesc: { section: "image_conf", field: "record_image_description" },
  cfgAlwaysSelf: { section: "image_conf", field: "image_always_include_self" },
  cfgNeverSelf: { section: "image_conf", field: "image_never_include_self" },
  cfgImageTypes: { section: "image_conf", field: "image_enabled_types" },
  cfgVideoTypes: { section: "image_conf", field: "video_enabled_types" },
  cfgAppearancePrompt: { section: "image_conf", field: "appearance_prompt" },
  cfgTtsEnabled: { section: "tts_conf", field: "enable_tts" },
  cfgAudioOnly: { section: "tts_conf", field: "prefer_audio_only" },
  cfgTtsTypes: { section: "tts_conf", field: "tts_enabled_types" },
  cfgWeixinCompress: { section: "image_conf", field: "weixin_compress_images" },
  cfgWeixinMaxSide: { section: "image_conf", field: "weixin_image_max_side" },
  cfgWeixinMaxSize: { section: "image_conf", field: "weixin_image_max_size_kb" },
  cfgWeixinTimeout: { section: "image_conf", field: "weixin_api_timeout_seconds" },
  cfgWeixinCleanupMax: { section: "image_conf", field: "weixin_temp_cleanup_max_count" },
  cfgNewsApiEnabled: { section: "news_conf", field: "enable_news_api" },
  cfgNewsApiKey: { section: "news_conf", field: "nycnm_api_key" },
  cfgNewsMode: { section: "news_conf", field: "news_random_mode" },
  cfgNewsFixedSource: { section: "news_conf", field: "news_api_source" },
  cfgNewsItemsCount: { section: "news_conf", field: "news_items_count" },
  cfgNewsShareCount: { section: "news_conf", field: "news_share_count" },
  cfgNewsApiTimeout: { section: "news_conf", field: "news_api_timeout" },
  cfgNewsWebSearch: { section: "news_conf", field: "enable_tavily_search" },
  cfgNewsRandomSources: { section: "news_conf", field: "news_random_sources" },
  cfgLlmProviderId: { section: "llm_conf", field: "llm_provider_id" },
  cfgLlmTimeout: { section: "llm_conf", field: "llm_timeout" },
  cfgUsePersona: { section: "llm_conf", field: "use_persona" },
  cfgPersonaId: { section: "llm_conf", field: "persona_id" },
};

export const settingsPayloadGroups = {
  target: ["cfgContactAliases", "cfgTargetGroups", "cfgTargetUsers", "cfgBriefingGroups", "cfgBriefingUsers"],
  basic: [
    "cfgBasicTriggerMode",
    "cfgBasicFixedTimes",
    "cfgBasicShareCron",
    "cfgBasicRandomPeriods",
    "cfgBasicSmartMaxCount",
    "cfgBasicSmartQuietHours",
    "cfgBasicSmartPrompt",
    "cfgBasicCronDelay",
    "cfgBasicShareType",
    "cfgBasicRetentionDays",
    "cfgBasicDynamicDays",
  ],
  sequence: [
    "cfgDawnSequence",
    "cfgMorningSequence",
    "cfgForenoonSequence",
    "cfgNoonSequence",
    "cfgAfternoonSequence",
    "cfgEveningSequence",
    "cfgNightSequence",
    "cfgLateNightSequence",
  ],
  context: [
    "cfgReferenceHistoryCount",
    "cfgLifeContext",
    "cfgLifeContextGroup",
    "cfgGroupSchedule",
    "cfgChatHistory",
    "cfgDeepHistory",
    "cfgDeepHistoryHours",
    "cfgDeepHistoryMaxCount",
    "cfgPrivateHistoryCount",
    "cfgGroupIntensityCount",
    "cfgGroupShareStrategy",
    "cfgRecordMemory",
  ],
  briefing: [
    "cfgBriefing60s",
    "cfgBriefingAi",
    "cfgBriefingQzoneSync",
    "cfgBriefingScheduleMode",
    "cfgBriefingFixedTimes",
    "cfgBriefingRandomPeriods",
    "cfgBriefingCron",
    "cfgBriefingSmartMaxCount",
    "cfgBriefingSmartQuietHours",
    "cfgBriefingSmartPrompt",
    "cfgBriefingDelay",
  ],
  qzone: [
    "cfgQzoneEnabled",
    "cfgQzoneTimeout",
    "cfgQzoneTriggerMode",
    "cfgQzoneFixedTimes",
    "cfgQzoneCron",
    "cfgQzoneRandomPeriods",
    "cfgQzoneSmartMaxCount",
    "cfgQzoneSmartQuietHours",
    "cfgQzoneSmartPrompt",
    "cfgQzoneShareType",
    "cfgQzoneImage",
    "cfgQzoneHotImage",
    "cfgQzoneImageTypes",
    "cfgQzoneVideo",
    "cfgQzoneVideoTypes",
    "cfgQzoneAutoInteraction",
    "cfgQzoneAutoInteractionInterval",
    "cfgQzoneAutoInteractionCron",
    "cfgQzoneAutoLike",
    "cfgQzoneAutoLikeLimit",
    "cfgQzoneAutoComment",
    "cfgQzoneAutoCommentLimit",
    "cfgQzoneAutoCommentPrompt",
    "cfgQzoneAutoReply",
    "cfgQzoneAutoReplyLimit",
    "cfgQzoneAutoReplyPrompt",
  ],
  qzone_sequence: [
    "cfgQzoneDawnSequence",
    "cfgQzoneMorningSequence",
    "cfgQzoneForenoonSequence",
    "cfgQzoneNoonSequence",
    "cfgQzoneAfternoonSequence",
    "cfgQzoneEveningSequence",
    "cfgQzoneNightSequence",
    "cfgQzoneLateNightSequence",
  ],
  content: ["cfgKnowledgePrefix", "cfgRecPrefix", "cfgKnowledgeCats", "cfgRecCats"],
  media: [
    "cfgAiImage",
    "cfgHotImage",
    "cfgNewsImageCleanupMax",
    "cfgPriorityText",
    "cfgAiVideo",
    "cfgSeparateMedia",
    "cfgSeparateDelay",
    "cfgRecordImageDesc",
    "cfgAppearancePrompt",
    "cfgAlwaysSelf",
    "cfgNeverSelf",
    "cfgTtsEnabled",
    "cfgAudioOnly",
    "cfgImageTypes",
    "cfgVideoTypes",
    "cfgTtsTypes",
  ],
  weixin: [
    "cfgWeixinCompress",
    "cfgWeixinMaxSide",
    "cfgWeixinMaxSize",
    "cfgWeixinTimeout",
    "cfgWeixinCleanupMax",
  ],
  news: [
    "cfgNewsApiEnabled",
    "cfgNewsApiKey",
    "cfgNewsMode",
    "cfgNewsFixedSource",
    "cfgNewsItemsCount",
    "cfgNewsShareCount",
    "cfgNewsApiTimeout",
    "cfgNewsWebSearch",
    "cfgNewsRandomSources",
  ],
  llm: ["cfgLlmProviderId", "cfgLlmTimeout", "cfgUsePersona", "cfgPersonaId"],
};

export function settingsMappedSchemaFields() {
  const mapped = {
    root: new Set(),
    sections: new Map(),
  };
  for (const mapping of Object.values(settingsFieldSchema)) {
    if (mapping.root) {
      mapped.root.add(mapping.root);
    } else if (mapping.section && mapping.field) {
      if (!mapped.sections.has(mapping.section)) mapped.sections.set(mapping.section, new Set());
      mapped.sections.get(mapping.section).add(mapping.field);
    }
  }
  return mapped;
}

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

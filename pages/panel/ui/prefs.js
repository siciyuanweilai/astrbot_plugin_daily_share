import { text } from "./format.js?v=20260614-smart-schedule";

const CONFIG_AUTO_SAVE_FAST_DELAY_MS = 360;
const CONFIG_AUTO_SAVE_TEXT_DELAY_MS = 900;
const CONFIG_AUTO_SAVE_RETRY_DELAY_MS = 600;

export function createSettingsConfig({
  state,
  elements: el,
  bridge,
  apiGet,
  apiPost,
  setNotice,
  loadStatus,
  closeSweetSelects,
  syncSweetCombo,
  syncSweetSelect,
  syncSweetSelects,
  applySettingsSchemaEnhancements,
  normalizeSettingsSliders,
  syncSettingSlider,
} = {}) {
  function arrayToLines(value) {
    return Array.isArray(value) ? value.join("\n") : "";
  }

  function newsSourceDisplayLabel(value) {
    return text(value).trim().replace(/热搜$/, "");
  }

  function newsSourceArrayToLines(value, options = []) {
    if (!Array.isArray(value)) return "";
    const labels = new Map(
      options.map((source) => [
        text(source?.value).trim(),
        newsSourceDisplayLabel(source?.label),
      ]),
    );
    return value
      .map((item) => {
        const raw = text(item).trim();
        return labels.get(raw) || raw;
      })
      .filter(Boolean)
      .join("\n");
  }

  function shareTypeArrayToLines(value) {
    if (!Array.isArray(value)) return "";
    return value.map((item) => text(item).trim()).filter(Boolean).join("\n");
  }

  function linesToArray(value) {
    return text(value)
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function setInputValue(input, value) {
    if (!input) return;
    input.value = value ?? "";
    syncSettingSlider(input);
  }

  function setInputChecked(input, value) {
    if (!input) return;
    input.checked = Boolean(value);
  }

  function configSection(name) {
    return state.configData?.sections?.[name] || {};
  }

  function setConfigDirty(value) {
    state.configDirty = Boolean(value);
    if (el.saveConfigButton) {
      el.saveConfigButton.disabled = !state.configDirty || state.configSaving || !state.configData;
    }
  }

  function configAutoSaveDelay(event) {
    const target = event?.target;
    if (event?.type === "change") return CONFIG_AUTO_SAVE_FAST_DELAY_MS;
    if (target instanceof HTMLSelectElement) return CONFIG_AUTO_SAVE_FAST_DELAY_MS;
    if (!(target instanceof HTMLInputElement)) return CONFIG_AUTO_SAVE_TEXT_DELAY_MS;
    if (target.type === "range" || target.type === "checkbox" || target.type === "radio") {
      return CONFIG_AUTO_SAVE_FAST_DELAY_MS;
    }
    return CONFIG_AUTO_SAVE_TEXT_DELAY_MS;
  }

  function scheduleConfigAutoSave(eventOrDelay) {
    window.clearTimeout(state.configAutoSaveTimer);
    const delay = typeof eventOrDelay === "number" ? eventOrDelay : configAutoSaveDelay(eventOrDelay);
    const changeSeq = state.configChangeSeq;
    state.configAutoSaveTimer = window.setTimeout(() => {
      state.configAutoSaveTimer = 0;
      void commitConfigSave({ auto: true, changeSeq });
    }, delay);
  }

  function handleConfigChanged(event) {
    if (state.configApplying || isTargetEditorEvent(event)) return;
    handleScheduleChanged(event);
    handleAutoScheduleChanged(event);
    state.configChangeSeq += 1;
    setConfigDirty(true);
    scheduleConfigAutoSave(event);
  }

  function numberValue(input, fallback = 0) {
    const raw = text(input?.value).trim();
    return raw === "" ? fallback : Number(raw);
  }

  function intValue(value, fallback, min, max) {
    const parsed = Number.parseInt(text(value).trim(), 10);
    const number = Number.isFinite(parsed) ? parsed : fallback;
    return Math.min(max, Math.max(min, number));
  }

  function scheduleControls(kind) {
    const groups = {
      basic: {
        mode: el.cfgBasicTriggerMode,
        fixed: el.cfgBasicFixedTimes,
        random: el.cfgBasicRandomPeriods,
        cron: el.cfgBasicShareCron,
        delay: el.cfgBasicCronDelay,
        smart: [
          el.cfgBasicSmartMaxCount,
          el.cfgBasicSmartQuietHours,
          el.cfgBasicSmartPrompt,
        ],
        defaultMode: "llm_smart",
      },
      briefing: {
        mode: el.cfgBriefingScheduleMode,
        fixed: el.cfgBriefingFixedTimes,
        random: el.cfgBriefingRandomPeriods,
        cron: el.cfgBriefingCron,
        delay: el.cfgBriefingDelay,
        smart: [
          el.cfgBriefingSmartMaxCount,
          el.cfgBriefingSmartQuietHours,
          el.cfgBriefingSmartPrompt,
        ],
        defaultMode: "llm_smart",
      },
      qzone: {
        mode: el.cfgQzoneTriggerMode,
        fixed: el.cfgQzoneFixedTimes,
        random: el.cfgQzoneRandomPeriods,
        cron: el.cfgQzoneCron,
        smart: [
          el.cfgQzoneSmartMaxCount,
          el.cfgQzoneSmartQuietHours,
          el.cfgQzoneSmartPrompt,
        ],
        defaultMode: "llm_smart",
      },
    };
    return groups[kind] || null;
  }

  function syncScheduleVisibility(kind) {
    const controls = scheduleControls(kind);
    if (!controls) return;
    const mode = controls.mode?.value || controls.defaultMode;
    const visibleKey = {
      fixed_time: "fixed",
      random_period: "random",
      llm_smart: "smart",
      cron: "cron",
    }[mode] || "smart";
    for (const key of ["fixed", "random", "smart", "cron"]) {
      for (const node of el.configForm?.querySelectorAll(`[data-schedule="${kind}-${key}"]`) || []) {
        node.hidden = key !== visibleKey;
      }
    }
    const delayVisible = mode === "fixed_time" || mode === "cron";
    for (const node of el.configForm?.querySelectorAll(`[data-schedule="${kind}-delay"]`) || []) {
      node.hidden = !delayVisible;
    }
    syncSweetSelect(controls.mode);
  }

  function handleScheduleChanged(event) {
    const target = event?.target;
    for (const kind of ["basic", "briefing", "qzone"]) {
      const controls = scheduleControls(kind);
      const fields = Object.values(controls).flat();
      if (!controls || !fields.includes(target)) continue;
      syncScheduleVisibility(kind);
      return;
    }
  }

  function autoScheduleControls(kind) {
    return {
      interval: el.cfgQzoneAutoInteractionInterval,
      cron: el.cfgQzoneAutoInteractionCron,
      defaultInterval: 45,
      defaultCron: "0 */2 * * *",
    };
  }

  function setAutoSchedule(kind, cronValue, intervalValue) {
    const controls = autoScheduleControls(kind);
    setInputValue(controls.interval, intervalValue ?? controls.defaultInterval);
    setInputValue(controls.cron, text(cronValue).trim() || controls.defaultCron);
  }

  function autoSchedulePayload(kind) {
    const controls = autoScheduleControls(kind);
    return {
      interval: intValue(controls.interval?.value, controls.defaultInterval, 0, 1440),
      cron: text(controls.cron?.value).trim() || controls.defaultCron,
    };
  }

  function handleAutoScheduleChanged(event) {
    const target = event?.target;
    const controls = autoScheduleControls("interaction");
    if (target !== controls.interval && target !== controls.cron) return;
  }

  function populateDatalist(list, options = [], selected = "") {
    if (!list) return;
    const seen = new Set();
    const nodes = [];
    for (const option of options) {
      const value = text(option?.value).trim();
      if (!value || seen.has(value)) continue;
      seen.add(value);
      const node = document.createElement("option");
      node.value = value;
      node.label = text(option?.label).trim() || value;
      nodes.push(node);
    }
    const selectedValue = text(selected).trim();
    if (selectedValue && !seen.has(selectedValue)) {
      const node = document.createElement("option");
      node.value = selectedValue;
      node.label = selectedValue;
      nodes.push(node);
    }
    list.replaceChildren(...nodes);
    if (list === el.cfgLlmProviderOptions) syncSweetCombo(el.cfgLlmProviderId);
    if (list === el.cfgPersonaOptions) syncSweetCombo(el.cfgPersonaId);
  }

  function populateNewsSourceSelect(options = [], selected = "zhihu") {
    if (!el.cfgNewsFixedSource) return;
    const nextOptions = options.length
      ? options.map((source) => new Option(newsSourceDisplayLabel(source.label || source.value), source.value))
      : [new Option("知乎", "zhihu")];
    el.cfgNewsFixedSource.replaceChildren(...nextOptions);
    el.cfgNewsFixedSource.value = selected || nextOptions[0]?.value || "";
    syncSweetSelect(el.cfgNewsFixedSource);
  }

  function applyConfigData(data = {}) {
    state.configApplying = true;
    state.configData = data;
    const target = configSection("target");
    const basic = configSection("basic");
    const sequence = configSection("sequence");
    const context = configSection("context");
    const briefing = configSection("briefing");
    const qzone = configSection("qzone");
    const qzoneSequence = configSection("qzone_sequence");
    const content = configSection("content");
    const media = configSection("media");
    const weixin = configSection("weixin");
    const news = configSection("news");
    const llm = configSection("llm");

    setInputValue(el.cfgTargetGroups, arrayToLines(target.groups));
    setInputValue(el.cfgTargetUsers, arrayToLines(target.users));
    setInputValue(el.cfgBriefingGroups, arrayToLines(target.briefing_groups));
    setInputValue(el.cfgBriefingUsers, arrayToLines(target.briefing_users));
    setInputValue(el.cfgContactAliases, arrayToLines(target.contact_aliases));

    setInputChecked(el.cfgEnabled, data.enabled);
    setInputValue(el.cfgBasicTriggerMode, basic.trigger_mode || "llm_smart");
    setInputValue(el.cfgBasicFixedTimes, arrayToLines(basic.fixed_times));
    setInputValue(el.cfgBasicShareCron, basic.share_cron || "0 8,20 * * *");
    setInputValue(el.cfgBasicRandomPeriods, arrayToLines(basic.random_periods));
    setInputValue(el.cfgBasicSmartMaxCount, basic.smart_schedule_max_count ?? 2);
    setInputValue(el.cfgBasicSmartQuietHours, arrayToLines(basic.smart_schedule_quiet_hours));
    setInputValue(el.cfgBasicSmartPrompt, basic.smart_schedule_prompt || "");
    syncScheduleVisibility("basic");
    setInputValue(el.cfgBasicCronDelay, basic.cron_random_delay ?? 0);
    setInputValue(el.cfgBasicShareType, basic.share_type || "自动");
    setInputValue(el.cfgBasicRetentionDays, basic.data_retention_days ?? 60);
    setInputValue(el.cfgBasicDynamicDays, basic.dashboard_dynamic_days ?? 60);

    setInputValue(el.cfgDawnSequence, shareTypeArrayToLines(sequence.dawn_sequence));
    setInputValue(el.cfgMorningSequence, shareTypeArrayToLines(sequence.morning_sequence));
    setInputValue(el.cfgForenoonSequence, shareTypeArrayToLines(sequence.forenoon_sequence));
    setInputValue(el.cfgNoonSequence, shareTypeArrayToLines(sequence.noon_sequence));
    setInputValue(el.cfgAfternoonSequence, shareTypeArrayToLines(sequence.afternoon_sequence));
    setInputValue(el.cfgEveningSequence, shareTypeArrayToLines(sequence.evening_sequence));
    setInputValue(el.cfgNightSequence, shareTypeArrayToLines(sequence.night_sequence));
    setInputValue(el.cfgLateNightSequence, shareTypeArrayToLines(sequence.late_night_sequence));

    setInputValue(el.cfgReferenceHistoryCount, context.reference_history_count ?? 3);
    setInputChecked(el.cfgLifeContext, context.enable_life_context);
    setInputChecked(el.cfgLifeContextGroup, context.life_context_in_group);
    setInputChecked(el.cfgGroupSchedule, context.group_share_schedule);
    setInputChecked(el.cfgChatHistory, context.enable_chat_history);
    setInputChecked(el.cfgDeepHistory, context.enable_deep_history);
    setInputValue(el.cfgDeepHistoryHours, context.deep_history_hours ?? 24);
    setInputValue(el.cfgDeepHistoryMaxCount, context.deep_history_max_count ?? 50);
    setInputValue(el.cfgPrivateHistoryCount, context.private_history_count ?? 20);
    setInputValue(el.cfgGroupIntensityCount, context.group_intensity_check_count ?? 30);
    setInputValue(el.cfgGroupShareStrategy, context.group_share_strategy || "cautious");
    setInputChecked(el.cfgRecordMemory, context.record_share_to_memory);

    setInputChecked(el.cfgBriefing60s, briefing.enable_60s_news);
    setInputChecked(el.cfgBriefingAi, briefing.enable_ai_news);
    setInputChecked(el.cfgBriefingQzoneSync, briefing.sync_briefing_to_qzone);
    setInputValue(el.cfgBriefingScheduleMode, briefing.briefing_schedule_mode || "llm_smart");
    setInputValue(el.cfgBriefingFixedTimes, arrayToLines(briefing.briefing_fixed_times));
    setInputValue(el.cfgBriefingRandomPeriods, arrayToLines(briefing.briefing_random_periods));
    setInputValue(el.cfgBriefingCron, briefing.cron_briefing || "0 8 * * *");
    setInputValue(el.cfgBriefingSmartMaxCount, briefing.briefing_smart_schedule_max_count ?? 1);
    setInputValue(el.cfgBriefingSmartQuietHours, arrayToLines(briefing.briefing_smart_schedule_quiet_hours));
    setInputValue(el.cfgBriefingSmartPrompt, briefing.briefing_smart_schedule_prompt || "");
    setInputValue(el.cfgBriefingDelay, briefing.briefing_cron_random_delay ?? 0);
    syncScheduleVisibility("briefing");

    setInputChecked(el.cfgQzoneEnabled, qzone.enable_qzone);
    setInputValue(el.cfgQzoneTimeout, qzone.qzone_api_timeout_seconds ?? 120);
    setInputValue(el.cfgQzoneTriggerMode, qzone.qzone_trigger_mode || "llm_smart");
    setInputValue(el.cfgQzoneFixedTimes, arrayToLines(qzone.qzone_fixed_times));
    setInputValue(el.cfgQzoneCron, qzone.qzone_cron || "0 20 * * *");
    setInputValue(el.cfgQzoneRandomPeriods, arrayToLines(qzone.qzone_random_periods));
    setInputValue(el.cfgQzoneSmartMaxCount, qzone.qzone_smart_schedule_max_count ?? 1);
    setInputValue(el.cfgQzoneSmartQuietHours, arrayToLines(qzone.qzone_smart_schedule_quiet_hours));
    setInputValue(el.cfgQzoneSmartPrompt, qzone.qzone_smart_schedule_prompt || "");
    syncScheduleVisibility("qzone");
    setInputValue(el.cfgQzoneShareType, qzone.qzone_share_type || "自动");
    setInputChecked(el.cfgQzoneImage, qzone.qzone_enable_image);
    setInputChecked(el.cfgQzoneHotImage, qzone.qzone_attach_hot_news_image);
    setInputValue(el.cfgQzoneImageTypes, shareTypeArrayToLines(qzone.qzone_image_enabled_types));
    setInputChecked(el.cfgQzoneVideo, qzone.qzone_enable_video);
    setInputValue(el.cfgQzoneVideoTypes, shareTypeArrayToLines(qzone.qzone_video_enabled_types));
    setInputChecked(
      el.cfgQzoneAutoInteraction,
      qzone.qzone_enable_auto_interaction
        ?? (qzone.qzone_enable_auto_like || qzone.qzone_enable_auto_comment || qzone.qzone_enable_auto_reply),
    );
    setAutoSchedule(
      "interaction",
      qzone.qzone_auto_interaction_cron || "0 */2 * * *",
      qzone.qzone_auto_interaction_interval_minutes ?? 45,
    );
    setInputChecked(el.cfgQzoneAutoLike, qzone.qzone_enable_auto_like);
    setInputValue(el.cfgQzoneAutoLikeLimit, qzone.qzone_auto_like_limit ?? 3);
    setInputChecked(el.cfgQzoneAutoComment, qzone.qzone_enable_auto_comment);
    setInputValue(el.cfgQzoneAutoCommentLimit, qzone.qzone_auto_comment_limit ?? 3);
    setInputValue(el.cfgQzoneAutoCommentPrompt, qzone.qzone_auto_comment_prompt || "");
    setInputChecked(el.cfgQzoneAutoReply, qzone.qzone_enable_auto_reply);
    setInputValue(el.cfgQzoneAutoReplyLimit, qzone.qzone_auto_reply_limit ?? 3);
    setInputValue(el.cfgQzoneAutoReplyPrompt, qzone.qzone_auto_reply_prompt || "");

    setInputValue(el.cfgQzoneDawnSequence, shareTypeArrayToLines(qzoneSequence.qzone_dawn_sequence));
    setInputValue(el.cfgQzoneMorningSequence, shareTypeArrayToLines(qzoneSequence.qzone_morning_sequence));
    setInputValue(el.cfgQzoneForenoonSequence, shareTypeArrayToLines(qzoneSequence.qzone_forenoon_sequence));
    setInputValue(el.cfgQzoneNoonSequence, shareTypeArrayToLines(qzoneSequence.qzone_noon_sequence));
    setInputValue(el.cfgQzoneAfternoonSequence, shareTypeArrayToLines(qzoneSequence.qzone_afternoon_sequence));
    setInputValue(el.cfgQzoneEveningSequence, shareTypeArrayToLines(qzoneSequence.qzone_evening_sequence));
    setInputValue(el.cfgQzoneNightSequence, shareTypeArrayToLines(qzoneSequence.qzone_night_sequence));
    setInputValue(el.cfgQzoneLateNightSequence, shareTypeArrayToLines(qzoneSequence.qzone_late_night_sequence));

    setInputChecked(el.cfgKnowledgePrefix, content.show_knowledge_type_prefix);
    setInputChecked(el.cfgRecPrefix, content.show_rec_type_prefix);
    setInputValue(el.cfgKnowledgeCats, arrayToLines(content.knowledge_cats));
    setInputValue(el.cfgRecCats, arrayToLines(content.rec_cats));

    setInputChecked(el.cfgAiImage, media.enable_ai_image);
    setInputChecked(el.cfgHotImage, media.attach_hot_news_image);
    setInputValue(el.cfgNewsImageCleanupMax, media.news_image_cleanup_max_count ?? 200);
    setInputChecked(el.cfgPriorityText, media.priority_text_over_schedule);
    setInputChecked(el.cfgAiVideo, media.enable_ai_video);
    setInputChecked(el.cfgSeparateMedia, media.separate_text_and_image);
    setInputValue(el.cfgSeparateDelay, media.separate_send_delay || "1.0-2.0");
    setInputChecked(el.cfgRecordImageDesc, media.record_image_description);
    setInputChecked(el.cfgAlwaysSelf, media.image_always_include_self);
    setInputChecked(el.cfgNeverSelf, media.image_never_include_self);
    setInputChecked(el.cfgTtsEnabled, media.enable_tts);
    setInputChecked(el.cfgAudioOnly, media.prefer_audio_only);
    setInputValue(el.cfgImageTypes, shareTypeArrayToLines(media.image_enabled_types));
    setInputValue(el.cfgVideoTypes, shareTypeArrayToLines(media.video_enabled_types));
    setInputValue(el.cfgTtsTypes, shareTypeArrayToLines(media.tts_enabled_types));
    setInputValue(el.cfgAppearancePrompt, media.appearance_prompt || "");

    setInputChecked(el.cfgWeixinCompress, weixin.weixin_compress_images);
    setInputValue(el.cfgWeixinMaxSide, weixin.weixin_image_max_side ?? 4096);
    setInputValue(el.cfgWeixinMaxSize, weixin.weixin_image_max_size_kb ?? 10240);
    setInputValue(el.cfgWeixinTimeout, weixin.weixin_api_timeout_seconds ?? 60);
    setInputValue(el.cfgWeixinCleanupMax, weixin.weixin_temp_cleanup_max_count ?? 10);

    setInputChecked(el.cfgNewsApiEnabled, news.enable_news_api);
    setInputValue(el.cfgNewsApiKey, news.nycnm_api_key || "");
    setInputValue(el.cfgNewsMode, news.news_random_mode || "config");
    populateNewsSourceSelect(data.options?.news_sources || [], news.news_api_source || "zhihu");
    setInputValue(el.cfgNewsItemsCount, news.news_items_count ?? 5);
    setInputValue(el.cfgNewsShareCount, news.news_share_count || "1-2");
    setInputValue(el.cfgNewsApiTimeout, news.news_api_timeout ?? 30);
    setInputChecked(el.cfgNewsWebSearch, news.enable_tavily_search);
    setInputValue(el.cfgNewsRandomSources, newsSourceArrayToLines(news.news_random_sources, data.options?.news_sources || []));

    populateDatalist(el.cfgLlmProviderOptions, data.options?.providers || [], llm.llm_provider_id);
    populateDatalist(el.cfgPersonaOptions, data.options?.personas || [], llm.persona_id);
    setInputValue(el.cfgLlmProviderId, llm.llm_provider_id || "");
    setInputValue(el.cfgLlmTimeout, llm.llm_timeout ?? 120);
    setInputChecked(el.cfgUsePersona, llm.use_persona);
    setInputValue(el.cfgPersonaId, llm.persona_id || "");

    applySettingsSchemaEnhancements(data);
    state.configApplying = false;
    setConfigDirty(false);
    syncSweetSelects();
  }

  function collectConfigPayload() {
    normalizeSettingsSliders();
    const autoInteractionSchedule = autoSchedulePayload("interaction");
    const targetPayload = {
      contact_aliases: linesToArray(el.cfgContactAliases?.value),
    };
    if (el.cfgTargetGroups) targetPayload.groups = linesToArray(el.cfgTargetGroups.value);
    if (el.cfgTargetUsers) targetPayload.users = linesToArray(el.cfgTargetUsers.value);
    if (el.cfgBriefingGroups) targetPayload.briefing_groups = linesToArray(el.cfgBriefingGroups.value);
    if (el.cfgBriefingUsers) targetPayload.briefing_users = linesToArray(el.cfgBriefingUsers.value);

    return {
      enabled: Boolean(el.cfgEnabled?.checked),
      sections: {
        target: targetPayload,
        basic: {
          trigger_mode: el.cfgBasicTriggerMode?.value || "llm_smart",
          fixed_times: linesToArray(el.cfgBasicFixedTimes?.value),
          share_cron: text(el.cfgBasicShareCron?.value).trim(),
          random_periods: linesToArray(el.cfgBasicRandomPeriods?.value),
          smart_schedule_max_count: intValue(el.cfgBasicSmartMaxCount?.value, 2, 1, 6),
          smart_schedule_quiet_hours: linesToArray(el.cfgBasicSmartQuietHours?.value),
          smart_schedule_prompt: text(el.cfgBasicSmartPrompt?.value).trim(),
          cron_random_delay: numberValue(el.cfgBasicCronDelay, 0),
          share_type: el.cfgBasicShareType?.value || "自动",
          data_retention_days: numberValue(el.cfgBasicRetentionDays, 60),
          dashboard_dynamic_days: numberValue(el.cfgBasicDynamicDays, 60),
        },
        sequence: {
          dawn_sequence: linesToArray(el.cfgDawnSequence?.value),
          morning_sequence: linesToArray(el.cfgMorningSequence?.value),
          forenoon_sequence: linesToArray(el.cfgForenoonSequence?.value),
          noon_sequence: linesToArray(el.cfgNoonSequence?.value),
          afternoon_sequence: linesToArray(el.cfgAfternoonSequence?.value),
          evening_sequence: linesToArray(el.cfgEveningSequence?.value),
          night_sequence: linesToArray(el.cfgNightSequence?.value),
          late_night_sequence: linesToArray(el.cfgLateNightSequence?.value),
        },
        context: {
          reference_history_count: numberValue(el.cfgReferenceHistoryCount, 3),
          enable_life_context: Boolean(el.cfgLifeContext?.checked),
          life_context_in_group: Boolean(el.cfgLifeContextGroup?.checked),
          group_share_schedule: Boolean(el.cfgGroupSchedule?.checked),
          enable_chat_history: Boolean(el.cfgChatHistory?.checked),
          enable_deep_history: Boolean(el.cfgDeepHistory?.checked),
          deep_history_hours: numberValue(el.cfgDeepHistoryHours, 24),
          deep_history_max_count: numberValue(el.cfgDeepHistoryMaxCount, 50),
          private_history_count: numberValue(el.cfgPrivateHistoryCount, 20),
          group_intensity_check_count: numberValue(el.cfgGroupIntensityCount, 30),
          group_share_strategy: el.cfgGroupShareStrategy?.value || "cautious",
          record_share_to_memory: Boolean(el.cfgRecordMemory?.checked),
        },
        briefing: {
          enable_60s_news: Boolean(el.cfgBriefing60s?.checked),
          enable_ai_news: Boolean(el.cfgBriefingAi?.checked),
          sync_briefing_to_qzone: Boolean(el.cfgBriefingQzoneSync?.checked),
          briefing_schedule_mode: el.cfgBriefingScheduleMode?.value || "llm_smart",
          briefing_fixed_times: linesToArray(el.cfgBriefingFixedTimes?.value),
          briefing_random_periods: linesToArray(el.cfgBriefingRandomPeriods?.value),
          cron_briefing: text(el.cfgBriefingCron?.value).trim(),
          briefing_smart_schedule_max_count: intValue(el.cfgBriefingSmartMaxCount?.value, 1, 1, 6),
          briefing_smart_schedule_quiet_hours: linesToArray(el.cfgBriefingSmartQuietHours?.value),
          briefing_smart_schedule_prompt: text(el.cfgBriefingSmartPrompt?.value).trim(),
          briefing_cron_random_delay: numberValue(el.cfgBriefingDelay, 0),
        },
        qzone: {
          enable_qzone: Boolean(el.cfgQzoneEnabled?.checked),
          qzone_api_timeout_seconds: numberValue(el.cfgQzoneTimeout, 120),
          qzone_trigger_mode: el.cfgQzoneTriggerMode?.value || "llm_smart",
          qzone_fixed_times: linesToArray(el.cfgQzoneFixedTimes?.value),
          qzone_cron: text(el.cfgQzoneCron?.value).trim(),
          qzone_random_periods: linesToArray(el.cfgQzoneRandomPeriods?.value),
          qzone_smart_schedule_max_count: intValue(el.cfgQzoneSmartMaxCount?.value, 1, 1, 6),
          qzone_smart_schedule_quiet_hours: linesToArray(el.cfgQzoneSmartQuietHours?.value),
          qzone_smart_schedule_prompt: text(el.cfgQzoneSmartPrompt?.value).trim(),
          qzone_share_type: el.cfgQzoneShareType?.value || "自动",
          qzone_enable_image: Boolean(el.cfgQzoneImage?.checked),
          qzone_attach_hot_news_image: Boolean(el.cfgQzoneHotImage?.checked),
          qzone_image_enabled_types: linesToArray(el.cfgQzoneImageTypes?.value),
          qzone_enable_video: Boolean(el.cfgQzoneVideo?.checked),
          qzone_video_enabled_types: linesToArray(el.cfgQzoneVideoTypes?.value),
          qzone_enable_auto_interaction: Boolean(el.cfgQzoneAutoInteraction?.checked),
          qzone_auto_interaction_interval_minutes: autoInteractionSchedule.interval,
          qzone_auto_interaction_cron: autoInteractionSchedule.cron,
          qzone_enable_auto_like: Boolean(el.cfgQzoneAutoLike?.checked),
          qzone_auto_like_limit: numberValue(el.cfgQzoneAutoLikeLimit, 3),
          qzone_enable_auto_comment: Boolean(el.cfgQzoneAutoComment?.checked),
          qzone_auto_comment_limit: numberValue(el.cfgQzoneAutoCommentLimit, 3),
          qzone_auto_comment_prompt: text(el.cfgQzoneAutoCommentPrompt?.value).trim(),
          qzone_enable_auto_reply: Boolean(el.cfgQzoneAutoReply?.checked),
          qzone_auto_reply_limit: numberValue(el.cfgQzoneAutoReplyLimit, 3),
          qzone_auto_reply_prompt: text(el.cfgQzoneAutoReplyPrompt?.value).trim(),
        },
        qzone_sequence: {
          qzone_dawn_sequence: linesToArray(el.cfgQzoneDawnSequence?.value),
          qzone_morning_sequence: linesToArray(el.cfgQzoneMorningSequence?.value),
          qzone_forenoon_sequence: linesToArray(el.cfgQzoneForenoonSequence?.value),
          qzone_noon_sequence: linesToArray(el.cfgQzoneNoonSequence?.value),
          qzone_afternoon_sequence: linesToArray(el.cfgQzoneAfternoonSequence?.value),
          qzone_evening_sequence: linesToArray(el.cfgQzoneEveningSequence?.value),
          qzone_night_sequence: linesToArray(el.cfgQzoneNightSequence?.value),
          qzone_late_night_sequence: linesToArray(el.cfgQzoneLateNightSequence?.value),
        },
        content: {
          show_knowledge_type_prefix: Boolean(el.cfgKnowledgePrefix?.checked),
          show_rec_type_prefix: Boolean(el.cfgRecPrefix?.checked),
          knowledge_cats: linesToArray(el.cfgKnowledgeCats?.value),
          rec_cats: linesToArray(el.cfgRecCats?.value),
        },
        media: {
          enable_ai_image: Boolean(el.cfgAiImage?.checked),
          attach_hot_news_image: Boolean(el.cfgHotImage?.checked),
          news_image_cleanup_max_count: numberValue(el.cfgNewsImageCleanupMax, 200),
          priority_text_over_schedule: Boolean(el.cfgPriorityText?.checked),
          enable_ai_video: Boolean(el.cfgAiVideo?.checked),
          separate_text_and_image: Boolean(el.cfgSeparateMedia?.checked),
          separate_send_delay: text(el.cfgSeparateDelay?.value).trim() || "1.0-2.0",
          record_image_description: Boolean(el.cfgRecordImageDesc?.checked),
          appearance_prompt: text(el.cfgAppearancePrompt?.value).trim(),
          image_always_include_self: Boolean(el.cfgAlwaysSelf?.checked),
          image_never_include_self: Boolean(el.cfgNeverSelf?.checked),
          enable_tts: Boolean(el.cfgTtsEnabled?.checked),
          prefer_audio_only: Boolean(el.cfgAudioOnly?.checked),
          image_enabled_types: linesToArray(el.cfgImageTypes?.value),
          video_enabled_types: linesToArray(el.cfgVideoTypes?.value),
          tts_enabled_types: linesToArray(el.cfgTtsTypes?.value),
        },
        weixin: {
          weixin_compress_images: Boolean(el.cfgWeixinCompress?.checked),
          weixin_image_max_side: numberValue(el.cfgWeixinMaxSide, 4096),
          weixin_image_max_size_kb: numberValue(el.cfgWeixinMaxSize, 10240),
          weixin_api_timeout_seconds: numberValue(el.cfgWeixinTimeout, 60),
          weixin_temp_cleanup_max_count: numberValue(el.cfgWeixinCleanupMax, 10),
        },
        news: {
          enable_news_api: Boolean(el.cfgNewsApiEnabled?.checked),
          nycnm_api_key: text(el.cfgNewsApiKey?.value).trim(),
          news_random_mode: el.cfgNewsMode?.value || "config",
          news_api_source: el.cfgNewsFixedSource?.value || "zhihu",
          news_items_count: numberValue(el.cfgNewsItemsCount, 5),
          news_share_count: text(el.cfgNewsShareCount?.value).trim() || "1-2",
          news_api_timeout: numberValue(el.cfgNewsApiTimeout, 30),
          enable_tavily_search: Boolean(el.cfgNewsWebSearch?.checked),
          news_random_sources: linesToArray(el.cfgNewsRandomSources?.value),
        },
        llm: {
          llm_provider_id: text(el.cfgLlmProviderId?.value).trim(),
          llm_timeout: numberValue(el.cfgLlmTimeout, 120),
          use_persona: Boolean(el.cfgUsePersona?.checked),
          persona_id: text(el.cfgPersonaId?.value).trim(),
        },
      },
    };
  }

  function setSettingsTab(tab, { scroll = true, sync = true } = {}) {
    state.settingsTab = tab || "target";
    for (const section of el.settingsSections) {
      section.classList.toggle("active", section.dataset.settingsSection === state.settingsTab);
    }
    if (sync) {
      closeSweetSelects();
      syncSweetSelects();
    }
    if (!scroll) return;
    const section = el.settingsSections.find((item) => item.dataset.settingsSection === state.settingsTab);
    if (section) {
      state.settingsScrollLockUntil = Date.now() + 720;
      const top = Math.max(0, section.getBoundingClientRect().top + window.scrollY - 16);
      window.scrollTo({ top, behavior: "smooth" });
    }
  }

  function settingsVisiblePixels(section, viewportTop, viewportBottom) {
    const rect = section.getBoundingClientRect();
    return Math.max(0, Math.min(rect.bottom, viewportBottom) - Math.max(rect.top, viewportTop));
  }

  function resolveSettingsTabFromViewport() {
    if (state.activeView !== "settings" || !el.settingsSections.length) return;
    if (Date.now() < state.settingsScrollLockUntil) return;
    const viewportTop = Math.min(180, Math.max(96, window.innerHeight * 0.14));
    const viewportBottom = window.innerHeight - 24;
    let active = state.settingsTab || el.settingsSections[0].dataset.settingsSection || "target";
    let activeVisible = 0;
    let best = active;
    let bestVisible = 0;

    for (const section of el.settingsSections) {
      const tab = section.dataset.settingsSection || "";
      const visible = settingsVisiblePixels(section, viewportTop, viewportBottom);
      if (tab === active) activeVisible = visible;
      if (visible > bestVisible) {
        best = tab || best;
        bestVisible = visible;
      }
    }

    if (best && best !== state.settingsTab && (activeVisible < 64 || bestVisible - activeVisible > 96)) {
      setSettingsTab(best, { scroll: false, sync: false });
    }
  }

  function updateSettingsTabFromScroll() {
    if (state.settingsScrollFrame) return;
    state.settingsScrollFrame = window.requestAnimationFrame(() => {
      state.settingsScrollFrame = 0;
      resolveSettingsTabFromViewport();
    });
  }

  async function loadConfig({ quiet = false } = {}) {
    if (!bridge) return;
    try {
      const data = await apiGet("page/config");
      applyConfigData(data);
      if (!quiet) setNotice("");
    } catch (error) {
      setNotice(error.message || "设置加载失败", "error");
    }
  }

  async function commitConfigSave({ auto = false, changeSeq = state.configChangeSeq } = {}) {
    if (!state.configDirty) return;
    if (state.configSaving) {
      state.configSaveQueued = true;
      return;
    }

    window.clearTimeout(state.configAutoSaveTimer);
    state.configAutoSaveTimer = 0;
    state.configSaving = true;
    state.configSaveQueued = false;
    setConfigDirty(true);
    if (el.reloadConfigButton) el.reloadConfigButton.disabled = true;

    let shouldQueueNextSave = false;
    try {
      const data = await apiPost("page/config", collectConfigPayload());
      shouldQueueNextSave = state.configSaveQueued || state.configChangeSeq !== changeSeq;
      if (shouldQueueNextSave) {
        state.configData = data;
        setConfigDirty(true);
      } else if (auto) {
        state.configData = data;
        setConfigDirty(false);
      } else {
        applyConfigData(data);
      }
      await loadStatus({ quiet: true });
      if (!auto) setNotice("设置已保存。", "success");
    } catch (error) {
      shouldQueueNextSave = false;
      setConfigDirty(true);
      setNotice(error.message || "设置保存失败", "error");
    } finally {
      state.configSaving = false;
      if (shouldQueueNextSave || state.configSaveQueued) {
        state.configSaveQueued = false;
        setConfigDirty(true);
        scheduleConfigAutoSave(CONFIG_AUTO_SAVE_RETRY_DELAY_MS);
      }
      if (el.reloadConfigButton) el.reloadConfigButton.disabled = false;
      setConfigDirty(state.configDirty);
    }
  }

  async function saveConfig(event) {
    event?.preventDefault();
    if (event && !event.submitter && isTargetEditorElement(document.activeElement)) return;
    await commitConfigSave({ auto: false, changeSeq: state.configChangeSeq });
  }

  function isTargetEditorElement(node) {
    return Boolean(node?.closest?.(".settings-target-editor"));
  }

  function isTargetEditorEvent(event) {
    return isTargetEditorElement(event?.target);
  }

  return {
    handleConfigChanged,
    loadConfig,
    saveConfig,
    setSettingsTab,
    updateSettingsTabFromScroll,
  };
}

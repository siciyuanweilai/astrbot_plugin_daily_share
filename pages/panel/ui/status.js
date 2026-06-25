import {
  BUILTIN_TARGET_IDS,
  enabledShortLabel,
  formatNextShareTime,
  formatRelativeActionTime,
  replaceChildren,
  targetLabel,
  text,
  triggerSummary,
  typeLabel,
} from "./format.js?v=20260614-smart-schedule";

const RECENT_ACTION_DISPLAY_LIMIT = 1;
const actionStatusLabels = {
  running: "进行中",
  done: "成功",
  success: "成功",
  ok: "成功",
  error: "失败",
  failed: "失败",
  failure: "失败",
};

const actionTargetLabels = {
  broadcast: "群聊 / 私聊",
  broadcast_groups: "仅群聊",
  broadcast_users: "仅私聊",
  qzone: "QQ 空间",
  briefing: "早报",
  retry: "重试",
};

const actionSourceLabels = {
  manual: "手动",
  scheduled: "定时",
  smart_schedule: "智能定时",
  command: "自然语言",
};

const periodLabels = {
  dawn: "凌晨",
  morning: "早晨",
  forenoon: "上午",
  noon: "中午",
  afternoon: "下午",
  evening: "傍晚",
  night: "晚上",
  late_night: "深夜",
};

export function createStatusView({
  state,
  elements: el,
  syncSweetSelect,
} = {}) {
  function fillNewsSources() {
    const selected = el.newsSource.value;
    const options = [new Option("自动", "")];
    for (const source of state.status?.news_sources || []) {
      options.push(new Option(source.name || source.key, source.key));
    }
    el.newsSource.replaceChildren(...options);
    el.newsSource.value = selected;
    syncSweetSelect(el.newsSource);
  }

  function renderMetrics() {
    const status = state.status || {};
    el.runButton.disabled = Boolean(status.busy);
  }

  function actionStatusTone(status) {
    const normalized = text(status).trim().toLowerCase();
    if (normalized === "running") return "running";
    if (["done", "success", "ok"].includes(normalized)) return "success";
    if (["error", "failed", "failure"].includes(normalized)) return "error";
    return "neutral";
  }

  function actionTargetLabel(action = {}) {
    const target = text(action.target).trim();
    const targetId = text(action.target_id).trim();
    if (target === "retry") {
      const source = targetLabel(targetId, action.target_label, action.kind);
      return source && source !== "全局" ? `重试 · ${source}` : "重试";
    }
    if (targetId && !BUILTIN_TARGET_IDS.has(targetId)) {
      return targetLabel(targetId, action.target_label, action.kind);
    }
    return actionTargetLabels[target] || targetLabel(targetId || target, action.target_label, action.kind);
  }

  function actionSourceLabel(action = {}) {
    const raw = text(action.source_type).trim().toLowerCase();
    return text(action.source_label).trim() || actionSourceLabels[raw] || "";
  }

  function actionMetaText(action = {}) {
    const detailPieces = [];
    const time = formatRelativeActionTime(action.finished_at || action.started_at);
    const target = actionTargetLabel(action);
    const shareType = typeLabel(action.share_type);
    const newsSource = text(action.news_source).trim();
    if (target && target !== "全局") detailPieces.push(target);
    if (shareType && shareType !== "--") detailPieces.push(shareType);
    if (newsSource) detailPieces.push(newsSource);
    const detail = detailPieces.join(" · ");
    if (time !== "--" && detail) return `${time} ${detail}`;
    return time !== "--" ? time : detail || "等待更新";
  }

  function recentActionNode(action = {}) {
    const status = text(action.status).trim().toLowerCase();
    const tone = actionStatusTone(status);
    const node = document.createElement("article");
    node.className = `recent-action is-${tone}`;
    const badge = document.createElement("span");
    badge.className = "recent-action-status";
    badge.textContent = actionStatusLabels[status] || "记录";
    const body = document.createElement("div");
    body.className = "recent-action-body";
    const title = document.createElement("strong");
    const message = text(action.message).trim() || `${actionTargetLabel(action)}${badge.textContent}`;
    const source = actionSourceLabel(action);
    title.textContent = source ? `${source} · ${message}` : message;
    const meta = document.createElement("span");
    meta.textContent = actionMetaText(action);
    body.append(title, meta);
    node.append(badge, body);
    return node;
  }

  function progressActionItem() {
    const progress = state.status?.progress || {};
    if (actionStatusTone(progress.status) !== "running") return null;
    const message = text(progress.message).trim() ||
      text(progress.stage_label).trim() ||
      "分享进行中";
    return {
      id: text(progress.id).trim() || "share-progress-running",
      source: "progress",
      target: "",
      target_id: progress.target_id || "",
      target_label: progress.target_label || "",
      kind: progress.kind || "",
      share_type: progress.share_type || "auto",
      news_source: progress.news_source || "",
      status: "running",
      message,
      started_at: progress.started_at || progress.updated_at || "",
      finished_at: "",
      source_type: progress.source_type || "",
      source_label: progress.source_label || actionSourceLabels[text(progress.source_type).trim().toLowerCase()] || "",
    };
  }

  function recentShareItems() {
    const runningProgress = progressActionItem();
    const progressId = text(runningProgress?.id).trim();
    const runningActions = [...(state.status?.actions || [])].filter(
      (item) => actionStatusTone(item.status) === "running" && text(item.id).trim() !== progressId,
    );
    const historyShares = Array.isArray(state.status?.recent_shares)
      ? state.status.recent_shares
      : [];
    return [
      ...(runningProgress ? [runningProgress] : []),
      ...runningActions,
      ...historyShares,
    ].sort((a, b) => {
      const runningDiff = Number(actionStatusTone(b.status) === "running") -
        Number(actionStatusTone(a.status) === "running");
      if (runningDiff) return runningDiff;
      return text(b?.finished_at || b?.started_at).localeCompare(text(a?.finished_at || a?.started_at));
    });
  }

  function isSpecificRunTarget(target) {
    return target === "broadcast_groups" || target === "broadcast_users";
  }

  function renderRecentActions() {
    if (!el.recentActionsList) return;
    const actions = recentShareItems();
    const visibleActions = actions.slice(0, RECENT_ACTION_DISPLAY_LIMIT);
    if (!actions.length) {
      const empty = document.createElement("div");
      empty.className = "recent-action recent-action-empty";
      empty.textContent = "暂无今日分享";
      replaceChildren(el.recentActionsList, [empty]);
      return;
    }
    replaceChildren(
      el.recentActionsList,
      visibleActions.map(recentActionNode),
    );
  }

  function configRow(label, value, tone = "") {
    const row = document.createElement("div");
    row.className = `config-row ${tone}`.trim();
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    row.append(dt, dd);
    return row;
  }

  function nextScheduleItem() {
    const jobs = state.status?.scheduler?.jobs || [];
    return jobs
      .filter((job) => job.next_run_time)
      .sort((a, b) => String(a.next_run_time).localeCompare(String(b.next_run_time)))[0];
  }

  function mediaStatLabels(label) {
    return Array.isArray(label) ? label : [label];
  }

  function mediaStatItem({ key, label, value, tone = "", mediaKind = "" }) {
    const node = mediaKind ? document.createElement("button") : document.createElement("div");
    node.className = `media-stat-chip ${tone}`.trim();
    node.dataset.mediaStat = key;
    if (mediaKind) {
      node.type = "button";
      node.dataset.mediaKind = mediaKind;
      node.setAttribute("aria-pressed", "false");
    }
    for (const item of mediaStatLabels(label)) {
      const title = document.createElement("span");
      title.textContent = item;
      node.append(title);
    }
    if (value !== "") {
      const body = document.createElement("strong");
      body.textContent = value;
      node.append(body);
    }
    return node;
  }

  function mediaStatStructureMatches(node, spec) {
    const labels = [...node.querySelectorAll("span")].map((item) => item.textContent);
    const strong = node.querySelector("strong");
    return node.dataset.mediaStat === spec.key &&
      node.dataset.mediaKind === spec.mediaKind &&
      node.classList.contains("media-stat-chip") &&
      node.classList.contains(spec.tone) &&
      labels.join("\n") === mediaStatLabels(spec.label).join("\n") &&
      Boolean(strong) === (spec.value !== "");
  }

  function updateMediaStatValue(node, value) {
    const strong = node.querySelector("strong");
    if (strong && strong.textContent !== value) strong.textContent = value;
  }

  function settingsSummaryItem(label, enabled) {
    const node = document.createElement("span");
    node.className = `settings-summary-item ${enabled ? "is-on" : "is-off"}`;
    node.textContent = `${label} ${enabledShortLabel(enabled)}`;
    return node;
  }

  function renderNextShareLine(nextJob) {
    if (!el.nextShareLine) return;
    const label = document.createElement("span");
    label.className = "next-share-label";
    label.textContent = "下次分享";

    if (!nextJob) {
      const empty = document.createElement("strong");
      empty.className = "next-share-empty";
      empty.textContent = "暂无任务";
      replaceChildren(el.nextShareLine, [label, empty]);
      return;
    }

    const time = document.createElement("strong");
    time.className = "next-share-time";
    time.textContent = formatNextShareTime(nextJob.next_run_time);

    const title = document.createElement("span");
    title.className = "next-share-title";
    title.textContent = nextJob.display_name || nextJob.name || "任务";

    replaceChildren(el.nextShareLine, [label, time, title]);
  }

  function progressStepTone(status) {
    const normalized = text(status).trim().toLowerCase();
    if (["done", "success", "ok"].includes(normalized)) return "done";
    if (normalized === "running") return "running";
    if (["error", "failed", "failure"].includes(normalized)) return "error";
    if (normalized === "skipped") return "skipped";
    return "pending";
  }

  function renderShareProgress() {
    if (!el.shareProgressLine) return;

    const progress = state.status?.progress || {};
    const status = text(progress.status).trim().toLowerCase();
    const running = status === "running";
    const finished = ["done", "success", "ok", "error", "failed", "failure"].includes(status);
    const card = document.createElement("div");
    card.className = `share-progress is-${running ? "running" : finished ? progressStepTone(status) : "idle"}`;

    const label = document.createElement("span");
    label.className = "share-progress-label";
    label.textContent = "分享进度";

    const stage = document.createElement("strong");
    stage.className = "share-progress-stage";
    stage.textContent = running || finished ? (text(progress.stage_label) || text(progress.message) || "进行中") : "空闲";

    const title = document.createElement("span");
    title.className = "share-progress-title";
    const titleParts = [];
    if (text(progress.target_label)) titleParts.push(text(progress.target_label));
    if (text(progress.share_type_label)) titleParts.push(text(progress.share_type_label));
    const totalTargets = Number(progress.total_targets || 0);
    const currentTarget = Number(progress.current_index || 0);
    if (running && totalTargets > 1 && currentTarget > 0) {
      titleParts.push(`${currentTarget}/${totalTargets}`);
    }
    title.textContent = (running || finished) && titleParts.length ? titleParts.join(" · ") : "等待下一次分享";

    const head = document.createElement("div");
    head.className = "share-progress-head";
    head.append(label, stage, title);

    const steps = document.createElement("div");
    steps.className = "share-progress-steps";
    if (running || finished) {
      for (const step of progress.steps || []) {
        const item = document.createElement("span");
        item.className = `share-progress-step is-${progressStepTone(step.status)}`;
        item.textContent = text(step.label || step.key);
        steps.append(item);
      }
    }

    card.append(head);
    if (running || finished) {
      card.append(steps);
    }
    replaceChildren(el.shareProgressLine, [card]);
  }

  function renderMediaStats({ dynamicCount, textCount, imageCount, videoCount, todayCount }) {
    if (!el.mediaStats) return;
    const stats = [
      { key: "dynamic", label: "动态", value: `${dynamicCount}`, tone: "is-dynamic", mediaKind: "all" },
      { key: "today", label: "今日", value: `${todayCount}`, tone: "is-today", mediaKind: "today" },
      { key: "text", label: "文案", value: `${textCount}`, tone: "is-text", mediaKind: "text" },
      { key: "image", label: "图片", value: `${imageCount}`, tone: "is-image", mediaKind: "image" },
      { key: "video", label: "视频", value: `${videoCount}`, tone: "is-video", mediaKind: "video" },
      { key: "qzone", label: ["QQ", "空间"], value: "", tone: "is-qzone", mediaKind: "qzone" },
    ];
    const toolbar = el.mediaStats.querySelector(".media-bulk-toolbar");
    const current = [...el.mediaStats.children].filter((node) => !node.classList.contains("media-bulk-toolbar"));
    const canReuse = current.length === stats.length &&
      current.every((node, index) => mediaStatStructureMatches(node, stats[index]));
    if (!canReuse) {
      const statNodes = stats.map(mediaStatItem);
      replaceChildren(el.mediaStats, toolbar ? [...statNodes, toolbar] : statNodes);
      return;
    }
    stats.forEach((spec, index) => updateMediaStatValue(current[index], spec.value));
    if (toolbar && toolbar.parentElement === el.mediaStats) el.mediaStats.append(toolbar);
  }

  function renderConfig() {
    const status = state.status || {};
    const cfg = state.status?.config || {};
    const targets = status.targets?.summary || {};
    const historySummary = status.history_summary || {};
    const nextJob = nextScheduleItem();
    const totalTargets = Number(targets.share_targets || 0) + Number(targets.briefing_targets || 0);
    const dynamicCount = Number(historySummary.dynamic ?? historySummary.success ?? (status.media || []).length);
    const textCount = Number(
      historySummary.text ??
        Math.max(0, dynamicCount - Number(historySummary.media ?? 0))
    );
    const imageCount = Number(historySummary.image ?? 0);
    const videoCount = Number(historySummary.video ?? 0);
    const todayCount = Number(historySummary.today ?? 0);
    const currentPeriod = `${periodLabels[status.period?.key] || status.period?.key || "--"} ${status.period?.range || ""}`.trim();
    replaceChildren(el.configList, [
      configRow("自动分享", status.enabled ? "开启" : "关闭", "is-runtime"),
      configRow("全局触发", triggerSummary(cfg.trigger_mode)),
      configRow("全局类型", typeLabel(cfg.share_type)),
      configRow("QQ 空间", cfg.qzone_enabled ? "开启" : "关闭"),
      configRow("空间触发", triggerSummary(cfg.qzone_trigger_mode)),
      configRow("早报", `${cfg.briefing_60s ? "60s" : ""}${cfg.briefing_60s && cfg.briefing_ai ? " + " : ""}${cfg.briefing_ai ? "AI" : ""}` || "关闭"),
      configRow("早报空间", cfg.briefing_qzone_sync ? "开启" : "关闭"),
      configRow("当前时段", currentPeriod, "is-runtime"),
      configRow("定时任务", `${status.scheduler?.job_count || 0} 个`, "is-runtime"),
      configRow("接收目标", `${totalTargets} 个`, "is-runtime"),
    ]);
    replaceChildren(el.settingsSummary, [
      settingsSummaryItem("配图", Boolean(cfg.ai_image_enabled)),
      settingsSummaryItem("视频", Boolean(cfg.ai_video_enabled)),
      settingsSummaryItem("语音", Boolean(cfg.tts_enabled)),
      settingsSummaryItem("检索", Boolean(cfg.web_search_enabled)),
    ]);
    renderNextShareLine(nextJob);
    renderShareProgress();
    renderMediaStats({ dynamicCount, textCount, imageCount, videoCount, todayCount });
    if (el.configInsightList) {
      replaceChildren(el.configInsightList, []);
      el.configInsightList.hidden = true;
    }
  }

  return {
    fillNewsSources,
    isSpecificRunTarget,
    renderConfig,
    renderMetrics,
    renderRecentActions,
  };
}

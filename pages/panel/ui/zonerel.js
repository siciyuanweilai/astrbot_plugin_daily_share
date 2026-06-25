import {
  emptyNode,
  replaceChildren,
  text,
} from "./format.js?v=20260614-schedule-modes";

const RELATION_PAGE_SIZE = 9;
const RELATION_LABELS = {
  care: "我在意谁",
  care_by: "谁在意我",
};

function relationType(value) {
  return value === "care_by" ? "care_by" : "care";
}

function relationItems(state) {
  return state.qzoneRelationItems?.[relationType(state.qzoneRelationType)] || [];
}

function relationPageCount(items) {
  return Math.max(1, Math.ceil(items.length / RELATION_PAGE_SIZE));
}

function normalizeAvatar(url, uin) {
  const value = text(url).trim();
  if (value) return value.startsWith("//") ? `https:${value}` : value;
  const qq = text(uin).trim();
  return qq ? `https://q.qlogo.cn/headimg_dl?dst_uin=${encodeURIComponent(qq)}&spec=100` : "";
}

function friendName(item = {}) {
  return text(item.remark || item.name || item.nickname || item.uin).trim() || "QQ 用户";
}

function shortName(value) {
  const name = text(value).trim();
  if (name.length <= 3) return name;
  return `${name.slice(0, 2)}…`;
}

function createRelationItem(item = {}) {
  const link = document.createElement("a");
  link.className = "qzone-relation-item";
  link.href = text(item.home).trim() || `https://user.qzone.qq.com/${encodeURIComponent(text(item.uin).trim())}`;
  link.target = "_blank";
  link.rel = "noreferrer";
  link.title = `${friendName(item)} (${text(item.uin).trim()})`;

  const avatar = document.createElement("span");
  avatar.className = "qzone-relation-avatar";
  const img = document.createElement("img");
  img.alt = "";
  img.src = normalizeAvatar(item.avatar, item.uin);
  img.addEventListener("error", () => {
    avatar.textContent = shortName(friendName(item)) || "QQ";
    avatar.classList.add("is-fallback");
  }, { once: true });
  avatar.append(img);

  const overlay = document.createElement("span");
  overlay.className = "qzone-relation-name";
  overlay.textContent = shortName(friendName(item));
  avatar.append(overlay);

  const time = document.createElement("span");
  time.className = "qzone-relation-time";
  const score = Number(item.score || 0);
  time.textContent = text(item.time_label).trim() || (score > 0 ? `${score}` : "--");

  link.append(avatar, time);
  return link;
}

export function createQzoneRelation({
  state,
  elements: el,
  apiGet,
  setNotice,
} = {}) {
  function pageItems(items) {
    const pageCount = relationPageCount(items);
    state.qzoneRelationPage = Math.min(Math.max(0, state.qzoneRelationPage || 0), pageCount - 1);
    const start = state.qzoneRelationPage * RELATION_PAGE_SIZE;
    return items.slice(start, start + RELATION_PAGE_SIZE);
  }

  function renderRelation() {
    if (!el.qzoneRelationCard) return;
    const type = relationType(state.qzoneRelationType);
    const items = relationItems(state);
    for (const button of el.qzoneRelationTabs || []) {
      const active = relationType(button.dataset.qzoneRelation) === type;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    }

    if (state.qzoneRelationLoading && !items.length) {
      replaceChildren(el.qzoneRelationGrid, [emptyNode("正在加载在意好友...")]);
    } else if (state.qzoneRelationMessage && !items.length) {
      replaceChildren(el.qzoneRelationGrid, [emptyNode(state.qzoneRelationMessage)]);
    } else if (!items.length) {
      replaceChildren(el.qzoneRelationGrid, [emptyNode("暂无在意好友")]);
    } else {
      replaceChildren(el.qzoneRelationGrid, pageItems(items).map(createRelationItem));
    }

    const pageCount = relationPageCount(items);
    if (el.qzoneRelationPrev) el.qzoneRelationPrev.disabled = !items.length || state.qzoneRelationPage <= 0;
    if (el.qzoneRelationNext) el.qzoneRelationNext.disabled = !items.length || state.qzoneRelationPage >= pageCount - 1;
    if (el.qzoneRelationMeta) {
      el.qzoneRelationMeta.textContent = items.length
        ? `${state.qzoneRelationPage + 1}/${pageCount}`
        : "…";
    }

    const stats = state.qzoneRelationStats || {};
    const hasStats = Boolean(stats.available || stats.today_views || stats.total_views);
    if (el.qzoneRelationStats) {
      el.qzoneRelationStats.hidden = !hasStats;
      el.qzoneRelationStats.textContent = hasStats
        ? `今日浏览 ${Number(stats.today_views || 0)}　总浏览 ${Number(stats.total_views || 0)}`
        : "";
    }
  }

  async function loadRelation({ quiet = true, force = false } = {}) {
    if (!el.qzoneRelationCard || !apiGet || !state.bridgeReady) return;
    const type = relationType(state.qzoneRelationType);
    if (!force && state.qzoneRelationLoaded?.[type]) {
      renderRelation();
      return;
    }
    const requestSeq = state.qzoneRelationRequestSeq + 1;
    state.qzoneRelationRequestSeq = requestSeq;
    state.qzoneRelationLoading = true;
    state.qzoneRelationMessage = "";
    renderRelation();
    try {
      const data = await apiGet("page/qzone/relation", { type, _ts: Date.now() });
      if (requestSeq !== state.qzoneRelationRequestSeq) return;
      state.qzoneAccount = data.account || state.qzoneAccount;
      state.qzoneRelationItems[type] = Array.isArray(data.items) ? data.items : [];
      state.qzoneRelationLoaded[type] = true;
      state.qzoneRelationStats = data.stats || state.qzoneRelationStats;
      state.qzoneRelationMessage = "";
      if (!quiet) setNotice("");
    } catch (error) {
      if (requestSeq === state.qzoneRelationRequestSeq) {
        state.qzoneRelationMessage = error.message || `${RELATION_LABELS[type]}加载失败`;
        if (!quiet) setNotice(state.qzoneRelationMessage, "error");
      }
    } finally {
      if (requestSeq === state.qzoneRelationRequestSeq) {
        state.qzoneRelationLoading = false;
        renderRelation();
      }
    }
  }

  function switchRelation(type) {
    const nextType = relationType(type);
    if (nextType === state.qzoneRelationType) return;
    state.qzoneRelationType = nextType;
    state.qzoneRelationPage = 0;
    renderRelation();
    loadRelation({ quiet: true });
  }

  function changePage(delta) {
    const items = relationItems(state);
    const pageCount = relationPageCount(items);
    state.qzoneRelationPage = Math.min(
      Math.max(0, state.qzoneRelationPage + delta),
      pageCount - 1,
    );
    renderRelation();
  }

  function bindRelationEvents() {
    for (const button of el.qzoneRelationTabs || []) {
      button.addEventListener("click", () => switchRelation(button.dataset.qzoneRelation));
    }
    el.qzoneRelationPrev?.addEventListener("click", () => changePage(-1));
    el.qzoneRelationNext?.addEventListener("click", () => changePage(1));
  }

  return {
    bindRelationEvents,
    loadRelation,
    renderRelation,
  };
}

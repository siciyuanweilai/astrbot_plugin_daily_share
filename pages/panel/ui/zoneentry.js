import {
  emptyNode,
  replaceChildren,
  text,
} from "./format.js?v=20260614-schedule-modes";
import {
  QZONE_PAGE_SIZE,
  authorAvatar,
  authorName,
  fillAvatar,
  postId,
  qzoneContentText,
} from "./zonekit.js?v=20260618-qzone-mention-display";

const ENTRY_LABELS = {
  about: "与我相关",
  today: "那年今日",
  board: "留言板",
};

function createPostSummary(item = {}) {
  const node = document.createElement("article");
  node.className = "qzone-entry-item qzone-entry-post";

  const avatar = document.createElement("span");
  avatar.className = "qzone-avatar qzone-entry-avatar";
  fillAvatar(avatar, authorAvatar(item));

  const body = document.createElement("div");
  body.className = "qzone-entry-body";

  const title = document.createElement("div");
  title.className = "qzone-entry-item-title";
  title.textContent = authorName(item);

  const content = document.createElement("p");
  content.className = "qzone-entry-item-text";
  content.textContent = qzoneContentText(item);

  const meta = document.createElement("span");
  meta.className = "qzone-entry-item-meta";
  const images = Array.isArray(item.images) ? item.images.length : 0;
  const videos = Array.isArray(item.videos) ? item.videos.length : 0;
  meta.textContent = [
    text(item.created_at ? new Date(Number(item.created_at) * 1000).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "").trim(),
    images ? `${images} 图` : "",
    videos ? `${videos} 视频` : "",
  ].filter(Boolean).join(" · ");

  body.append(title, content, meta);
  node.append(avatar, body);
  return node;
}

function createMessageItem(item = {}) {
  const node = document.createElement("article");
  node.className = "qzone-entry-item qzone-entry-message";

  const avatar = document.createElement("span");
  avatar.className = "qzone-avatar qzone-entry-avatar";
  fillAvatar(avatar, item.author?.avatar);

  const body = document.createElement("div");
  body.className = "qzone-entry-body";

  const title = document.createElement("div");
  title.className = "qzone-entry-item-title";
  title.textContent = text(item.author?.nickname || item.author?.uin).trim() || "QQ 用户";

  const content = document.createElement("p");
  content.className = "qzone-entry-item-text";
  content.textContent = text(item.content).trim() || "暂无留言内容";

  const meta = document.createElement("span");
  meta.className = "qzone-entry-item-meta";
  meta.textContent = [
    item.floor ? `${item.floor} 楼` : "",
    text(item.time_label).trim(),
  ].filter(Boolean).join(" · ");

  body.append(title, content, meta);
  node.append(avatar, body);
  return node;
}

export function createQzoneEntry({
  state,
  elements: el,
  apiGet,
  renderQzone,
  setNotice,
} = {}) {
  function renderEntryButtons() {
    for (const button of el.qzoneEntryLinks || []) {
      const active = text(button.dataset.qzoneEntry).trim() === state.qzoneEntry;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    }
  }

  function renderEntryPanel() {
    renderEntryButtons();
    if (!el.qzoneEntryPanel) return;
    const active = Boolean(state.qzoneEntry);
    el.qzoneEntryPanel.hidden = !active;
    if (!active) return;

    if (el.qzoneEntryTitle) el.qzoneEntryTitle.textContent = ENTRY_LABELS[state.qzoneEntry] || "空间入口";
    if (el.qzoneEntryMeta) {
      el.qzoneEntryMeta.textContent = state.qzoneEntryLoading && !state.qzoneEntryLoadingMore
        ? "加载中..."
        : `${state.qzoneEntryItems.length} 条`;
    }

    if (state.qzoneEntryLoading && !state.qzoneEntryItems.length) {
      const loading = document.createElement("div");
      loading.className = "qzone-loading";
      loading.textContent = `正在加载${ENTRY_LABELS[state.qzoneEntry] || "空间内容"}...`;
      replaceChildren(el.qzoneEntryList, [loading]);
    } else if (!state.qzoneEntryItems.length) {
      replaceChildren(el.qzoneEntryList, [emptyNode(state.qzoneEntryMessage || "暂时没有读取到内容")]);
    } else {
      const renderer = state.qzoneEntryKind === "posts"
        ? createPostSummary
        : createMessageItem;
      replaceChildren(el.qzoneEntryList, state.qzoneEntryItems.map(renderer));
    }

    if (el.qzoneEntryMore) {
      el.qzoneEntryMore.hidden = !state.qzoneEntryHasMore;
      el.qzoneEntryMore.disabled = state.qzoneEntryLoadingMore;
      el.qzoneEntryMore.textContent = state.qzoneEntryLoadingMore ? "加载中..." : "加载更多";
    }
  }

  async function loadEntry(entry = state.qzoneEntry, { append = false } = {}) {
    const key = text(entry).trim();
    if (!key || !apiGet || !state.bridgeReady) return;
    if (append && (state.qzoneEntryLoadingMore || !state.qzoneEntryHasMore)) return;
    const requestSeq = state.qzoneEntryRequestSeq + 1;
    state.qzoneEntryRequestSeq = requestSeq;
    state.qzoneEntry = key;
    state.qzoneEntryLoading = true;
    state.qzoneEntryLoadingMore = append;
    state.qzoneEntryMessage = "";
    if (!append) {
      state.qzoneEntryItems = [];
      state.qzoneEntryNextPos = 0;
      state.qzoneEntryHasMore = false;
    }
    renderQzone();
    try {
      const data = await apiGet("page/qzone/entry", {
        entry: key,
        pos: append ? state.qzoneEntryNextPos : 0,
        num: QZONE_PAGE_SIZE,
        _ts: Date.now(),
      });
      if (requestSeq !== state.qzoneEntryRequestSeq) return;
      const items = Array.isArray(data.items) ? data.items : [];
      state.qzoneAccount = data.account || state.qzoneAccount;
      state.qzoneEntryKind = text(data.kind).trim();
      state.qzoneEntryItems = append ? [...state.qzoneEntryItems, ...items] : items;
      state.qzoneEntryHasMore = Boolean(data.has_more);
      state.qzoneEntryNextPos = Number(data.next_pos || state.qzoneEntryItems.length) || state.qzoneEntryItems.length;
      state.qzoneEntryMessage = text(data.message).trim();
      setNotice("");
    } catch (error) {
      if (requestSeq === state.qzoneEntryRequestSeq) {
        state.qzoneEntryMessage = error.message || `${ENTRY_LABELS[key] || "空间入口"}加载失败`;
        if (!append) state.qzoneEntryItems = [];
        setNotice(state.qzoneEntryMessage, "error");
      }
    } finally {
      if (requestSeq === state.qzoneEntryRequestSeq) {
        state.qzoneEntryLoading = false;
        state.qzoneEntryLoadingMore = false;
        renderQzone();
      }
    }
  }

  function closeEntry({ render = true } = {}) {
    state.qzoneEntry = "";
    state.qzoneEntryItems = [];
    state.qzoneEntryKind = "";
    state.qzoneEntryHasMore = false;
    state.qzoneEntryNextPos = 0;
    state.qzoneEntryMessage = "";
    if (render) renderQzone();
  }

  function bindEntryEvents() {
    for (const button of el.qzoneEntryLinks || []) {
      button.addEventListener("click", () => loadEntry(button.dataset.qzoneEntry));
    }
    el.qzoneEntryMore?.addEventListener("click", () => loadEntry(state.qzoneEntry, { append: true }));
    el.qzoneEntryClose?.addEventListener("click", closeEntry);
  }

  function rememberPostItems() {
    if (state.qzoneEntryKind !== "posts") return;
    for (const item of state.qzoneEntryItems || []) {
      const id = postId(item);
      if (id && !state.qzoneDetails.has(id)) state.qzoneDetails.set(id, item);
    }
  }

  return {
    bindEntryEvents,
    closeEntry,
    renderEntryPanel,
    rememberPostItems,
  };
}

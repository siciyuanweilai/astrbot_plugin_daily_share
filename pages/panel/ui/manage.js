export function mediaHistoryId(item = {}) {
  const id = Number(item.id);
  return Number.isInteger(id) && id > 0 ? id : 0;
}

function uniquePositiveIds(ids = []) {
  return [...new Set(ids.map((item) => Number(item)))]
    .filter((item) => Number.isInteger(item) && item > 0);
}

function mediaDeleteKey(ids = []) {
  return uniquePositiveIds(ids)
    .sort((a, b) => a - b)
    .join(",");
}

function setMediaToolbarChipContent(node, label, value = "") {
  if (!node) return;
  const title = document.createElement("span");
  title.textContent = label;
  if (value === "") {
    node.replaceChildren(title);
    return;
  }
  const body = document.createElement("strong");
  body.textContent = value;
  node.replaceChildren(title, body);
}

function createMediaToolbarButton(action, label, className = "text-button", value = "") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.dataset.mediaBulkAction = action;
  if (className.includes("media-stat-chip")) {
    setMediaToolbarChipContent(button, label, value);
  } else {
    button.textContent = label;
  }
  return button;
}

export function createMediaManageController({
  state,
  elements: el,
  apiPost,
  setNotice,
  reloadStatus,
  mediaPageParams,
  applyMediaPage,
  renderMedia,
  syncMediaFilterbarPin,
} = {}) {
  function selectedMediaIds() {
    return [...state.mediaSelectedIds]
      .map((item) => Number(item))
      .filter((item) => Number.isInteger(item) && item > 0);
  }

  function clearMediaPendingDelete({ render = false } = {}) {
    if (state.mediaPendingDeleteTimer) {
      window.clearTimeout(state.mediaPendingDeleteTimer);
      state.mediaPendingDeleteTimer = 0;
    }
    if (!state.mediaPendingDeleteKey) return;
    state.mediaPendingDeleteKey = "";
    state.mediaRenderSignature = "";
    if (render) renderMedia({ force: true });
  }

  function armMediaDelete(ids) {
    const key = mediaDeleteKey(ids);
    if (!key) return false;
    clearMediaPendingDelete();
    state.mediaPendingDeleteKey = key;
    state.mediaRenderSignature = "";
    state.mediaPendingDeleteTimer = window.setTimeout(() => {
      clearMediaPendingDelete({ render: true });
    }, 5000);
    renderMedia({ force: true });
    return true;
  }

  function clearMediaSelection() {
    clearMediaPendingDelete();
    state.mediaSelectMode = false;
    state.mediaSelectedIds.clear();
    state.mediaRenderSignature = "";
  }

  function syncMediaSelection(media = state.media) {
    const visibleIds = new Set(media.map(mediaHistoryId).filter(Boolean));
    for (const id of [...state.mediaSelectedIds]) {
      if (!visibleIds.has(id)) state.mediaSelectedIds.delete(id);
    }
  }

  function ensureMediaBulkToolbar() {
    const host = el.mediaStats;
    if (!host) return null;
    let toolbar = host.querySelector(".media-bulk-toolbar");
    if (toolbar) return toolbar;
    toolbar = el.mediaPanel?.querySelector(".media-bulk-toolbar");
    if (toolbar) {
      host.insertBefore(toolbar, host.firstChild);
      return toolbar;
    }

    toolbar = document.createElement("div");
    toolbar.className = "media-bulk-toolbar";

    const status = document.createElement("span");
    status.className = "media-bulk-status";
    status.dataset.mediaBulkStatus = "true";

    toolbar.append(
      createMediaToolbarButton("select", "\u7ba1\u7406", "media-stat-chip is-manage media-bulk-select"),
      status,
      createMediaToolbarButton("delete", "\u5220\u9664\u9009\u4e2d", "text-button danger media-bulk-delete"),
      createMediaToolbarButton("cancel", "\u53d6\u6d88", "text-button media-bulk-cancel"),
    );
    host.append(toolbar);
    return toolbar;
  }

  function renderMediaBulkToolbar(media = []) {
    const toolbar = ensureMediaBulkToolbar();
    if (!toolbar) return;
    const hasDeletableItems = media.some((item) => mediaHistoryId(item));
    const selectedCount = selectedMediaIds().length;
    toolbar.hidden = state.mediaKindFilter === "qzone" || !hasDeletableItems;
    toolbar.classList.toggle("is-selecting", state.mediaSelectMode);

    const status = toolbar.querySelector("[data-media-bulk-status]");
    const selectButton = toolbar.querySelector("[data-media-bulk-action='select']");
    const deleteButton = toolbar.querySelector("[data-media-bulk-action='delete']");
    const cancelButton = toolbar.querySelector("[data-media-bulk-action='cancel']");
    const confirming = selectedCount > 0 && state.mediaPendingDeleteKey === mediaDeleteKey(selectedMediaIds());

    if (status) {
      status.hidden = !state.mediaSelectMode;
      status.textContent = confirming ? "\u518d\u70b9\u786e\u8ba4" : `\u5df2\u9009 ${selectedCount} \u6761`;
    }
    if (selectButton) {
      selectButton.hidden = false;
      selectButton.disabled = state.mediaDeleting;
      selectButton.classList.toggle("active", state.mediaSelectMode);
      selectButton.setAttribute("aria-pressed", state.mediaSelectMode ? "true" : "false");
    }
    if (deleteButton) {
      deleteButton.hidden = !state.mediaSelectMode;
      deleteButton.disabled = state.mediaDeleting || selectedCount <= 0;
      deleteButton.classList.toggle("is-confirming", confirming);
      deleteButton.textContent = state.mediaDeleting
        ? "\u5220\u9664\u4e2d..."
        : confirming
          ? "\u786e\u8ba4\u5220\u9664"
          : "\u5220\u9664\u9009\u4e2d";
    }
    if (cancelButton) {
      cancelButton.hidden = !state.mediaSelectMode;
      cancelButton.disabled = state.mediaDeleting;
    }
  }

  function setMediaSelectMode(enabled) {
    state.mediaSelectMode = Boolean(enabled);
    if (!state.mediaSelectMode) state.mediaSelectedIds.clear();
    state.mediaRenderSignature = "";
    renderMedia({ force: true });
  }

  function syncVisibleMediaSelection() {
    if (!el.mediaList) return;
    for (const node of el.mediaList.querySelectorAll(".media-item[data-history-id]")) {
      const id = Number(node.dataset.historyId);
      const selected = state.mediaSelectedIds.has(id);
      node.classList.toggle("is-selected", selected);
      const button = node.querySelector(".media-select-toggle");
      if (!button) continue;
      button.textContent = selected ? "\u2713" : "";
      button.setAttribute("aria-pressed", selected ? "true" : "false");
      button.setAttribute(
        "aria-label",
        selected ? "\u53d6\u6d88\u9009\u62e9\u8bb0\u5f55" : "\u9009\u62e9\u8bb0\u5f55",
      );
    }
  }

  function toggleMediaSelected(item) {
    if (state.mediaDeleting) return;
    const id = mediaHistoryId(item);
    if (!id) return;
    if (state.mediaSelectedIds.has(id)) {
      state.mediaSelectedIds.delete(id);
    } else {
      state.mediaSelectedIds.add(id);
    }
    const media = state.mediaLoaded ? state.media : state.status?.media || [];
    syncVisibleMediaSelection();
    renderMediaBulkToolbar(media);
    syncMediaFilterbarPin();
    state.mediaRenderSignature = "";
  }

  async function deleteMediaRecords(ids) {
    if (state.mediaDeleting) return;
    const deleteIds = uniquePositiveIds(ids);
    if (!deleteIds.length) return;
    clearMediaPendingDelete();

    state.mediaDeleting = true;
    renderMedia({ force: true });
    try {
      const data = await apiPost("page/media/delete", {
        ids: deleteIds,
        ...mediaPageParams(state.mediaLimit),
      });
      applyMediaPage(data);
      syncMediaSelection(state.media);
      if (!selectedMediaIds().length) {
        state.mediaSelectMode = false;
      }
      const fileDeleted = Number(data.files?.deleted || 0);
      const fileSkipped = Number(data.files?.skipped || 0);
      const fileFailed = Number(data.files?.failed || 0);
      const fileText = data.files?.requested && (fileDeleted || fileSkipped || fileFailed)
        ? `，本地文件 ${fileDeleted} 个${fileSkipped ? `，跳过 ${fileSkipped} 个` : ""}${fileFailed ? `，失败 ${fileFailed} 个` : ""}`
        : "";
      setNotice(
        Number(data.deleted || 0) > 0 ? `已删除 ${data.deleted} 条记录${fileText}` : "没有记录被删除",
        Number(data.deleted || 0) > 0 ? "success" : "info",
      );
      await reloadStatus?.({ quiet: true, reveal: false });
    } catch (error) {
      setNotice(error.message || "删除记录失败", "error");
    } finally {
      state.mediaDeleting = false;
      renderMedia({ force: true });
    }
  }

  function requestMediaDelete(ids) {
    const deleteIds = uniquePositiveIds(ids);
    if (!deleteIds.length || state.mediaDeleting) return;
    const key = mediaDeleteKey(deleteIds);
    if (state.mediaPendingDeleteKey !== key) {
      armMediaDelete(deleteIds);
      return;
    }
    void deleteMediaRecords(deleteIds);
  }

  function deleteSelectedMedia() {
    requestMediaDelete(selectedMediaIds());
  }

  return {
    clearMediaSelection,
    deleteSelectedMedia,
    renderMediaBulkToolbar,
    selectedMediaIds,
    setMediaSelectMode,
    syncMediaSelection,
    toggleMediaSelected,
  };
}

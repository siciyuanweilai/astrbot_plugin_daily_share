import {
  emptyNode,
  replaceChildren,
  text,
} from "./format.js?v=20260614-schedule-modes";
import {
  QZONE_AUTO_LOAD_MARGIN_PX,
  QZONE_PAGE_SIZE,
  QZONE_RETRY_DELAYS_MS,
  fillAvatar,
  postId,
  qzoneContentText,
  qzoneNeedsExpand,
  scopeTitle,
} from "./zonekit.js?v=20260619-qzone-self-mood";
import { createQzonePostCardRenderer } from "./zonecard.js?v=20260618-qzone-reply-style";
import { createQzoneComposer } from "./zonepost.js?v=20260618-qzone-processing-notice-default";
import { bindQzoneUiEvents } from "./zonebind.js?v=20260613-refactor";
import { createQzoneActions } from "./zoneact.js?v=20260613-refactor";
import { createQzoneRelation } from "./zonerel.js?v=20260619-qzone-relation";
import { createQzoneEntry } from "./zoneentry.js?v=20260620-qzone-single-active";

export function createQzoneUi({
  state,
  elements: el,
  apiGet,
  apiPost,
  setNotice,
  openMediaLightbox,
  reloadStatus,
} = {}) {
  function currentTargetId() {
    if (state.qzoneScope === "target") return text(state.qzoneTargetId).trim();
    if (state.qzoneScope === "self") {
      return text(state.qzoneAccount?.uin || state.status?.qzone?.uin).trim();
    }
    return "";
  }

  function renderAccount() {
    const status = state.status?.qzone || {};
    const account = state.qzoneAccount || {};
    const uin = text(account.uin || status.uin).trim();
    const name = text(account.nickname || status.nickname).trim();
    const available = Boolean(status.available || account.uin);
    if (el.qzoneAccountName) el.qzoneAccountName.textContent = name || (available ? "我的说说" : "QQ 空间");
    if (el.qzoneAccountLine) {
      el.qzoneAccountLine.textContent = available ? `QQ ${uin || "--"}` : (text(status.error).trim() || "等待 OneBot 登录态");
    }
    if (el.qzoneAccountAvatar) {
      if (uin) {
        fillAvatar(el.qzoneAccountAvatar, `https://q.qlogo.cn/headimg_dl?dst_uin=${encodeURIComponent(uin)}&spec=100`);
      } else {
        fillAvatar(el.qzoneAccountAvatar);
      }
    }
    el.qzonePanel?.classList.toggle("is-qzone-error", !available);
  }

  function renderScope() {
    for (const button of el.qzoneScopeButtons || []) {
      const active = !state.qzoneEntry && button.dataset.qzoneScope === state.qzoneScope;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    }
    if (el.qzoneTargetField) el.qzoneTargetField.hidden = state.qzoneScope !== "target";
    if (el.qzoneTargetInput && el.qzoneTargetInput.value !== state.qzoneTargetId) {
      el.qzoneTargetInput.value = state.qzoneTargetId;
    }
  }

  function updateButtons() {
    if (el.qzoneRefreshButton) {
      el.qzoneRefreshButton.disabled = state.qzoneLoading;
      el.qzoneRefreshButton.classList.toggle("is-loading", state.qzoneLoading);
    }
    if (el.qzonePublishButton) {
      el.qzonePublishButton.disabled = state.qzonePublishing || state.qzoneMediaReading;
      el.qzonePublishButton.classList.toggle("is-loading", state.qzonePublishing);
    }
    if (el.qzoneMediaInput) el.qzoneMediaInput.disabled = state.qzonePublishing || state.qzoneMediaReading;
  }

  const composer = createQzoneComposer({
    state,
    elements: el,
    apiPost,
    setNotice,
    updateButtons,
    renderQzone,
    reloadStatus,
    loadQzoneFeed,
  });

  function clearRetry() {
    window.clearTimeout(state.qzoneRetryTimer);
    state.qzoneRetryTimer = 0;
    state.qzoneRetryCount = 0;
  }

  function scheduleRetry() {
    if (state.qzoneScope === "target" && !currentTargetId()) return;
    if (state.qzoneRetryCount >= QZONE_RETRY_DELAYS_MS.length) return;
    const delay = QZONE_RETRY_DELAYS_MS[state.qzoneRetryCount];
    state.qzoneRetryCount += 1;
    window.clearTimeout(state.qzoneRetryTimer);
    state.qzoneRetryTimer = window.setTimeout(() => {
      state.qzoneRetryTimer = 0;
      loadQzoneFeed({ quiet: true, autoRetry: true });
    }, delay);
  }

  function openQzoneImage(src) {
    const url = text(src).trim();
    if (!url) return;
    openMediaLightbox?.(url, "", "image");
  }

  function postItem(id) {
    return state.qzoneDetails.get(id) || state.qzoneItems.find((item) => postId(item) === id) || null;
  }

  function postCardNode(id) {
    if (!el.qzoneFeed) return null;
    return [...el.qzoneFeed.querySelectorAll(".qzone-card")].find((card) => card.dataset.postId === id) || null;
  }

  function closeQzoneMenu() {
    const menuId = state.qzoneMenuId || state.qzoneDeleteConfirmId;
    if (!menuId) return false;
    state.qzoneMenuId = "";
    state.qzoneDeleteConfirmId = "";
    const card = postCardNode(menuId);
    card?.querySelector(".qzone-card-menu-toggle")?.setAttribute("aria-expanded", "false");
    const panel = card?.querySelector(".qzone-card-menu-panel");
    if (panel) panel.hidden = true;
    return true;
  }

  function handleQzoneDocumentClick(event) {
    if (!state.qzoneMenuId && !state.qzoneDeleteConfirmId) return;
    if (event.target?.closest?.(".qzone-card-menu")) return;
    closeQzoneMenu();
  }

  function updatePostExpandView(id) {
    const item = postItem(id);
    const card = postCardNode(id);
    if (!item || !card) {
      renderFeed();
      return;
    }
    const expanded = state.qzoneExpandedId === id;
    const expandable = qzoneNeedsExpand(item);
    const content = card.querySelector(".qzone-content");
    if (content) {
      content.textContent = qzoneContentText(item);
      content.classList.toggle("is-collapsed", expandable && !expanded);
    }
    const expandButton = card.querySelector(".qzone-expand");
    if (expandButton) {
      expandButton.hidden = !expandable;
      expandButton.setAttribute("aria-expanded", expanded ? "true" : "false");
      expandButton.textContent = expanded ? "收起" : "展开全文";
    }
  }

  function updateCommentDraft(form) {
    const id = text(form?.dataset.postId).trim();
    const value = String(form?.elements?.content?.value || "");
    if (!id) return;
    if (value) {
      state.qzoneCommentDrafts.set(id, value);
    } else {
      state.qzoneCommentDrafts.delete(id);
    }
  }

  const actions = createQzoneActions({
    state,
    apiGet,
    apiPost,
    setNotice,
    reloadStatus,
    loadQzoneFeed,
    postItem,
    updatePostExpandView,
    renderQzone,
    renderFeed,
  });
  const createPostCard = createQzonePostCardRenderer({
    state,
    handleDeletePost: actions.handleDeletePost,
  });
  const relation = createQzoneRelation({
    state,
    elements: el,
    apiGet,
    setNotice,
  });
  const entry = createQzoneEntry({
    state,
    elements: el,
    apiGet,
    renderQzone,
    setNotice,
  });

  function canTryLoadMore() {
    return state.qzoneScope === "friends" && state.qzoneItems.length > 0 && !state.qzoneNoMore;
  }

  function renderQzoneMoreButton() {
    if (!el.qzoneMoreButton) return;
    if (state.qzoneEntry) {
      el.qzoneMoreButton.hidden = true;
      return;
    }
    const visible = state.qzoneItems.length > 0 && (
      state.qzoneHasMore ||
      state.qzoneLoadingMore ||
      canTryLoadMore()
    );
    el.qzoneMoreButton.hidden = !visible;
    el.qzoneMoreButton.disabled = state.qzoneLoadingMore;
    el.qzoneMoreButton.textContent = state.qzoneLoadingMore ? "加载中..." : "加载更多";
  }

  function renderFeed() {
    if (!el.qzoneFeed) return;
    const entryActive = Boolean(state.qzoneEntry);
    if (el.qzoneFeedToolbar) el.qzoneFeedToolbar.hidden = entryActive;
    el.qzoneFeed.hidden = entryActive;
    if (entryActive) {
      renderQzoneMoreButton();
      return;
    }
    const title = scopeTitle(state.qzoneScope, state.qzoneTargetId);
    if (el.qzoneFeedTitle) el.qzoneFeedTitle.textContent = title;
    if (el.qzoneFeedMeta) {
      el.qzoneFeedMeta.textContent = state.qzoneLoading && !state.qzoneLoadingMore ? "加载中..." : `${state.qzoneItems.length} 条`;
    }
    if (state.qzoneLoading && !state.qzoneItems.length) {
      const loading = document.createElement("div");
      loading.className = "qzone-loading";
      loading.textContent = "正在加载 QQ 空间动态...";
      replaceChildren(el.qzoneFeed, [loading]);
      renderQzoneMoreButton();
      return;
    }
    if (state.qzoneScope === "target" && !currentTargetId()) {
      replaceChildren(el.qzoneFeed, [emptyNode("输入 QQ 号后查看空间")]);
      renderQzoneMoreButton();
      return;
    }
    if (!state.qzoneItems.length && state.qzoneRetryable) {
      const label = state.qzoneRetryCount < QZONE_RETRY_DELAYS_MS.length
        ? "QQ 空间暂不可用，正在重新加载..."
        : (state.qzoneMessage || "QQ 空间暂不可用");
      replaceChildren(el.qzoneFeed, [emptyNode(label)]);
      renderQzoneMoreButton();
      return;
    }
    if (!state.qzoneItems.length) {
      replaceChildren(el.qzoneFeed, [emptyNode("还没有读取到说说")]);
      renderQzoneMoreButton();
      return;
    }
    replaceChildren(el.qzoneFeed, state.qzoneItems.map(createPostCard));
    renderQzoneMoreButton();
  }

  function renderQzone() {
    renderAccount();
    relation.renderRelation();
    entry.rememberPostItems();
    entry.renderEntryPanel();
    renderScope();
    composer.renderComposerMedia();
    updateButtons();
    renderFeed();
    window.requestAnimationFrame(handleQzonePageScroll);
  }

  function mergeQzoneItems(items) {
    const merged = new Map();
    const beforeCount = state.qzoneItems.length;
    for (const item of [...state.qzoneItems, ...items]) {
      const key = postId(item);
      if (key) merged.set(key, item);
    }
    state.qzoneItems = [...merged.values()];
    return state.qzoneItems.length - beforeCount;
  }

  async function loadQzoneFeed({ quiet = false, autoRetry = false, append = false } = {}) {
    if (!el.qzonePanel || !apiGet || !state.bridgeReady) return;
    if (append && (state.qzoneLoadingMore || (!state.qzoneHasMore && !canTryLoadMore()))) return;
    const targetId = currentTargetId();
    if (state.qzoneScope === "target" && !targetId) {
      state.qzoneItems = [];
      state.qzoneDetails.clear();
      state.qzoneSelectedId = "";
      state.qzoneHasMore = false;
      state.qzoneLoadingMore = false;
      state.qzoneNoMore = false;
      renderQzone();
      return;
    }
    const requestSeq = state.qzoneRequestSeq + 1;
    state.qzoneRequestSeq = requestSeq;
    state.qzoneLoading = true;
    state.qzoneLoadingMore = append;
    renderQzone();
    try {
      const data = await apiGet("page/qzone/feed", {
        scope: state.qzoneScope === "target" ? "profile" : state.qzoneScope,
        target_id: targetId,
        pos: append ? state.qzoneItems.length : 0,
        num: QZONE_PAGE_SIZE,
        detail: state.qzoneScope === "friends" ? "1" : "",
        _ts: Date.now(),
      });
      if (requestSeq !== state.qzoneRequestSeq) return;
      const items = Array.isArray(data.items) ? data.items : [];
      state.qzoneAccount = data.account || state.qzoneAccount;
      let addedCount = items.length;
      if (append) {
        addedCount = mergeQzoneItems(items);
        if (addedCount <= 0) state.qzoneNoMore = true;
      } else {
        state.qzoneItems = items;
        state.qzoneDetails.clear();
        state.qzoneExpandedId = "";
        state.qzoneCommentExpandedId = "";
        state.qzoneMenuId = "";
        state.qzoneDeleteConfirmId = "";
        state.qzoneNoMore = false;
      }
      state.qzoneMessage = text(data.message).trim();
      state.qzoneRetryable = Boolean(data.retryable);
      state.qzoneHasMore = typeof data.has_more === "boolean"
        ? (append ? data.has_more && addedCount > 0 : data.has_more || items.length > 0)
        : (append ? addedCount > 0 : items.length > 0);
      if (!state.qzoneItems.some((item) => postId(item) === state.qzoneSelectedId)) {
        state.qzoneSelectedId = "";
      }
      if (state.qzoneRetryable) scheduleRetry();
      else clearRetry();
      if (!quiet) setNotice("");
    } catch (error) {
      if (requestSeq === state.qzoneRequestSeq) {
        if (append) {
          setNotice(error.message || "更多说说加载失败", "error");
        } else {
          state.qzoneMessage = error.message || "QQ 空间说说加载失败";
          state.qzoneRetryable = true;
          state.qzoneHasMore = false;
          if (!autoRetry) state.qzoneRetryCount = 0;
          scheduleRetry();
          if (!quiet) setNotice(error.message || "QQ 空间说说加载失败", "error");
        }
      }
    } finally {
      if (requestSeq === state.qzoneRequestSeq) {
        state.qzoneLoading = false;
        state.qzoneLoadingMore = false;
        renderQzone();
      }
    }
  }

  function loadMoreQzoneFeed() {
    loadQzoneFeed({ quiet: true, append: true });
  }

  function canAutoLoadMore() {
    return Boolean(
      el.qzonePanel &&
      !el.qzonePanel.hidden &&
      state.bridgeReady &&
      state.qzoneItems.length &&
      !state.qzoneLoading &&
      !state.qzoneLoadingMore &&
      (state.qzoneHasMore || canTryLoadMore())
    );
  }

  function handleQzonePageScroll() {
    if (!canAutoLoadMore()) return;
    const doc = document.documentElement;
    const scrollTop = window.scrollY || doc.scrollTop || 0;
    const viewportBottom = scrollTop + window.innerHeight;
    const pageBottom = Math.max(doc.scrollHeight, document.body?.scrollHeight || 0);
    if (viewportBottom >= pageBottom - QZONE_AUTO_LOAD_MARGIN_PX) loadMoreQzoneFeed();
  }

  function closeQzoneEvents() {
    window.clearTimeout(state.qzoneRetryTimer);
    window.clearTimeout(state.qzoneTargetTimer);
    state.qzoneRetryTimer = 0;
    state.qzoneTargetTimer = 0;
    document.removeEventListener("click", handleQzoneDocumentClick);
    window.removeEventListener("scroll", handleQzonePageScroll);
  }

  function resetFeedState() {
    clearRetry();
    state.qzoneItems = [];
    state.qzoneDetails.clear();
    state.qzoneSelectedId = "";
    state.qzoneExpandedId = "";
    state.qzoneCommentExpandedId = "";
    state.qzoneCommentDrafts.clear();
    state.qzoneMenuId = "";
    state.qzoneDeleteConfirmId = "";
    state.qzoneDeletingId = "";
    state.qzoneMessage = "";
    state.qzoneRetryable = false;
    state.qzoneHasMore = false;
    state.qzoneLoadingMore = false;
    state.qzoneNoMore = false;
  }

  function bindQzoneEvents() {
    bindQzoneUiEvents({
      state,
      elements: el,
      composer,
      updateButtons,
      loadQzoneFeed,
      loadMoreQzoneFeed,
      handleQzoneDocumentClick,
      handleQzonePageScroll,
      resetFeedState,
      closeEntry: entry.closeEntry,
      renderQzone,
      renderFeed,
      closeQzoneMenu,
      openQzoneImage,
      postCardNode,
      loadDetail: actions.loadDetail,
      toggleExpandPost: actions.toggleExpandPost,
      selectPost: actions.selectPost,
      likePost: actions.likePost,
      handleDeletePost: actions.handleDeletePost,
      updateCommentDraft,
      submitComment: actions.submitComment,
    });
    relation.bindRelationEvents();
    entry.bindEntryEvents();
  }

  return {
    bindQzoneEvents,
    closeQzoneEvents,
    loadQzoneFeed,
    loadQzoneRelation: relation.loadRelation,
    renderQzone,
  };
}

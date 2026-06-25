import { text } from "./format.js?v=20260614-schedule-modes";

export function bindQzoneUiEvents({
  state,
  elements: el,
  composer,
  updateButtons,
  loadQzoneFeed,
  loadMoreQzoneFeed,
  handleQzoneDocumentClick,
  handleQzonePageScroll,
  resetFeedState,
  closeEntry,
  renderQzone,
  renderFeed,
  closeQzoneMenu,
  openQzoneImage,
  postCardNode,
  loadDetail,
  toggleExpandPost,
  selectPost,
  likePost,
  handleDeletePost,
  updateCommentDraft,
  submitComment,
} = {}) {
  el.qzonePublishForm?.addEventListener("submit", composer.publishQzone);
  el.qzoneMediaInput?.addEventListener("change", async () => {
    await composer.uploadQzoneFiles(el.qzoneMediaInput.files || []);
    el.qzoneMediaInput.value = "";
  });
  el.qzoneMediaStrip?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-qzone-media-index]");
    if (!button) return;
    const index = Number(button.dataset.qzoneMediaIndex);
    if (!Number.isInteger(index)) return;
    state.qzoneMedia.splice(index, 1);
    composer.renderComposerMedia();
    updateButtons();
  });
  el.qzoneRefreshButton?.addEventListener("click", () => loadQzoneFeed());
  el.qzoneMoreButton?.addEventListener("click", loadMoreQzoneFeed);
  document.addEventListener("click", handleQzoneDocumentClick);
  window.addEventListener("scroll", handleQzonePageScroll, { passive: true });
  el.qzoneTargetInput?.addEventListener("input", () => {
    resetFeedState();
    state.qzoneTargetId = text(el.qzoneTargetInput.value).trim();
    window.clearTimeout(state.qzoneTargetTimer);
    state.qzoneTargetTimer = window.setTimeout(() => {
      state.qzoneTargetTimer = 0;
      loadQzoneFeed({ quiet: true });
    }, 360);
    renderQzone();
  });
  for (const button of el.qzoneScopeButtons || []) {
    button.addEventListener("click", () => {
      const nextScope = button.dataset.qzoneScope || "friends";
      if (nextScope === state.qzoneScope) {
        closeEntry?.();
        return;
      }
      state.qzoneScope = nextScope;
      closeEntry?.({ render: false });
      resetFeedState();
      renderQzone();
      loadQzoneFeed({ quiet: true });
    });
  }
  el.qzoneFeed?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-qzone-action]");
    if (!button) {
      closeQzoneMenu();
      return;
    }
    const action = button.dataset.qzoneAction;
    const id = button.dataset.postId;
    if (action === "image") {
      event.preventDefault();
      event.stopPropagation();
      closeQzoneMenu();
      openQzoneImage(button.dataset.qzoneImageSrc);
      return;
    }
    if (action === "menu") {
      event.preventDefault();
      event.stopPropagation();
      const nextMenuId = state.qzoneMenuId === id ? "" : id;
      state.qzoneMenuId = nextMenuId;
      if (state.qzoneDeleteConfirmId !== nextMenuId) state.qzoneDeleteConfirmId = "";
      renderFeed();
      return;
    }
    if (action === "delete") {
      event.preventDefault();
      event.stopPropagation();
      handleDeletePost(id);
      return;
    }
    if (action === "expand") {
      event.preventDefault();
      event.stopPropagation();
      closeQzoneMenu();
      toggleExpandPost(id);
      return;
    }
    if (action === "comment-focus") {
      event.preventDefault();
      event.stopPropagation();
      closeQzoneMenu();
      const input = postCardNode(id)?.querySelector(".qzone-card-comment-input");
      input?.focus();
      return;
    }
    if (action === "comments") {
      event.preventDefault();
      event.stopPropagation();
      closeQzoneMenu();
      state.qzoneCommentExpandedId = state.qzoneCommentExpandedId === id ? "" : id;
      renderFeed();
      if (state.qzoneCommentExpandedId === id && !state.qzoneDetails.has(id)) {
        loadDetail(id).then(renderFeed);
      }
      return;
    }
    if (action === "select") selectPost(id);
    if (action === "detail") selectPost(id, { fetchDetail: true });
    if (action === "like") likePost(id);
  });
  el.qzoneFeed?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const button = event.target.closest("[data-qzone-action='select']");
    if (!button) return;
    event.preventDefault();
    selectPost(button.dataset.postId);
  });
  el.qzoneFeed?.addEventListener("input", (event) => {
    if (!event.target?.classList?.contains("qzone-card-comment-input")) return;
    updateCommentDraft(event.target.closest(".qzone-comment-form"));
  });
  el.qzoneFeed?.addEventListener("submit", (event) => {
    if (event.target?.classList?.contains("qzone-comment-form")) submitComment(event);
  });
}

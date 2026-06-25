import { text } from "./format.js?v=20260614-schedule-modes";
import {
  postId,
  samePost,
} from "./zonekit.js?v=20260613-qzone-split";

export function createQzoneActions({
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
} = {}) {
  async function loadDetail(id) {
    if (!id || state.qzoneDetails.has(id)) return;
    try {
      const data = await apiGet("page/qzone/detail", { id, _ts: Date.now() });
      const item = data.item || data.post;
      if (item) {
        let mergedItem = item;
        state.qzoneItems = state.qzoneItems.map((old) => {
          if (!samePost(old, id)) return old;
          const next = { ...old, ...item };
          next.expandable = Boolean(old.expandable || item.expandable);
          mergedItem = next;
          return next;
        });
        state.qzoneDetails.set(id, mergedItem);
      }
    } catch (error) {
      setNotice(error.message || "说说详情加载失败", "error");
    }
  }

  async function toggleExpandPost(id) {
    if (!id) return;
    if (state.qzoneExpandedId === id) {
      state.qzoneExpandedId = "";
      updatePostExpandView(id);
      return;
    }
    state.qzoneExpandedId = id;
    updatePostExpandView(id);
    if (!state.qzoneDetails.has(id)) {
      await loadDetail(id);
      updatePostExpandView(id);
    }
  }

  async function selectPost(id, { fetchDetail = false } = {}) {
    state.qzoneSelectedId = id;
    renderQzone();
    if (fetchDetail) {
      await loadDetail(id);
      renderQzone();
    }
  }

  async function likePost(id) {
    if (!id) return;
    try {
      await apiPost("page/qzone/like", { id });
      setNotice("已点赞", "success");
      await loadQzoneFeed({ quiet: true });
    } catch (error) {
      setNotice(error.message || "点赞失败", "error");
    }
  }

  async function deletePost(id) {
    if (!id) return;
    const item = postItem(id);
    if (!item?.can_delete) {
      setNotice("只能删除自己发布的说说", "error");
      return;
    }
    state.qzoneDeletingId = id;
    state.qzoneMenuId = id;
    renderFeed();
    try {
      await apiPost("page/qzone/delete", { id }, 45000);
      state.qzoneItems = state.qzoneItems.filter((old) => postId(old) !== id);
      state.qzoneDetails.delete(id);
      state.qzoneCommentDrafts.delete(id);
      if (state.qzoneSelectedId === id) state.qzoneSelectedId = "";
      if (state.qzoneExpandedId === id) state.qzoneExpandedId = "";
      if (state.qzoneCommentExpandedId === id) state.qzoneCommentExpandedId = "";
      if (state.qzoneMenuId === id) state.qzoneMenuId = "";
      if (state.qzoneDeleteConfirmId === id) state.qzoneDeleteConfirmId = "";
      setNotice("说说已删除", "success");
      renderQzone();
      await reloadStatus?.({ quiet: true });
    } catch (error) {
      setNotice(error.message || "删除失败", "error");
      renderFeed();
    } finally {
      if (state.qzoneDeletingId === id) {
        state.qzoneDeletingId = "";
        renderFeed();
      }
    }
  }

  async function handleDeletePost(id) {
    if (!id || state.qzoneDeletingId === id) return;
    if (state.qzoneDeleteConfirmId !== id) {
      state.qzoneDeleteConfirmId = id;
      state.qzoneMenuId = id;
      setNotice("再次点击确认删除", "info", 2600);
      renderFeed();
      return;
    }
    await deletePost(id);
  }

  async function submitComment(event) {
    event.preventDefault();
    const form = event.target?.classList?.contains("qzone-comment-form") ? event.target : event.currentTarget;
    const id = text(form?.dataset.postId).trim();
    const input = form?.elements?.content;
    const content = text(input?.value).trim();
    if (!id || !content) return;
    const button = form.querySelector("button[type='submit']");
    if (button) button.disabled = true;
    if (input) input.disabled = true;
    try {
      await apiPost("page/qzone/comment", { id, content });
      if (input) input.value = "";
      state.qzoneCommentDrafts.delete(id);
      state.qzoneDetails.delete(id);
      await loadDetail(id);
      setNotice("评论已发送", "success");
      renderQzone();
    } catch (error) {
      setNotice(error.message || "评论发送失败", "error");
    } finally {
      if (button) button.disabled = false;
      if (input) input.disabled = false;
    }
  }

  return {
    handleDeletePost,
    likePost,
    loadDetail,
    selectPost,
    submitComment,
    toggleExpandPost,
  };
}

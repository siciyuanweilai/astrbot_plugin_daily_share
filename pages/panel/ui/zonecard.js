import {
  authorAvatar,
  authorName,
  commentAuthorAvatar,
  commentAuthorName,
  commentList,
  commentTime,
  createTextNode,
  fillAvatar,
  imageList,
  postId,
  postTime,
  qzoneContentText,
  qzoneDisplayText,
  qzoneIcon,
  qzoneNeedsExpand,
  statNumber,
} from "./zonekit.js?v=20260618-qzone-mention-display";

function renderMedia(images) {
  if (!images.length) return null;
  const grid = document.createElement("div");
  grid.className = `qzone-media-grid count-${Math.min(images.length, 9)}`;
  for (const src of images.slice(0, 9)) {
    const media = document.createElement("button");
    media.type = "button";
    media.className = "qzone-media";
    media.dataset.qzoneAction = "image";
    media.dataset.qzoneImageSrc = src;
    media.setAttribute("aria-label", "查看空间配图");
    const img = document.createElement("img");
    img.loading = "lazy";
    img.alt = "空间配图";
    img.src = src;
    img.addEventListener("error", () => media.remove(), { once: true });
    media.append(img);
    grid.append(media);
  }
  return grid;
}

function createAvatar(item) {
  const avatar = document.createElement("span");
  avatar.className = "qzone-avatar";
  fillAvatar(avatar, authorAvatar(item));
  return avatar;
}

function createSocialButton({ action, postId: id, icon, label, count = 0, active = false }) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `qzone-social-button${active ? " active" : ""}`;
  button.dataset.qzoneAction = action;
  button.dataset.postId = id;
  button.setAttribute("aria-label", label);
  button.title = label;
  button.append(qzoneIcon(icon));
  const value = document.createElement("span");
  value.className = "qzone-social-count";
  value.textContent = String(count);
  button.append(value);
  return button;
}

function replyToName(comment = {}) {
  const target = comment.reply_to || {};
  return qzoneDisplayText(target.nickname || target.name || target.uin);
}

function escapeRegExp(value = "") {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function commentContentText(comment = {}, targetName = "") {
  const content = qzoneDisplayText(comment.content);
  return targetName ? content.replace(new RegExp(`^@${escapeRegExp(targetName)}\\s*`), "") : content;
}

function createCardComments(item, id, state) {
  const comments = commentList(item).filter((comment) => commentContentText(comment, replyToName(comment)));
  const block = document.createElement("div");
  block.className = "qzone-card-comments";
  if (!comments.length) {
    block.hidden = true;
    return block;
  }
  const expanded = state.qzoneCommentExpandedId === id;
  const previewCount = expanded ? comments.length : 3;
  for (const comment of comments.slice(0, previewCount)) {
    const targetName = replyToName(comment);
    const row = document.createElement("div");
    row.className = "qzone-card-comment";
    row.classList.toggle("is-reply", Boolean(targetName));
    const avatar = document.createElement("span");
    avatar.className = "qzone-comment-avatar";
    fillAvatar(avatar, commentAuthorAvatar(comment));
    const body = document.createElement("span");
    body.className = "qzone-card-comment-body";
    const line = document.createElement("span");
    line.className = "qzone-card-comment-line";
    const name = document.createElement("strong");
    name.textContent = commentAuthorName(comment);
    const content = document.createElement("span");
    content.textContent = commentContentText(comment, targetName);
    if (targetName) {
      const replyLabel = document.createElement("span");
      replyLabel.className = "qzone-comment-reply-label";
      replyLabel.textContent = " 回复";
      const target = document.createElement("strong");
      target.textContent = targetName;
      line.append(name, replyLabel, target, document.createTextNode("："), content);
    } else {
      line.append(name, document.createTextNode("："), content);
    }
    const time = commentTime(comment.created_at);
    body.append(line);
    if (time) body.append(createTextNode("qzone-card-comment-time", time));
    row.append(avatar, body);
    block.append(row);
  }
  const displayTotal = Math.max(statNumber(item, "comments"), comments.length);
  if (displayTotal > previewCount) {
    const more = document.createElement("button");
    more.type = "button";
    more.className = "qzone-card-comment-more";
    more.dataset.qzoneAction = "comments";
    more.dataset.postId = id;
    more.textContent = `查看全部 ${displayTotal} 条评论`;
    block.append(more);
  } else if (expanded && comments.length > 3) {
    const collapse = document.createElement("button");
    collapse.type = "button";
    collapse.className = "qzone-card-comment-more";
    collapse.dataset.qzoneAction = "comments";
    collapse.dataset.postId = id;
    collapse.textContent = "收起评论";
    block.append(collapse);
  }
  return block;
}

function createCardCommentForm(id, state) {
  const form = document.createElement("form");
  form.className = "qzone-comment-form qzone-card-comment-form";
  form.dataset.postId = id;
  const input = document.createElement("input");
  input.type = "text";
  input.name = "content";
  input.autocomplete = "off";
  input.className = "qzone-card-comment-input";
  input.placeholder = "评论";
  input.value = state.qzoneCommentDrafts.get(id) || "";
  const hint = document.createElement("span");
  hint.className = "qzone-comment-enter-hint";
  hint.textContent = "Enter ↵";
  form.append(input, hint);
  return form;
}

function createCardSocial(item, id, state) {
  const social = document.createElement("div");
  social.className = "qzone-card-social";

  const top = document.createElement("div");
  top.className = "qzone-card-social-top";
  const buttons = document.createElement("div");
  buttons.className = "qzone-card-social-buttons";
  buttons.append(
    createSocialButton({
      action: "like",
      postId: id,
      icon: "like",
      label: item.liked ? "已点赞" : "点赞",
      count: statNumber(item, "likes"),
      active: Boolean(item.liked),
    }),
    createSocialButton({
      action: "comment-focus",
      postId: id,
      icon: "comment",
      label: "评论",
      count: statNumber(item, "comments"),
    }),
  );
  top.append(buttons);
  social.append(top, createCardComments(item, id, state), createCardCommentForm(id, state));
  return social;
}

export function createQzonePostCardRenderer({ state, handleDeletePost }) {
  return function createPostCard(item = {}) {
    const id = postId(item);
    const card = document.createElement("article");
    const canDelete = Boolean(item.can_delete);
    card.className = [
      "qzone-card",
      state.qzoneSelectedId === id ? "selected" : "",
      canDelete ? "has-menu" : "",
    ].filter(Boolean).join(" ");
    card.dataset.postId = id;

    const button = document.createElement("div");
    button.className = "qzone-card-main";
    button.dataset.qzoneAction = "select";
    button.dataset.postId = id;
    button.tabIndex = 0;
    button.role = "button";

    const head = document.createElement("div");
    head.className = "qzone-card-head";
    const identity = document.createElement("div");
    identity.className = "qzone-identity";
    const author = document.createElement("strong");
    author.textContent = authorName(item);
    const meta = createTextNode("qzone-card-time", postTime(item.created_at));
    identity.append(author, meta);
    head.append(createAvatar(item), identity);

    const content = document.createElement("p");
    content.className = "qzone-content";
    const contentText = qzoneContentText(item);
    const expanded = state.qzoneExpandedId === id;
    const expandable = qzoneNeedsExpand(item);
    content.classList.toggle("is-collapsed", expandable && !expanded);
    content.textContent = contentText;

    button.append(head, content);
    if (expandable) {
      const expandButton = document.createElement("button");
      expandButton.type = "button";
      expandButton.className = "qzone-expand";
      expandButton.dataset.qzoneAction = "expand";
      expandButton.dataset.postId = id;
      expandButton.setAttribute("aria-expanded", expanded ? "true" : "false");
      expandButton.textContent = expanded ? "收起" : "展开全文";
      button.append(expandButton);
    }
    const media = renderMedia(imageList(item));
    if (media) button.append(media);

    if (canDelete) {
      const menu = document.createElement("div");
      menu.className = "qzone-card-menu";
      const menuOpen = state.qzoneMenuId === id;
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "qzone-card-menu-toggle";
      toggle.dataset.qzoneAction = "menu";
      toggle.dataset.postId = id;
      toggle.setAttribute("aria-label", "展开说说操作");
      toggle.setAttribute("aria-expanded", menuOpen ? "true" : "false");
      toggle.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.6 5.8 8 10.2l4.4-4.4"/></svg>';
      const panel = document.createElement("div");
      panel.className = "qzone-card-menu-panel";
      panel.hidden = !menuOpen;
      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.className = state.qzoneDeleteConfirmId === id ? "confirm-delete" : "";
      deleteButton.dataset.qzoneAction = "delete";
      deleteButton.dataset.postId = id;
      deleteButton.disabled = state.qzoneDeletingId === id;
      deleteButton.textContent = state.qzoneDeletingId === id
        ? "删除中..."
        : (state.qzoneDeleteConfirmId === id ? "确认删除" : "删除");
      deleteButton.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        handleDeletePost(id);
      });
      panel.append(deleteButton);
      menu.append(toggle, panel);
      card.append(menu);
    }

    card.append(button, createCardSocial(item, id, state));
    return card;
  };
}

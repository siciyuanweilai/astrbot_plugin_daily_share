import {
  formatMediaTime,
  text,
} from "./format.js?v=20260614-schedule-modes";

export const QZONE_PAGE_SIZE = 10;
export const QZONE_RETRY_DELAYS_MS = [1800, 5000, 12000];
export const QZONE_MEDIA_LIMIT = 9;
export const QZONE_VIDEO_LIMIT = 1;
export const QZONE_PREVIEW_LINES = 6;
export const QZONE_PREVIEW_TEXT_LIMIT = 150;
export const QZONE_AUTO_LOAD_MARGIN_PX = 520;

export function postId(item = {}) {
  return text(item.id || item.post_id || item.tid).trim();
}

export function samePost(item = {}, id = "") {
  return postId(item) === text(id).trim();
}

export function postTime(value) {
  const numeric = Number(value || 0);
  if (!numeric) return "未知时间";
  return formatMediaTime(new Date(numeric * 1000).toISOString());
}

export function authorName(item = {}) {
  const author = item.author || {};
  return text(author.nickname || author.name || author.uin).trim() || "QQ 空间用户";
}

export function authorAvatar(item = {}) {
  const author = item.author || {};
  const avatar = text(author.avatar).trim();
  if (avatar) return avatar.startsWith("//") ? `https:${avatar}` : avatar;
  const uin = text(author.uin).trim();
  return uin ? `https://q.qlogo.cn/headimg_dl?dst_uin=${encodeURIComponent(uin)}&spec=100` : "";
}

export function fillAvatar(container, url = "") {
  container.replaceChildren();
  container.classList.remove("has-image");
  const src = text(url).trim();
  if (!src) {
    container.textContent = "🌸";
    return;
  }
  const img = document.createElement("img");
  img.alt = "";
  img.src = src.startsWith("//") ? `https:${src}` : src;
  img.addEventListener("error", () => {
    container.classList.remove("has-image");
    container.textContent = "🌸";
  }, { once: true });
  container.append(img);
  container.classList.add("has-image");
}

export function isDisplayableQzoneImage(url) {
  const lower = text(url).trim().toLowerCase();
  if (!lower) return false;
  if (!lower.startsWith("http://") && !lower.startsWith("https://") && !lower.startsWith("data:image/")) return false;
  return ![
    "qzonestyle.gtimg.cn",
    "qlogo.cn",
    "q.qlogo.cn",
    "q1.qlogo.cn",
    "thirdqq.qlogo.cn",
    "headimg_dl",
    "/head/",
    "/portrait/",
    "blank.gif",
    "loading.gif",
    "transparent.gif",
    "space.gif",
  ].some((item) => lower.includes(item));
}

export function imageList(item = {}) {
  return Array.isArray(item.images) ? item.images.filter(isDisplayableQzoneImage) : [];
}

export function commentList(item = {}) {
  return Array.isArray(item.comments) ? item.comments : [];
}

export function statNumber(item = {}, key) {
  const value = Number(item.stats?.[key] ?? item[key] ?? 0);
  return Number.isFinite(value) && value > 0 ? value : 0;
}

export function commentAuthorName(comment = {}) {
  const author = comment.author || {};
  return text(author.nickname || author.name || author.uin).trim() || "QQ 用户";
}

export function commentAuthorAvatar(comment = {}) {
  const author = comment.author || {};
  const avatar = text(author.avatar).trim();
  if (avatar) return avatar.startsWith("//") ? `https:${avatar}` : avatar;
  const uin = text(author.uin).trim();
  return uin ? `https://q.qlogo.cn/headimg_dl?dst_uin=${encodeURIComponent(uin)}&spec=100` : "";
}

export function commentTime(value) {
  const numeric = Number(value || 0);
  return numeric ? formatMediaTime(new Date(numeric * 1000).toISOString()) : "";
}

export function qzoneIcon(kind) {
  const icons = {
    like: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7.2 20.3H4.8a1.8 1.8 0 0 1-1.8-1.8v-7.1a1.8 1.8 0 0 1 1.8-1.8h2.4v10.7Zm2.1 0V9.2l4.1-5.8c.5-.8 1.7-.4 1.7.6v4.1h3.8c1.3 0 2.3 1.2 2 2.5l-1.5 7.7a2.4 2.4 0 0 1-2.4 2H9.3Z"/></svg>',
    comment: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5.4A3.4 3.4 0 0 1 8.4 2h7.2A3.4 3.4 0 0 1 19 5.4v5.2a3.4 3.4 0 0 1-3.4 3.4h-4.4l-4.1 4.1c-.8.8-2.1.2-2.1-.9V5.4Zm3.4-.8a.8.8 0 0 0-.8.8v9l2.6-2.6h5.4a.8.8 0 0 0 .8-.8V5.4a.8.8 0 0 0-.8-.8H8.4Z"/></svg>',
  };
  const node = document.createElement("span");
  node.className = "qzone-action-icon";
  node.innerHTML = icons[kind] || "";
  return node;
}

export function scopeTitle(scope, targetId) {
  if (scope === "self") return "我的说说";
  if (scope === "target") return targetId ? `${targetId} 的空间` : "指定 QQ";
  return "好友动态";
}

export function createTextNode(className, value, fallback = "") {
  const node = document.createElement("span");
  node.className = className;
  node.textContent = text(value).trim() || fallback;
  return node;
}

export function qzoneDisplayText(value) {
  return text(value).replace(/@\{([^{}]+)\}/g, (source, body) => {
    const nickname = String(body || "").match(/(?:^|,)nick:([^,{}]+)/i)?.[1]?.trim();
    return nickname ? `@${nickname} ` : source;
  }).replace(/[ \t]{2,}/g, " ").trim();
}

export function qzoneContentText(item = {}) {
  return qzoneDisplayText(item.content) || "图片说说";
}

export function qzoneNeedsExpand(item = {}) {
  const content = qzoneContentText(item);
  if (!content) return false;
  return content.split(/\r?\n/).length > QZONE_PREVIEW_LINES ||
    content.length > QZONE_PREVIEW_TEXT_LIMIT;
}

export function isImageFile(file) {
  return Boolean(file?.type?.startsWith("image/")) || /\.(avif|bmp|gif|jpe?g|png|webp)$/i.test(text(file?.name));
}

export function isVideoFile(file) {
  return Boolean(file?.type?.startsWith("video/")) || /\.(avi|m4v|mkv|mov|mp4|webm)$/i.test(text(file?.name));
}

export function qzoneMediaFileKind(file) {
  if (isVideoFile(file)) return "video";
  if (isImageFile(file)) return "image";
  return "";
}

export function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(String(reader.result || "")));
    reader.addEventListener("error", () => reject(new Error("媒体读取失败")));
    reader.readAsDataURL(file);
  });
}

export function dataUrlToBase64Source(dataUrl) {
  const value = text(dataUrl).trim();
  const marker = ";base64,";
  const index = value.indexOf(marker);
  return index >= 0 ? `base64://${value.slice(index + marker.length)}` : "";
}
